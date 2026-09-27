# 阶段1 · STEP07 学习文档：历史、修订、删除与反馈怎样协作

> 对应项目步骤：**S1-STEP07「历史修订、删除与反馈」**。本文面向第一次接触版本化数据、幂等请求和删除任务的读者，依据当前源码、[本步技术合同](../PsyEvoAgent项目计划/阶段1/02-技术方案与实施计划.md#s1-step07-implementation)、[验收协议](../PsyEvoAgent项目计划/阶段1/03-测试与验收标准.md#s1-step07-validation)及[执行证据](../PsyEvoAgent项目计划/阶段1/evidence/S1-STEP07/README.md)编写。文中的对话均为合成示例。

## 0. 先明确：这一步做成了什么

STEP06 只能查看一个会话的当前轮次。STEP07 在既有登录、消息、run、SSE 和独立 Worker 上增加四组能力：

1. 搜索本人会话标题，归档、恢复和查看有界分页的历史轮次。
2. 修订最后一条输入或用它重新生成；每次创建新 run 和新用户消息，旧分支保留为只读历史。
3. 在 run 结束后自愿提交帮助度、误解纠正等反馈，或直接跳过。
4. 确认删除会话后立即阻断访问，逐项清理在线内容，并在“删除处理记录”查看或重试未完成的任务。

这是**隔离合成工程交付**。本步没有接入真实模型 Provider、真实 SMTP、经专业审阅的支持内容，也没有对外发布。STEP08 的真实模型联调和整阶段交接尚未实施；153 项业务验收不能由本步工程测试推定为已通过。

## 1. 不懂代码时，先看数据怎样流动

```text
浏览器 /chat 或 /chat/{session_id}
  │ 搜索、改名、归档、修订、反馈或确认删除
  ▼
FastAPI：核对登录身份、owner、版本、来源与幂等键
  │
  ▼
PostgreSQL：原 Conversation / Run / Message / Event
            新 feedback / run_branches
  │
  ├─ 修订/重新生成 → 新 run → 既有 start → 独立 fake Worker → 既有 SSE
  └─ 确认删除 → 先提交在线阻断 → 分事务清理 → 持久删除回执
```

**数据库里的会话、run 和消息仍是业务事实。** `run_branches` 只记录“新 run 从哪个旧 run 来”；它不复制一份独立的对话正文。`feedback` 保存用户主动填写的评价，不自动附上完整对话。删除任务的回执说明实际处理到哪一步，不能只看网页是否跳走。

### 1.1 六个容易混淆的名字

| 名称 | 本步含义 | 直观理解 |
|---|---|---|
| `Conversation` | 一个用户拥有的会话，可为 `active`、`archived` 或 `deleted` | 对话文件夹 |
| `Run` | 一次回答生成及其状态 | 文件夹里的一次处理 |
| `Message.version` | 输入的版本；修订或重新生成产生新消息 | 这句话的第几版 |
| `RunBranch` | 新旧 run 的父子关系和分支类型 | 版本之间的一条连线 |
| `Feedback` | 对某个终态 run 的自愿评价 | 单独的反馈表单 |
| `DeletionJob` | 删除任务、已完成项和剩余项 | 可再次查询的处理回执 |

注意：会话的 `version` 用于改名、归档和删除时的并发检查；消息的 `version` 用于修订时确认“要改的是哪一版”。它们不是同一个计数器。

### 1.2 主要代码位置

| 文件 | 负责什么 |
|---|---|
| [backend/app/history.py](../backend/app/history.py) | 本人列表、历史、分支建立与反馈写入 |
| [backend/app/deletion.py](../backend/app/deletion.py) | 先阻断、逐项清理、回执查询与重试 |
| [backend/app/runs.py](../backend/app/runs.py) | 原有 start/快照/来源规则，以及新分支的启动和去重 |
| [backend/app/pages.py](../backend/app/pages.py) | 当前轮次排除已被替代的旧分支 |
| [backend/app/models.py](../backend/app/models.py) 与 [h007 迁移](../backend/migrations/versions/h007_history_feedback.py) | 两张新增表及 owner 约束 |
| [frontend/src/history-page.tsx](../frontend/src/history-page.tsx) | 会话列表、管理、历史、反馈、修订与删除回执组件 |
| [frontend/src/chat-page.tsx](../frontend/src/chat-page.tsx) 与 [support-shell.tsx](../frontend/src/support-shell.tsx) | 当前会话组合、跨标签通知与重新核权 |

## 2. 完整例子：从一句旧输入到一个新分支

假设合成用户在会话 A 的最后一轮写了“今天很累”，回答已结束。用户想把它改成“今天很累，想先被倾听”。以下是页面和服务器真正做的事。

### 第一步：打开本人会话和历史

`/chat` 调用 `GET /api/v1/sessions`。搜索参数 `q` 只匹配**标题**；`status` 在未归档和已归档之间切换，游标用于取更早的一批。默认一批 20 条，最多 100 条。删除的会话不列出，列表也不搜索消息正文。

进入 `/chat/{session_id}` 后，页面读取会话、`current-run` 和 `GET /api/v1/sessions/{session_id}/history`。历史接口只允许 owner 查询，并逐轮检查来源是否仍有效；失效来源对应的轮次不会把输入或回答正文返回给页面。历史包含 `input_id`、`input_version`、`branch_id`、`parent_run_id` 和 `is_current`，便于看出新旧分支。

### 第二步：保存修订，建立新草稿

用户打开“修订最后输入”并提交新文字。页面先用 Zod 检查：去首尾空白后必须非空、不含 NUL、最多 4000 字；校验失败仍可直接改正，也不会占用一次待重试的幂等尝试。随后调用：

```text
POST /api/v1/sessions/{session_id}/messages/{input_id}/revisions
Idempotency-Key: 同一次修订尝试的固定键

{ "content": "今天很累，想先被倾听", "expected_version": 1 }
```

服务器确认会话处于 `active`、消息属于当前用户与此会话、它是最后输入、版本仍为 1，且旧运行已终止、来源仍有效。成功时建立新 `Run`、新用户 `Message` 和一条 `RunBranch`，新消息版本为 2。**到这里仍只是草稿，不会调用模型。** 活动 run、过期版本或别人的消息会被拒绝。

### 第三步：启动新 run，等待权威快照

页面拿到新草稿的 `run_id` 和 `input_id`，再调用 `POST /api/v1/runs/{run_id}/start`，把 `input.source_message_id` 指向刚建立的新消息。start 不能改用另一段 `input.message` 偷换修订内容；它沿用 STEP05 的来源、预算、幂等、取消和 Worker 规则。

Worker 在隔离测试中使用 fake Support。页面接到 SSE 更新后重新读 `current-run`；新 run 是当前轮次，旧 run 仍在历史里并标作旧分支。新旧输入与回答没有被覆盖。模型上下文只取本次新输入，不把旧输入或旧回答拼进去。

“重新生成”走 `POST /api/v1/sessions/{session_id}/runs`，`kind` 为 `regenerate`，输入指向最后用户消息的 ID。服务器同样创建新 run、新消息和分支，但新消息正文沿用原输入。它是**相同文字再生成一次回答**，不是原 run 重跑或覆盖原回答。`client_message_id` 与 `Idempotency-Key` 共同防止丢回执后的重试变成两次生成。

### 第四步：可选反馈

终态 run 下方有“反馈或纠正 · 可跳过”。用户可以选帮助度与类别、留空补充说明、取消，或者完全不打开表单。提交示意：

```json
{
  "run_id": "本轮 run 的 UUID",
  "helpfulness": "unhelpful",
  "category": "misunderstood",
  "comment": ""
}
```

`POST /api/v1/feedback` 成功返回真实 `feedback_id`、`saved` 和 `feedback-scope/1`。服务端先确认 run 属于本人、可读且已终止；反馈表不复制对话正文，也不会自动修改交流偏好或安全策略。网页在请求失败时显示“未确认”，用原幂等键重试同一份反馈；只有拿到成功回应才显示保存回执。

## 3. 历史、归档和分支为什么要分开

### 3.1 改名和归档只改会话元数据

会话页的“管理此对话”用 `PATCH /api/v1/sessions/{id}` 修改标题或 `active/archived` 状态，并带 `expected_version`。服务器发现版本冲突或仍有活动运行就返回冲突，页面不显示“已保存”。归档后会话转到“已归档”列表；恢复后可继续发送。归档不会删除历史，也不改变旧输入正文。

纯元数据修改会更新仍有效的本会话版本绑定；它不会让失效的旧草稿或旧来源重新获权。删除状态无法通过 PATCH 恢复。

### 3.2 历史读模型不等于当前轮次

[history.py](../backend/app/history.py)按创建时间和 ID 分页读取所有未删除 run；每个返回项附上对应用户输入、可展示回答和父分支 ID。[pages.py](../backend/app/pages.py) 的 `current-run` 则排除已经成为父分支的 run，只呈现当前末端。因此旧分支仍可在有权时回看，却不会成为当前回答。

一个会话中可能有普通历史轮次，也可能有修订链。`is_current` 表示该 run 是否已被后续分支替代；它不是“这是会话唯一的一轮”。读接口只读取事实，不会因打开历史或刷新页面而启动生成。

### 3.3 来源权限每次使用时重新核对

修订和重新生成只继承仍有效的来源绑定。创建草稿、启动、Worker 提交、快照和历史读取都会在各自边界检查；来源随后被撤销或删除，旧分支与新分支都不能凭曾经的授权继续展示正文。评审修复还覆盖了**草稿尚无 `RunExecution`** 时的继承 grant 检查：这种草稿也不能漏过来源核权。

## 4. 删除：为什么要先阻断，再看回执

删除是重要操作，页面用原生 `dialog` 先说明范围并要求确认；“暂不删除”获得默认焦点，按 Escape 可以退出。真正提交时调用 `DELETE /api/v1/sessions/{id}`，请求包含 `confirmed: true`、当前会话 `expected_version` 和固定 `Idempotency-Key`。

删除按下面的顺序进行：

```text
确认请求
  → 事务 1：会话标记 deleted，关联 run 取消/屏障，DeletionJob 记 online_blocked
  → 事务 2：清空消息正文和标题
  → 事务 3：移除公共 SSE 与互动事件
  → 事务 4：移除关联反馈
  → 事务 5：撤销并清理来源关联
  → 回执状态 completed
```

第一个事务提交后，旧 URL、快照、SSE 与历史就不能继续读取被删正文；正在运行的 Worker 也不能迟到写入回答。后续每个清理步骤独立提交。若某步失败，先前的在线阻断不会回滚，任务记录 `failed_retryable`、已完成项、剩余项及错误码。用户在“删除处理记录”通过 `GET /api/v1/deletion-jobs` 查询，或用任务当前 `expected_version` 调用 `POST /api/v1/deletion-jobs/{id}/retry`。重试从未完成步骤继续，不能把部分清理说成完全完成。

网页一旦发出确认，就先隐藏当前正文。若服务器已完成、但回应丢失，重试沿用原删除幂等键，得到同一任务；确认成功后清理 Query 缓存并整页回到列表。另一标签页收到删除通知也整页重新核权。退出账号和浏览器前进/后退缓存恢复同样重新核权。

**“清理完成”有明确范围。** 在线标题、消息版本正文、事件、反馈和来源使用被清理；消息/run 的无正文墓碑、幂等摘要及用量元数据保留，用于拒绝迟到写入、识别重放和解释未知消耗。当前没有持久 LangGraph checkpointer、应用备份服务或 live Provider，回执对这些项写明“不适用”，不能据此声称已清理一个不存在的外部副本。以后若启用这些存储，删除范围和验证必须同步扩展。

## 5. 页面状态与数据库事实各归谁管

| 用户动作 | 页面做什么 | 服务器保存什么 |
|---|---|---|
| 搜索/翻页 | React Query 按条件读取，表单控制标题查询 | 会话列表查询，不写消息 |
| 改名/归档 | 成功后刷新相关查询 | `Conversation` 状态、标题和版本 |
| 修订 | Form + Zod 校验，保留未确认尝试 | 新 run、消息版本和分支边 |
| 重新生成 | 用最后输入 ID 发起幂等请求 | 新 run/消息、分支与既有执行记录 |
| 反馈 | 可跳过；失败时不显示成功 | `Feedback` 与真实回执 ID |
| 删除 | 确认后隐藏正文；查询或重试回执 | 先持久阻断，再按步骤清理和记录 |

前端复用现有 TanStack Start/Router、Query、Form、Zod 与蓝白主题，没有增加依赖或第二套身份状态。`BroadcastChannel` 只广播变更类型、会话 ID 和标签页标识，不传正文。普通改名、归档、修订和重新生成只刷新会话列表及受影响会话的查询，保留**无关标签页**未提交的聊天、修订与反馈表单；删除和退出则要求整页重新核权。Query 缓存只在内存中，没有把聊天正文写入 `localStorage`。

## 6. 表和迁移：实际新增了什么

[迁移 `h007_history_feedback`](../backend/migrations/versions/h007_history_feedback.py)只新增 `feedback` 和 `run_branches` 两张表。`feedback` 用 `(run_id, owner_id)` 关联本人 run；`run_branches` 对新旧 run 都使用包含 owner 的复合外键，并限制一条父分支只有一条后续边。已有会话、run、消息和 SSE 表继续使用，不复制另一套正文或启动第二个 Worker。

迁移在空库及上版数据上都经过检查；重复升级应保持稳定。两张新表已有数据时，降级会主动拒绝丢弃它们。现有开发库只能按 [DEVELOPMENT.md](../DEVELOPMENT.md) 做增量迁移，不能通过删卷或重置来“验证”本教程。

## 7. 测试和证据在证明什么

| 入口 | 主要检查 |
|---|---|
| [backend/tests/test_history.py](../backend/tests/test_history.py) | 本人隔离、来源失效、反馈去重、修订/重新生成上下文、删除故障与重试、运行中删除、分页 |
| [backend/tests/test_history_contracts.py](../backend/tests/test_history_contracts.py) | STEP05 旧 start 请求摘要保持兼容 |
| [frontend/tests/history.spec.ts](../frontend/tests/history.spec.ts) | 真实页面中的反馈丢回执、搜索归档与分支、跨标签表单保留、手机视口删除及退出返回阻断 |
| [scripts/check_step07.py](../scripts/check_step07.py) | 调用隔离 PostgreSQL、实际 API/网关、fake Worker、前置回归、页面和数据库重启核对 |

[原交付记录](../PsyEvoAgent项目计划/阶段1/evidence/S1-STEP07/README.md)有 65 项 PostgreSQL/API/迁移和 3 项 STEP07 页面通过。其后[评审修复复验](../PsyEvoAgent项目计划/阶段1/evidence/S1-STEP07/review-fixes.md)增加草稿来源、修订输入恢复及跨标签检查；**最终完整复验**为 68 项 PostgreSQL/API/迁移、66 项后端回归、4 项 STEP07 页面通过，前端 `check`/`build`、前置页面和数据库重启直查也通过。原失败与原交付收据保留，未被新数字覆盖。

Windows 门禁使用随机独立的合成 PostgreSQL 容器，不操作开发库。WSL 的内核隔离收据覆盖工程和 fake Support 检查；STEP07 PostgreSQL/API 与页面全链由 Windows 门禁验证，不能说它们也都在 WSL 内核隔离中运行。这些是工程执行证据，不证明真实模型质量、专业内容、SMTP、实际发布或全部 153 项业务验收。

## 8. 用几个失败场景检查自己是否理解

### 场景 A：两页同时改名

两页都读到会话版本 3。第一页 PATCH 成功后版本变化；第二页还带 `expected_version: 3`，服务器拒绝旧值。第二页应重新查询后再提交，不能只靠本地输入框判断保存成功。

### 场景 B：修订请求成功，网页没收到回应

页面保留同一次尝试的键和文字，再用原键重试；服务器返回原草稿。若用户把文字改成另一段，应先解决旧尝试，不能拿同一个键创建含不同正文的新版本。若本地输入只是空白，校验应先失败，用户改好后仍能提交或选择重新生成。

### 场景 C：修订草稿创建后，来源被撤销

即使草稿还没有执行记录，读取快照和历史也必须核对它继承的 grant。来源失效后拒绝正文；不能因为它只是 `draft` 就绕过检查。

### 场景 D：反馈已保存，但浏览器收到网络错误

页面仍显示“未确认”。同一内容、同一 `Idempotency-Key` 重试后拿回原 `feedback_id`，数据库只有一条反馈；不能凭按钮点击次数声称提交了几次。

### 场景 E：删除消息后，清理事件时出错

会话仍保持 `deleted` 且不可读。回执列出 `online_blocked`、`messages` 已完成，`events` 等仍待处理；用户可按任务版本重试。不能显示“清理完成”，也不能在重试期间重新开放会话。

## 9. 建议的学习顺序与自测

按一次用户操作走源码，比先读完整数据库模型更容易：

1. 看 [history-page.tsx](../frontend/src/history-page.tsx) 的 `SessionList`、`BranchActions`、`FeedbackForm` 和 `SessionActions`，找每个按钮发送的请求。
2. 看 [history.py](../backend/app/history.py) 的 `sessions()`、`history()`、`fork_run()`、`revise()` 与 `feedback()`，对应前端请求。
3. 看 [runs.py](../backend/app/runs.py) 的 `start_run()` 和 `send()`，理解草稿怎样变成排队 run，以及重试如何去重。
4. 看 [deletion.py](../backend/app/deletion.py) 的 `remove()`、`cleanup()` 和 `receipt()`，区分持久阻断与分步清理。
5. 最后看[迁移](../backend/migrations/versions/h007_history_feedback.py)、[页面用例](../frontend/tests/history.spec.ts)和[最终复验证据](../PsyEvoAgent项目计划/阶段1/evidence/S1-STEP07/review-fixes.md)。

可以用这些问题自测：

1. 为什么修订接口返回草稿后，页面还要单独调用 start？
2. 修订和重新生成各自改变什么？旧回答为什么还在历史里？
3. `Conversation.version` 和 `Message.version` 分别防止哪种过期操作？
4. 为什么历史列表不能只检查登录态，还要检查 owner 和来源？
5. 删除回执里的 `completed_steps` 与 `remaining_steps` 怎样避免“部分成功”被误认为“完全成功”？
6. 为什么保留无正文墓碑和未知用量记录，同时仍可声明本步在线内容清理完成？
7. 普通改名的跨标签通知与删除通知为什么采用不同的刷新方式？

能用“**旧 run 留在历史 → 新消息和分支承接修订 → 原 start/Worker 生成 → 反馈独立且可选 → 删除先阻断再逐项清理**”解释这一步，就抓住了 STEP07 的主干。
