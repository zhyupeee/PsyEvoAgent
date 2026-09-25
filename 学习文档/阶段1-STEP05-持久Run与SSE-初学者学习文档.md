# 阶段1 · STEP05 学习文档：一条消息怎样变成可恢复的 run

> 对应项目步骤：**S1-STEP05「run、SSE 与取消」**。本文面向第一次接触后端 API、数据库事务和浏览器事件流的读者。依据当前仓库的 STEP05 源码与 [本步验收记录](../PsyEvoAgent项目计划/阶段1/evidence/S1-STEP05/README.md)编写。文中的账号、消息和回答均为讲解用的合成例子。

## 0. 先明确：这一步做成了什么

STEP04 已经有一个只能在后端内部调用的合成 Support：它能接收输入、运行固定的 LangGraph 流程、调用本地 fake 模型、检查预算和输出规则。STEP05 为它接上了**可持久保存的任务与浏览器通信链路**：

1. 用户创建对话和 run 草稿，再提交一条消息启动 run。
2. API 把消息和执行条件写进 PostgreSQL，run 进入 `queued`。
3. 独立 Worker 领取任务，调用 STEP04 的 Support。
4. 结果和事件存入 PostgreSQL；浏览器用 SSE 接收、断线后重放。
5. 用户取消、退出登录、改密码或撤销来源时，已有任务和后续读取受相应检查约束。

这里完成的是**隔离合成工程链路**。真实模型 Provider、专业内容审阅和真实 SMTP 尚未配置；正式聊天/练习页面属于 STEP06，完整删除与历史修订属于 STEP07。本文的“完成”不等于整个心理支持产品已经完成或发布。

## 1. 不懂代码时，先记住这张图

假设用户在浏览器里输入“今天有点难受，想聊聊”。这一步的程序可以想成一个小型办事处：

```text
浏览器：提交一句话，并领取任务号 run_id
    │
    ▼
FastAPI：检查登录、请求格式、来源与版本；将任务单写入数据库
    │                                 │
    │ 立即返回「已排队」               │ PostgreSQL 保存状态、消息、事件、账本
    ▼                                 ▼
浏览器继续等待  ◀── SSE 发送事件 ── Worker 领取任务、调用 fake Support
    │
    └── 断线后凭最后收到的事件编号续接；太旧则读取 run 快照
```

**API 和 Worker 是两个独立进程。** API 负责接收请求并存任务；Worker 负责真正执行。STEP05 没有引入 Kafka 等额外队列：`runs` 表里的 `queued` 状态就是 Worker 要寻找的任务。

### 1.1 同一个 `session` 词有三种不同意思

| 源码里的名字 | 在本项目里的意思 | 不要与什么混淆 |
|---|---|---|
| `Conversation`，接口常写 `session_id` | 一段对话的容器，可容纳多次 run | 不是登录凭证 |
| `IdentitySession` | 登录后的一次身份会话，关联 Cookie 与 CSRF | 不是对话 |
| SQLAlchemy 的 `Session`，常命名 `db` | Python 读写数据库的工作单元 | 不是用户会话 |

### 1.2 最重要的对象

| 对象 | 可以想成 | 主要问题 |
|---|---|---|
| `Conversation` | 对话文件夹 | “这条消息属于哪段对话？” |
| `Run` | 一张处理任务单 | “这次任务现在是草稿、排队、运行，还是已经结束？” |
| `RunExecution` | 任务启动时封存的执行说明 | “这次绑定了哪个身份、预算、期限和来源？” |
| `Message` | 输入/输出纸条 | “用户发了什么？最后允许公开的回答是什么？” |
| `RunEvent` | 发给浏览器的进度流水 | “浏览器上次收到第几条？还能补发什么？” |
| `ModelCall` | 调用账本 | “哪次 fake 调用预占了多少，实际用量是否已知？” |
| `Interaction` | 浏览器报告的互动事实 | “主动发送和活跃区间是否被重复记录？” |
| `ContextGrant` | 指向额外来源的使用授权 | “本次 run 还能引用这个来源吗？” |

## 2. 完整例子：从草稿到完成

下面以一个已登录的合成用户为例。`sid` 表示对话编号，`rid` 表示 run 编号；实际编号由服务器生成，不会是这三个字母。

### 第一步：建对话、建草稿

原有 [API 文件](../backend/app/api.py) 的 `POST /api/v1/sessions` 创建 `Conversation`；`POST /api/v1/run-drafts` 创建 `Run`。草稿里有 `owner_id`、`session_id`、`session_version`，状态默认 `draft`。此时**没有模型调用，也没有助手回答**。

草稿的意义是：先取得稳定的 `run_id`，有需要时把 `ContextGrant` 绑定到这个 run，然后再启动。没有额外来源时，启动请求中的 `grant_ids` 可以为空。

### 第二步：浏览器发启动请求

假设浏览器调用 `POST /api/v1/runs/{rid}/start`，请求正文大致是：

```json
{
  "input": {"message": "今天有点难受，想聊聊"},
  "expected_version": 1,
  "expected_session_version": 1,
  "client_message_id": "msg-example-001",
  "grant_ids": [],
  "initiation": "user"
}
```

写请求还需登录 Cookie、匹配的 Origin、`X-CSRF-Token` 和 `Idempotency-Key`。上面的 `client_message_id` 与幂等键各有职责：前者标识**这条用户消息**，后者标识**这次 HTTP 创建操作**。例子中的编号仅为说明格式，不能拿来当多个真实请求的公共编号。

`expected_version: 1` 意思是：“我认为 run 仍处于版本 1。”如果别人或另一个请求已经改变了它，服务器会返回 `409 version_conflict`，防止用过期页面状态覆盖新状态。

### 第三步：API 在一个数据库事务里排队

`start_run()` 检查上述事实后，写入 `RunExecution` 和 `Message(role="user")`，并把 `Run.status` 改为 `queued`。这一步返回 HTTP `202`：服务器**接受并排队**，不是已经生成回答。

数据库事务可理解为“几项写入一起提交”。若中途抛异常，这组写入会回滚，不应出现“任务已排队但用户消息没存下”的半成品。SQLAlchemy 的 `db.flush()` 是把当前变更发给数据库以便取得编号/检查约束；它**不等于最终提交**。

### 第四步：Worker 领取并执行

独立 Worker 在数据库中寻找 `queued` 的 run，改为 `running`，产生 `run.started`。它读取启动时保存的用户消息、预算和版本，调用 STEP04 的 Support。fake 模型当前返回固定的合成回应“这是隔离合成测试回应。”，用于验证链路，不能据此判断真实心理支持质量。

### 第五步：结果和事件一同存下

检查通过后，Worker 写 `Message(role="assistant")`，发 `message.delta`，把 run 改为 `completed` 并发 `run.completed`。一个正常例子里，浏览器会看到事件编号 `1`、`2`、`3`。`message.delta` 这个事件名沿用流协议；当前 fake 示例在一条事件里发送经过检查的完整回答，不代表真实模型逐字输出已实现。

浏览器还可以 `GET /api/v1/runs/{rid}` 读取快照：状态、当前版本、预算使用情况、最后事件编号和获准展示的回答。

## 3. 核心业务代码：按执行顺序读

### 3.1 [backend/app/models.py](../backend/app/models.py)：Python 怎样认识数据库里的表

SQLAlchemy 的一个 `class` 对应一张表。例如：

```python
class RunExecution(Personal, Base):
    __tablename__ = "run_executions"
    run_id: Mapped[str] = mapped_column(String(36))
    request_hash: Mapped[str] = mapped_column(String(64))
    budget: Mapped[dict[str, object]] = mapped_column(JSONB)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

读法：`__tablename__` 是数据库表名；`run_id` 关联原来的 `Run`；`request_hash` 是启动内容的指纹；`budget` 存这次固定的预算；`deadline_at` 存这一次执行的截止时刻。源码还规定每个 run 最多有一条 `RunExecution`。它**不再另存一份运行状态**，避免 `Run.status` 和执行表的状态相互矛盾。

本步涉及的类与重点字段：

| 类 | 关键字段/约束 | 为什么需要 |
|---|---|---|
| `Run`（原有，STEP05 扩展状态约束） | `status`、`version`、`source_message_version`、`stop_reason` | 任务的权威状态；可表示 `draft`、`queued`、`running`、`completed`、`failed`、`cancelled`、`interrupted` |
| `RunExecution` | `identity_id`、`versions`、`budget`、`grant_ids`、`deadline_at`、`generation`、`event_seq`、`event_floor` | 启动时固定执行条件；管理事件编号和取消代次 |
| `Message` | `role`、`content`、`client_message_id`；同一 run 的同一角色唯一 | 保存一条用户输入和至多一条助手输出；消息编号帮助防重复 |
| `RunEvent` | `(run_id, event_id)` 组成主键，`envelope` 保存公开事件 | 可以按编号从 PostgreSQL 重放，而非只放进内存 |
| `ModelCall` | `request_id` 唯一，`receipt` 保存调用元数据 | Worker 重试或更新账本时不会无故增加一条调用 |
| `Interaction` | `(owner_id, event_key)` 和 `(owner_id, tab_id, sequence)` 唯一 | 防止互动上报重复计数 |

`Personal` 带来 `owner_id`、版本、删除标记等共用字段。带 `owner_id` 的联合外键与代码里的 `owned()` 一起防止跨用户关联。`JSONB` 是 PostgreSQL 的结构化 JSON 字段，适合存固定版本绑定、预算、事件封套等小型结构；它不意味着可以随意把正文、密钥塞进账本。

### 3.2 [数据库迁移 d642b94fcbb5](../backend/migrations/versions/d642b94fcbb5_step05_durable_support_runs_and_events.py)：表如何真正建出来

`models.py` 只是 Python 的表描述；数据库不会因为你写了类就自动拥有新表。Alembic 迁移的 `upgrade()` 用 `op.create_table(...)` 建立 `run_executions`、`messages`、`run_events`、`model_calls`、`interaction_events`，并创建主键、外键、唯一约束和索引。

可把两者区分为：**模型文件是“当前应该长什么样”，迁移文件是“从上一版怎样走到这一版”。** `down_revision = "g034_login_attempts"` 表示它接在上一条迁移之后。`downgrade()` 若发现这些新表已有执行记录，会拒绝删表，避免把历史数据一起抹掉。它不是日常清理命令。

### 3.3 [backend/app/api.py](../backend/app/api.py)：复用原有入口、身份与授权

这个文件主要来自 STEP03，本步只改了少量连接点，但它是理解 STEP05 的前置代码：

- `identity()`：根据 Cookie 查当前登录会话，验证用户存在且未失效；写请求额外验证 Origin 和 CSRF。FastAPI 参数写 `auth: Auth` 时，就会先运行这层依赖。
- `owned()`：按**资源编号 + 当前 owner 编号 + 未删除**查询。查不到统一返回 `404`，避免别人的资源被读到。
- `create_once()`：要求 `Idempotency-Key`，把“路径 + 规范化请求正文”做成指纹。相同用户、相同键、相同内容返回原资源；同键不同内容返回 `409`。
- `create_draft()`：先确认对话属于当前用户，保存对话版本，再创建 `Run(status="draft")`。
- `create_grant()`：把额外来源与当前草稿 run 绑定；它不会自动读取整段历史正文。
- `get_run()`：STEP05 改为调用 `snapshot()`，返回经当前来源检查后的状态与回答。
- `logout()` 和密码更改逻辑：STEP05 新增停止相关活动 run，避免失效身份仍继续执行。

看看 `create_once()` 的核心判断（下面是源码节选）：

```python
previous = db.get(Idempotency, (auth.owner_id, key))
if previous is not None:
    if previous.request_hash != fingerprint:
        raise APIError(409, "idempotency_conflict")
    return owned(db, model, previous.resource_id, auth.owner_id)
```

逐行理解：`db.get(...)` 查“当前用户 + 本次操作键”以前是否用过；若用过，但正文指纹不同，就拒绝复用；若完全相同，也不是直接信任旧响应，而是用 `owned()` 重新确认现在仍可读取原资源。`return` 会让后面的“新建资源”代码不再运行。

这里的 `Idempotency-Key` 和 `RunExecution.request_hash` 是两层检查：前者识别一次 HTTP 操作，后者确保**同一个 run** 不会用不同启动内容重新执行。重试不应重新计费、重新生成任务，也不能直接返回一份过期的敏感快照，所以重放时仍检查当前权限。

### 3.4 [backend/app/runs.py](../backend/app/runs.py)：STEP05 的运行规则主体

这是最重要、也最长的业务文件。建议按以下小节读，不要第一遍就逐行啃完。

#### 请求格式：`RunInput`、`Start`、`Send`

`RunInput.message` 最长 4000 字符；校验器拒绝空白消息和 NUL。`Start` 要求 `expected_version`、`expected_session_version`、`client_message_id`、`grant_ids` 与发起类型。Pydantic 在进入业务函数前先检验这些字段，格式错通常返回 `422`。`Send` 用于便捷接口 `POST /sessions/{id}/runs`，只支持普通 `message`；历史修订和 regenerate 不属于本步。

#### `sources_available()` 与 `executable()`：现在还准不准用

`sources_available()` 查对话是否属于本人、未删除、仍活跃；启动后还核用户消息版本/删除标记及每个 grant 指向的来源是否仍有效。`executable()` 再加登录身份、任务状态、执行期限等检查。

例子：run 启动时 grant 有效，后来用户撤销 grant。Worker 在模型调用前和输出前会再次检查；浏览器重放旧事件、读取快照时也会再次检查。**过去曾经有权，不等于现在仍有权。** 没有额外 `grant_ids` 时，当前合法输入仍可以走本次 Support；grant 不等于同意记录，也不是所有输入的前置门槛。

#### `start_run()`：把草稿变成排队任务

关键逻辑可以压缩成下面的教学伪代码；实际实现还有更多校验和错误处理：

```python
if support_mode != "fake":
    raise provider_not_configured
if this_run_was_started_before:
    verify_same_request_and_current_sources()
    return original_run
verify_run_session_message_and_grants()
save_frozen_execution_budget_and_deadline()
run.status = "queued"
save_user_message()
```

源码把 fake 执行期限设为启动时刻后 10 秒，并保存到 `RunExecution.deadline_at`。断开 SSE、HTTP 重试、Worker 重启都不应重新赠送 10 秒。这个期限只管**一次执行**，业务数据没有因此设置固定 TTL。

实际写入部分可以这样读（源码节选）：

```python
db.add(ex)
run.status, run.version, run.source_message_version = "queued", run.version + 1, 1
db.add(Message(owner_id=run.owner_id, run_id=run.id, role="user",
               content=body.input.message, client_message_id=body.client_message_id))
db.flush()
```

`ex` 是刚建好的 `RunExecution`；把它加到当前数据库工作单元。下一行同时改变任务状态、资源版本和来源消息版本。`Message` 保存真实用户输入，而 `db.flush()` 让这些变更在当前事务中被数据库处理；若事务随后失败，仍会回滚。`run.version + 1` 很关键：其他仍认为版本是 1 的写请求随后必须重新核对，不能盲目覆盖。

可选的“用户主动发起”`Interaction` 用数据库保存点 `db.begin_nested()` 尝试记录：若这条统计记录失败，不让它破坏已经合法的基本消息启动。保存点可理解为“大事务里的一个局部可撤回点”。

#### `emit()`：按序存公开事件

```python
ex.event_seq += 1
db.add(RunEvent(run_id=run.id, event_id=ex.event_seq, envelope={...}))
ex.event_floor = max(0, ex.event_seq - 128)
```

`event_seq` 是下一条事件的连续编号，`event_floor` 是已过期编号的边界。假设共发出 131 条，只保留最新 128 条，也就是编号 4～131；要求从编号 1 续接就太旧了，应返回 `410`，然后由浏览器读取同一个 run 的快照。删旧事件**不会重置编号**。

事件封套里有 `schema_version`、`run_id`、字符串形式的 `event_id`、`generation`、`type`、`run_version`、时间和 `payload`。公开事件与数据库 `Run` 的资源版本是两种编号：一次 `message.delta` 不等于修改一次 `Run.version`。

#### `terminal()`：解决“取消”和“完成”同时发生

核心数据库更新条件是：

```python
Run.id == run.id
Run.version == previous
Run.status.not_in(TERMINAL)
```

意思是：**只有任务还是我刚才看到的版本、而且尚未结束，才可以写最终状态。** 假设用户点击取消，Worker 同时准备完成：先成功的一方会改变版本/状态，后来的另一方不能覆盖它。这叫 CAS，英文可理解为“先比较当前值，再决定是否写入”。代码还使用 owner 行锁让同一用户的相关写入按一致顺序进行。

`completed`、`failed`、`cancelled`、`interrupted` 都是终态。终态确定后不能出现“已经取消却又补上一段回答”。Worker 提交回答前再次查状态与 `generation`，正是为了挡住迟到结果。

#### `snapshot()`、`authorized_event()`：断线恢复也要核权

`snapshot()` 读取 run 当前事实，只有 `completed` 且来源仍有效时才带 `output`。`authorized_event()` 每次打开新的数据库事务检查登录、owner、来源和游标，再取**下一条**事件。旧游标低于 `event_floor` 返回 `410`，超前游标返回 `422`。这意味着“恢复连接”不是绕过权限拿以前的正文。

#### `interactions()`：另一种事件，不要和 `RunEvent` 混淆

浏览器可以批量报告 `session_opened` 或 `active_segment`。`event_id` 与请求指纹负责重发去重，`tab_id + sequence` 防止同一标签页倒序/重复上报。区间要求起止有序且最长 30 秒；时间偏差过大被拒绝。合并可见且有焦点的报告区间时，重叠部分只算一次。

返回里的 `reported_union_ms` **只是客户端报告区间的并集**，不是经过校准的人类注意力时长。因此 `active_ms` 明确是 `null`、`coverage` 是 `uncalibrated`。`system_push` 目前只是可报告的来源标签，不表示推送功能已经实现。

### 3.5 [backend/app/support.py](../backend/app/support.py)：STEP04 的 Support 如何接上持久账本

这不是重新造一个 Support。STEP04 已有 `meta → support → output_policy` 的单条图。STEP05 给 `SupportRuntime` 增加可选的 `record_call` 回调：模型调用之前保存预占账本，调用之后更新用量和结果。Worker 传入自己的 `store_call()`，才把原来内存里的 `CallReceipt` 变成数据库里的 `ModelCall`。

“预占”可以类比信用卡预授权：发起调用前先记最多可能耗用的预算；若取消、失败或用量未知，不能假装这次什么都没消耗。这里的价格单位是合成测试值，不是真实供应商价格。输出还要经过固定规则与来源检查，未通过时不发布回答。

### 3.6 [backend/app/run_worker.py](../backend/app/run_worker.py)：任务执行员

按函数顺序理解：

1. `fake_model()` 创建本地 fake 模型，返回固定合成文本及合成 usage。
2. `claim()` 从数据库挑 `queued` 任务，检查是否过期，把合法任务改为 `running` 并发 `run.started`。
3. `allowed()` 回数据库检查任务、身份、来源和 `generation` 是否仍有效。
4. `store_call()` 把 `CallReceipt` 的**元数据**写到 `ModelCall`；不会把提示词、回答正文、凭证或异常原文写入调用账本。
5. `execute()` 从数据库读用户消息和启动绑定，运行 `SupportRuntime`，在执行中不断用 `allowed()` 检查；合格时存助手消息、发 `message.delta`、置 `completed`。
6. `execute_one()` 完成一次“领取 + 执行”；`consume()` 循环调用它。

`claim()` 里最直观的两行是（源码节选）：

```python
run.status, run.version, run.updated_at = "running", run.version + 1, now()
emit(db, run, ex, "run.started", {})
```

这不是“已经回答”，只是把任务标成正在执行并留下开始事件。`execute()` 最后发布答案的条件更严格（源码节选）：

```python
if run.status != "running" or ex.generation != generation:
    return
if not executable(db, run, ex):
    terminal(db, run, ex, "cancelled", "source_unavailable")
elif result.rule_verdict != "pass" or result.text is None:
    terminal(db, run, ex, "failed", result.stop_reason or "output_unavailable")
else:
    emit(db, run, ex, "message.delta", {"text": result.text})
    db.add(Message(owner_id=owner, run_id=run_id, role="assistant", content=result.text))
    terminal(db, run, ex, "completed", None)
```

第一关看 run 是否仍在运行、代次是否还是领取时的代次；第二关重新核身份和来源；第三关看 STEP04 的输出规则是否通过。只有走到 `else`，回答才会进入公开事件和助手消息。`emit()`、新增消息与 `terminal()` 在同一个数据库事务中提交，因此不会把尚未完成检查的候选文本提前当成成功回答发布。

`claim()` 与 `terminal()` 都遵循先锁 owner 再操作 run 的顺序，降低并发互相卡住的风险。`execute()` 即使拿到了一个答案，也要在最终数据库事务中复核 run 仍是 `running`、代次未变、来源仍有效。若用户刚取消，旧答案就不能迟到后写进去。

Worker 是单独启动的进程。`consume()` 收到停止信号时，会等正在运行的有界线程结束，再释放数据库连接池；否则线程可能还在用已关闭的连接。

### 3.7 [backend/app/run_stream.py](../backend/app/run_stream.py)：浏览器怎样接收 SSE

SSE（Server-Sent Events）是一个保持打开的 HTTP GET 响应，服务器可以不断发送文本事件。浏览器原生 `EventSource` 能接收并在断线后重连。此处只读，不会因为连接 SSE 而启动模型。

`events()` 先读 `after_event_id` 或 `Last-Event-ID`；两者若同时存在且不同，返回 `422`。随后调用 `authorized_event()` 做握手检查。发送循环每次只取一条事件、重新核权，再交给 FastAPI 的原生 SSE 编码器。没新事件时发注释心跳。慢连接超过 2 秒发送超时会关闭订阅，不改变 run 原有期限。

看发送循环中的关键部分（源码节选）：

```python
data, done, _ = await asyncio.to_thread(
    authorized_event, engine, owner, identity_id, run_id, current_cursor
)
if data is not None:
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    frame = format_sse_event(
        data_str=payload.decode(), event=str(data["type"]), id=str(data["event_id"])
    )
    current_cursor = int(str(data["event_id"]))
    yield frame
```

`await asyncio.to_thread(...)` 把数据库检查放进工作线程，避免堵住处理其他连接的异步事件循环。`authorized_event()` 每次只取下一条有权看的事件。`json.dumps()` 把 Python 字典转成 JSON；`format_sse_event()` 再把它变成浏览器认识的 SSE 文本；`yield frame` 才是真正向 HTTP 响应交出一帧。源码在这些行之间还做单帧大小检查；这里为了看清主干省略了那些行。若这一帧在网络上没送达，浏览器重连时仍可用自己**最后确实收到**的编号请求重放。

`Connections` 目前限制**单个 API 进程**内每位 owner 最多两条 SSE 连接；它不是多进程集群的全局配额。单帧上限 32768 字节，事件保留窗口为每 run 128 条。流失效后应查询当前授权的 run 快照，而不是无限尝试取早已删除的旧事件。

### 3.8 [backend/app/config.py](../backend/app/config.py)、[main.py](../backend/app/main.py)、[worker.py](../backend/app/worker.py)：如何组装与启动

- `config.py` 的 `support_mode` 默认 `disabled`。只有显式设为 `fake`、环境为 `test`、数据库是本机独立合成 check 库时，才接受这个模式。`load_settings()` 从指定环境变量读取配置，不自动读取 `.env`。
- `main.py` 的 `create_app()` 把原有 API、`runs_router`、`stream_router` 注册到同一个 FastAPI 应用，并创建连接计数器。**注册路由不等于启动 Worker**；API 导入或热重载时不应产生消费者。
- `worker.py` 是命令行入口；只有显式添加 `--support`，才导入并运行 `run_worker.consume()`。不加此参数仍是原有生命周期探针。

把组装关系记成下面三行就够了（分别来自三个文件的源码节选）：

```python
support_mode: Literal["disabled", "fake"] = "disabled"  # config.py：默认不开执行
application.include_router(runs_router)               # main.py：注册运行 API
application.include_router(stream_router)             # main.py：注册 SSE API
```

`include_router()` 是“让 Web 服务认识这些路径”，不是“马上处理排队任务”。后台处理要另开 `python -m app.worker --support`；这也解释了为什么 API 热重载不应顺手启动一个新的消费者。

## 4. 新旧 API 连接关系

| 请求 | 主要实现 | 成功时发生什么 | 初学者要记住 |
|---|---|---|---|
| `POST /api/v1/sessions` | `api.py` | 建一段对话 | `session_id` 是对话编号 |
| `POST /api/v1/run-drafts` | `api.py` | 建一个 `draft` run | 不调用模型 |
| `POST /api/v1/context-grants` | `api.py` | 给草稿关联可用来源 | 没有额外来源时可不创建；撤销后还会重新核权 |
| `POST /api/v1/runs/{id}/start` | `runs.py` | 存消息和执行绑定，进入 `queued` | 返回 `202` 表示已接受排队 |
| `POST /api/v1/sessions/{id}/runs` | `runs.py` | 便捷创建并启动普通消息 run | 相同客户端消息编号/内容可找回原 run |
| `POST /api/v1/runs/{id}/cancel` | `runs.py` | 在版本符合时结束活动 run | 终态已确定时返回已提交的事实 |
| `GET /api/v1/runs/{id}` | `api.py` → `runs.py` | 返回当前授权的快照 | 可用于断线恢复 |
| `GET /api/v1/runs/{id}/events` | `run_stream.py` → `runs.py` | SSE 发送或重放事件 | 每条事件都重新核权 |
| `POST /api/v1/interaction-events` | `runs.py` | 去重保存报告的互动 | 与服务器发出的 `RunEvent` 不同 |

几个常见状态码：`202` 是已接受排队；`401` 是未登录或会话失效；`403` 是请求/授权不允许；`404` 是当前用户看不到该资源；`409` 常见于版本或幂等冲突；`410` 是 SSE 游标已经过期；`422` 是请求格式或游标错误；默认未启用 fake 执行时启动返回 `503 provider_not_configured`。

## 5. 浏览器与测试文件：为什么它们不是正式聊天页

### [frontend/playwright.step05.config.ts](../frontend/playwright.step05.config.ts)

这是 Playwright 的测试配置。开头要求环境里存在合成数据库 URL 且 `PSYEVO_SUPPORT_MODE=fake`，否则立即报错。`testMatch: ['runs.spec.ts']` 表示只运行本步浏览器用例。`webServer` 启动一个测试专用 FastAPI 工厂和现有前端开发服务器；浏览器通过前端同源代理请求 `/api/v1`。

### [frontend/tests/runs.spec.ts](../frontend/tests/runs.spec.ts)

这个文件让真实测试浏览器依次登录、创建对话/草稿/grant、启动、使用原生 `EventSource` 接收事件，主动断开再凭游标续接，验证重复事件不会被当成多条不同进度。它还查询快照、验证完成后再取消不会改写终态、制造过期游标得到 `410`，最后撤销 grant 并验证旧正文不能继续读取。

它借 `/health` 页面运行测试脚本，是**浏览器验收消费者**。用户实际使用的 STEP06 聊天输入框、消息列表等页面尚未创建。

### [backend/tests/run_gateway.py](../backend/tests/run_gateway.py)

这是测试专用 API 工厂。它在正常 API 上额外注册 `/checks/runs/{run_id}/expire-cursor`：对已完成的合成 run 人工写入 130 条事件，使早期游标被 128 条窗口淘汰。这样浏览器测试能稳定验证 `410 → 快照恢复`。正式 `app.main` 不注册这个测试接口。

## 6. 自动测试文件：每个在验证什么

读测试时，先找 `test_...` 函数名，再看 **准备数据 → 执行动作 → `assert` 判断**。`assert` 就是“如果事实不符合预期，测试失败”。

| 文件 | 关键代码与学习重点 |
|---|---|
| [backend/tests/test_runs.py](../backend/tests/test_runs.py) | `client()` 为每个用例创建独立合成身份；`create()` 建对话/草稿/可选 grant；`test_draft_start_replay_and_persisted_output()` 先断言草稿零调用，再启动、重试、执行 Worker、查快照和事件编号，并查数据库唯一记录。其他用例覆盖并发 start、CAS、取消、撤权、过期游标、预算与互动去重。带 `postgres` 标记，须在隔离真实 PostgreSQL 上运行。 |
| [backend/tests/test_run_stream.py](../backend/tests/test_run_stream.py) | 模拟网络发送被卡住，检查只提前取到一条事件；测每用户连接上限、区间合并、默认 fake 禁用，以及 Worker 停止时先等线程结束再关连接池。 |
| [backend/tests/test_step03_migrations.py](../backend/tests/test_step03_migrations.py) | `test_step05_upgrade_preserves_runs_and_refuses_lossy_downgrade()` 先在上一版数据库里放一个 run，升级后确认还在，再加入执行记录，检查有历史时不能有损降级。 |
| [backend/tests/test_step03.py](../backend/tests/test_step03.py) | 老用例原以为 `start` 不存在；现在改为检验空正文 `422`，同时保留原有身份/来源测试。 |
| [backend/tests/test_foundation.py](../backend/tests/test_foundation.py) | 老用例原以为 API 没有 start 路由；现在检查路由存在，但“毒化” Worker 模块后 API 仍能导入，证明 API 导入不会偷偷启动消费者。 |
| [frontend/tests/runs.spec.ts](../frontend/tests/runs.spec.ts) | 经实际浏览器、前端网关、API、PostgreSQL、独立 fake Worker 验证断线续接；与只在 Python 内调用函数的测试相比，它多验证浏览器及代理行为。 |

这些测试不是完整业务验收。它们只证明对应的合成工程场景按预期运行；真实 Provider 的效果、真实邮件和 STEP06 用户页面不在这些断言内。

## 7. 检查脚本与工程配置：怎样产生验收收据

### [scripts/check_step05.py](../scripts/check_step05.py)

这个短文件只是入口，等价于调用 `check_step03.py --step05`，复用此前已经有的临时 PostgreSQL 和浏览器门禁，避免复制一整套脚本。

### [scripts/check_step03.py](../scripts/check_step03.py)

STEP05 给原脚本增加 `--step05` 分支。它创建随机命名的**临时** PostgreSQL 容器，设置隔离测试环境，依次检查锁文件、Ruff、mypy、迁移、schema drift、PostgreSQL 测试、后端工程测试、前端构建/check、已有浏览器/HTTPS 用例。STEP05 分支额外准备合成账号、显式启动 `app.worker --support`，运行 STEP05 浏览器用例，重启数据库，再直接查询 run、调用账本、互动与 128 条事件是否仍在。最后只清理本次创建的临时容器，并写出 `receipt.json` 和每条命令的日志。

脚本里的 `run(label, args, ...)` 是一个小型命令执行器：`subprocess.run(args, ...)` 启动外部程序，捕获标准输出和错误输出，写入以 `label` 命名的 `.txt`；同时把退出码加进 `receipt.json`。**退出码 0** 表示该命令正常完成；非 0 会抛出错误，使门禁失败。`finally` 块负责清理本次创建的容器，并尝试留下收据，方便知道失败发生在哪一步。

不要把“数据库重启后还在”和“服务已公开部署”混为一谈；这里检查的是本机隔离合成容器的数据持久性。

### [backend/pyproject.toml](../backend/pyproject.toml)

这个文件配置 Python 项目、Ruff、mypy 和 pytest。STEP05 为锁定的 Starlette `TestClient` 所用 AnyIO 弃用别名添加一条**精确匹配**的警告豁免；其他警告仍作为错误处理。这属于测试环境兼容设置，不是业务规则。

## 8. 规划与证据文件：看到“通过”时看哪一份

| 文件 | 它回答的问题 |
|---|---|
| [README.md](../README.md) | 整个仓库现在推进到哪里？顶部是 STEP05 当前状态，下面还有保留的历史时点摘要。 |
| [AGENTS.md](../AGENTS.md) | 后续协作者该遵守哪些仓库规则？顶部新增 STEP05 入口和边界。 |
| [DEVELOPMENT.md](../DEVELOPMENT.md) | 本地怎样运行 STEP05 检查和 fake Worker？配置从哪里读取？ |
| [阶段1/02-技术方案与实施计划.md](../PsyEvoAgent项目计划/阶段1/02-技术方案与实施计划.md#public-events) | STEP05 实际接口、事件、预算、来源、数据结构有什么约定？这是“合同”。 |
| [阶段1/03-测试与验收标准.md](../PsyEvoAgent项目计划/阶段1/03-测试与验收标准.md#s1-step05-validation) | 怎样验证这些合同？需要观察哪些正常和失败情形？ |
| [阶段1/04-分步实施与检查清单.md](../PsyEvoAgent项目计划/阶段1/04-分步实施与检查清单.md#s1-step05) | STEP05.1～05.4 的实施进度是什么？ |
| [S1-STEP05 证据总览](../PsyEvoAgent项目计划/阶段1/evidence/S1-STEP05/README.md) | 实际运行了哪些门禁、结果是什么、还存在哪些边界？ |

证据目录里的单个文件这样识别：

- `windows/receipt.json` 是 Windows 完整门禁的机器收据，含命令退出码和源码哈希；`windows/postgres-tests.xml` 是 PostgreSQL/API/迁移的 JUnit 结果；`windows/step05-gateway.txt` 是浏览器全链日志；`windows/step05-restart-facts.txt` 是数据库重启后的直接查询结果。
- `windows/` 的其余 `.txt` 是单项命令日志，例如 `lint`、`types`、`migration`、`frontend-check`、`database-cleanup`。某些日志为空，只表示该命令没有输出，须结合总收据里的退出码判断。
- `wsl/receipt.json`、`engineering.json`、`runtime.json` 等记录 WSL 内核隔离的工程及 fake Support 检查。其复用封装的 `step_id` 仍写 STEP04；不能把它说成 STEP05 的 PostgreSQL 全链也做了同一种内核隔离。
- `step05-first.xml`、`step05-inflight.xml`、`failure-old-start-assertion/`、`failure-old-import-assertion/`、`wsl-missing-pnpm/`、`wsl-missing-docs/` 是过程中的**失败记录**，用于说明发现并修复了哪些问题；最终结果看总览和最终收据。
- `prerequisite-support.xml` 是 STEP04 前置复验；`wsl-negative.txt` 是隔离失效时应失败的负例；`closure.txt` 是收尾文档与差异检查。

现有归档写明：最终 Windows 门禁有 42 项隔离真实 PostgreSQL/API/迁移测试、65 项后端工程测试，并完成浏览器/HTTPS 检查；WSL 隔离工程门禁另有记录。**这些数字来自本次已有收据，不是本文重新运行测试所得。**

## 9. 用几个失败场景检查自己是否真正理解

### 场景 A：浏览器超时，用户又点了一次“发送”

若它携带相同 `Idempotency-Key`、相同正文，服务器应返回原 run；若同一个键换了正文，返回 `409`。同一个 `client_message_id` 也帮助识别重复消息。目标是避免网络重试变成两次实际处理或两次主动发送统计。

### 场景 B：用户在 Worker 正要完成时点“取消”

`terminal()` 的版本与终态条件只允许一个终态成功。若取消先提交，Worker 最终复核发现状态或 `generation` 已变化，不写迟到回答；若完成先提交，之后的取消返回已经完成的事实。

### 场景 C：浏览器看到事件 1 后断网

重新连接并带游标 `1`，服务器只重放大于 1 的事件。浏览器用 `event_id` 去重，避免重连时把同一段回答显示两遍。若游标已低于保留窗口，得到 `410`，再读取当前授权的 run 快照。

### 场景 D：授权来源被撤销

启动时授权有效不保证以后一直有效。Worker 提交前和 SSE 重放/快照读取时均再次检查。若来源已不可用，不能继续凭旧连接或旧游标拿到旧正文。这是“每次使用时核权”的典型例子。

### 场景 E：模型调用中断，用量没有可靠结果

调用前的预占记录已写入 `ModelCall`。结果未知时保留预占，`budget_used.usage_unknown` 能说明“实际量未知”；不能为了让账本好看就写成 0，也不能把合成价格当真实供应商价格。

## 10. 建议的学习顺序与练习

第一次阅读时，按这条短路径走：

1. 看 [test_runs.py 的第一个用例](../backend/tests/test_runs.py)，跟着 `create → start → execute_one → GET run → events` 走一遍。
2. 看 [runs.py 的 `start_run()`](../backend/app/runs.py)，找出“哪一行使状态变成 `queued`”。
3. 看 [run_worker.py](../backend/app/run_worker.py)，找出“哪一行领取任务、哪一行存助手回答”。
4. 看 [run_stream.py](../backend/app/run_stream.py)，找出“从哪里读取游标、在哪里逐条核权”。
5. 回头看 [models.py](../backend/app/models.py) 与 [迁移](../backend/migrations/versions/d642b94fcbb5_step05_durable_support_runs_and_events.py)，把代码里的对象和实际表对应起来。

可以用下面的问题自测，不需要改动任何文件：

1. `draft` 和 `queued` 最大的区别是什么？为什么创建草稿不应调用模型？
2. `Run.status` 和 `RunExecution.generation` 分别解决什么问题？
3. 为什么 `db.flush()` 后还不能说“数据库事务已经提交”？
4. 浏览器断线后，为什么不能直接信任旧事件，而要重新检查当前身份和来源？
5. 同一次消息的 `client_message_id` 与 `Idempotency-Key` 为什么不能只保留其中一个？
6. `RunEvent` 与 `Interaction` 都叫“事件”，方向和用途有何不同？
7. 为什么 `reported_union_ms` 可以有数字，但 `active_ms` 仍应是 `null`？

如果能用“**API 存排队任务 → Worker 执行 → 数据库存结果与事件 → SSE 只读发送 → 取消/重放都查当前事实**”解释这一步，你就已经抓住 STEP05 的主干了。之后再看预算、并发和测试细节会容易许多。
