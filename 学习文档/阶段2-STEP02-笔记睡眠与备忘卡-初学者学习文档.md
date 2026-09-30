# 阶段2 · STEP02 学习文档：笔记、睡眠和备忘卡怎样进入一次对话

> 对应项目步骤：**S2-STEP02「笔记、睡眠及备忘 CRUD」**。本文面向第一次接触版本化记录、消息摘记、单次来源授权和删除闭环的读者，依据[当前实现合同](../PsyEvoAgent项目计划/阶段2/02-技术方案与实施计划.md#s2-step02-implementation)、[验收切片](../PsyEvoAgent项目计划/阶段2/03-测试与验收标准.md#s2-step02-checks)、[执行记录](../PsyEvoAgent项目计划/阶段2/evidence/S2-STEP02/README.md)及当前源码编写。例子中的用户和内容均为合成材料。STEP01 的来源/用途基础可先读[上一篇](阶段2-STEP01-来源用途与证据合同-初学者学习文档.md)。

## 0. 先明确：这一步做成了什么

STEP01 只定义了“来源是谁的、哪一版、能用于什么”。STEP02 把三类本人记录落到了页面、API 和 PostgreSQL：**自由笔记/消息摘记、睡眠记录、支持备忘卡**。用户可自愿从记录页选一条记录带入**下一次发送**；原有 run、独立 Worker 和 Support 图读取它，后续轮次不会自动继承。删除仍走既有 `DeletionJob`：先阻断在线访问，再清理相关内容，可查回执并重试。

这一步的工程验收已于 2026-09-30 完成。它没有加入 LangMem、长期记忆、画像、后台提取 job 或第二个 Worker。页面本身的增删改查不调用模型；只有用户发起带入记录的对话才走原有模型路径。测试中的模型输入捕获使用受控 fake，不是新一次真实 Provider 观察。

## 1. 不懂代码时，先看两条数据流

```text
记录页面：/records、/records/sleep、/me/support-card
  → 表单校验 → 带 Idempotency-Key 的 API 请求
  → 登录身份/owner/expected_version 核对
  → PostgreSQL：notes、note_sources、sleep_records、support_cards
  → 再读服务端记录；失败则保留编辑内容

用户选择一条记录并发送消息
  → 建立会话和 run 草稿 → 建 conversation grant + 记录 grant
  → start run → 独立 Worker 再核来源与版本
  → 原 Support 图收到仅本轮选择的记录上下文
  → 通过输出与提交检查后写入回答 → SSE/快照显示
```

**保存记录**与**把记录交给模型**是两次不同的动作。创建一条睡眠记录不会自动提取长期记忆；在记录页点“带入对话”也只是准备选择，真正的 grant 由下一次发送创建并绑定该 run。

### 1.1 几个容易混淆的对象

| 对象 | 本步含义 | 应记住什么 |
|---|---|---|
| `Note` | 本人的自由笔记或消息摘记 | 自由笔记有正文；摘记引用原消息，`body=null` |
| `NoteSource` | 摘记与消息 ID/版本的关系 | 保留可核对的边，不复制一份永久消息正文 |
| `SleepRecord` | 一个日期及可空的入睡、醒来时间 | 记录时间、发生时间、推导跨度不是一回事 |
| `SupportCard` | 每个 owner 一张支持备忘卡 | 三个文字分区可留空；联系人只是本人备注 |
| `ContextGrant` | 指定 run 的 `current_run` 来源许可 | 记录内容只在该次运行被选入 |
| `DeletionJob` | 持久的阻断、清理和重试回执 | 已不可见与已清理完成是两种状态 |

### 1.2 主要代码位置

| 文件 | 负责什么 |
|---|---|
| [backend/app/records.py](../backend/app/records.py) | 三类记录的字段校验、CRUD、来源解析、单次上下文和记录删除 |
| [backend/app/models.py](../backend/app/models.py) 与 [l012_records](../backend/migrations/versions/l012_records.py) | 表、owner 关系、类型化来源/删除目标外键及追加迁移 |
| [backend/app/api.py](../backend/app/api.py)、[runs.py](../backend/app/runs.py)、[run_worker.py](../backend/app/run_worker.py) | 复用身份、幂等、grant、start、Worker 与提交前复核 |
| [backend/app/history.py](../backend/app/history.py)、[titles.py](../backend/app/titles.py)、[deletion.py](../backend/app/deletion.py) | 排除临时来源派生前文/标题，及删源时阻断关联摘记 |
| [frontend/src/records-page.tsx](../frontend/src/records-page.tsx)、[records-api.ts](../frontend/src/records-api.ts) | 记录页面、表单和返回数据的 Zod 结构 |
| [frontend/src/chat-page.tsx](../frontend/src/chat-page.tsx) | 把所选记录和会话来源分别绑定到同一次 run |

## 2. 完整例子：一条消息怎样变成可核对的摘记

假设合成用户在自己的对话中写过“睡前想把想法记下来”，现在想摘记这条消息，并加上自己的备注“下次先写在纸上”。

### 第一步：从消息入口建立摘记

聊天消息菜单进入记录编辑器，并携带原消息的 ID 和版本。[`POST /api/v1/notes`](../backend/app/records.py) 接收 `kind=linked_excerpt`、`source_refs=[{source_type: message, source_id, source_version}]` 及用户写的 `annotation`；**摘记 `body` 必须是 `null`**。服务端核对消息属于本人、未删除、版本有效、仍在有效分支；助手消息还必须来自已完成的 run。成功后存下 `Note` 和 `NoteSource`，展示时再解析原消息正文。

因此摘记不是“复制原话后永远保存”。如果消息被修订成旧分支、来源撤销或删除，读取时可呈现 `needs_review`，不能继续作为有效模型来源。若只想保存一段独立文字，使用 `kind=free`；它要求非空正文且不能冒充消息引用。

### 第二步：编辑与保存有两层防重

更新使用 `PATCH /api/v1/notes/{id}`，带 `expected_version` 和 `Idempotency-Key`。前者防止两个页面用旧版互相覆盖，后者识别同一次请求的重试。`PATCH` 只合并**实际提供的字段**；省略发生时间与显式传 `null` 的含义不同。合并后的完整对象还要重新校验，不能通过分几次 PATCH 绕开摘记不得复制正文的规则。

如果服务器已经保存，但网页没收到响应，页面可用原键查 `GET /api/v1/record-requests/{key}`，得到本人这次提交的资源引用，再重新读取最新记录；它不会从回执接口取到缓存的私人旧正文。若返回版本冲突，页面保留当前编辑内容，展示最新版供用户核对，不能直接标“保存成功”。

### 第三步：选择记录后才带入一次对话

用户在记录页选择“带入对话”。页面进入聊天，并显示所选记录的类型、ID 和版本。点击发送时，[chat-page.tsx](../frontend/src/chat-page.tsx)依次创建 run 草稿、会话 `current_run` grant、记录 `current_run` grant，再调用原 `POST /api/v1/runs/{run_id}/start`。同一次请求的 `grant_ids` 包含会话与所选记录；没有选中的其他笔记不在其中。

Worker 领取任务后，[records.py 的 `record_context()`](../backend/app/records.py)按有效 grant 解析记录，把类型、ID、版本与允许字段加入 Support 输入，并明确把记录文本当资料而非系统指令。来源在创建、读取、调用及提交时都要重新核对；选中后若版本变化、被撤销或删除，旧 grant 不能让迟到回答发布。记录输入纳入原 token 预算，超出预算就停止，而不是偷偷截出一段新“版本”。

回答完成后，grant 不再对后续 run 有效。[历史上下文](../backend/app/history.py)排除带临时记录 grant 的上一轮派生回答，[自动标题](../backend/app/titles.py)也不把这一轮变成持续保存的标题来源。用户若想在下一轮使用记录，需要再次明确选择。

## 3. 睡眠记录：未知就保留未知

[`SleepInput`](../backend/app/records.py)把 `entry_date` 单独保存，不拿 `created_at` 代替用户所记的日期。`bed_at`、`wake_at` 和 `interruptions` 可以为 `null`；没有写醒来时间，就没有完整跨度。两个时间都填写时必须是带 UTC 偏移的完整时间，并与 IANA 时区一致；服务器拒绝不存在的夏令时时刻、错误偏移及醒来不晚于入睡的组合。

例如 `entry_date=2026-09-29`，入睡 `2026-09-29T23:30:00+08:00`，醒来 `2026-09-30T07:00:00+08:00`，时区为 `Asia/Shanghai`，可推导出两时刻之间的跨度。**跨度不是实际睡眠时长，也不是健康评分**。若只记得入睡、不记得醒来，就让 `wake_at=null`、`span_minutes=null`；页面和服务端都不能补一个常见的 07:00。午睡、跨日、未知起止与时区反例在本步测试中分别检查。

`PATCH /api/v1/sleep-records/{id}` 同样使用版本和幂等键。只改“感受”不会抹掉未提供的时间字段；显式清空时间才传 `null`。服务端校验合并后的完整记录，防止已有时间在改时区后变成非法组合。

## 4. 支持备忘卡：自愿填写、冲突可核对

`GET /api/v1/support-card` 返回本人的单张卡；首次 `PUT` 使用 `expected_version=0`。三个分区分别是 `helpful_methods`（有帮助的方法）、`self_reminders`（给自己的提醒）和 `contact_notes`（愿意主动联系的人或渠道）。可以全空或只写一项，没有强制联系人，也不会自动联系任何人。

每次保存递增版本，并保留最近一次保存的三个文字分区及版本作为旧版对照。两个标签页同时编辑时，先保存的一页改变版本，后到的旧版本收到 409；页面保留未提交文字，并把最新版和旧版显示给用户比较。清空要经过确认流程，清除正文和旧版文字，但保留同一张卡的 ID 与递增版本；未完成删除处理时不能趁空档重新写入。

`resource_refs` 需要实际可核实的公共资源。目前接口没有已核实条目，所以非空引用写入被拒绝；已有失效引用只显示需核对或不可用状态，页面不会编造建议。这张卡仍可只用本人文字正常保存。

## 5. 数据库为什么要有类型化外键

[l012_records 迁移](../backend/migrations/versions/l012_records.py)追加 `notes`、`note_sources`、`sleep_records`、`support_cards`，并扩展原有 `context_grants` 与 `deletion_jobs`。这不是另建一套账号或 run 系统。各表沿用 `owner_id`、版本和共同封套；`note_sources` 把摘记与本人消息用组合 owner 关系连起来。

`ContextGrant` 仍有 `source_type` 和 `source_id`，但数据库按类型生成 `conversation_source_id`、`note_source_id`、`sleep_source_id`、`card_source_id` 等列，每类对应真实目标和 owner 复合外键；`DeletionJob` 对目标也采用同样思路。这样“声称 type 是 note，ID 却指向别人的会话”不能只靠应用层字符串侥幸通过。旧的阶段1行和约束继续保留，迁移不批量伪造新 grant；已有记录时降级拒绝丢弃正文。

## 6. 删除：先阻断关联，再逐项清理

三类记录的删除请求都要求明确 `confirmed=true`、当前 `expected_version` 和幂等键。服务端先在事务中标记来源删除，终止受影响的 run，阻断关联摘记的读取，然后提交 `DeletionJob` 的 `online_blocked` 状态；之后按步骤清理正文、事件、反馈和引用。清理中断仍不可重新读取，回执列明完成和待处理项，可按原任务重试。

删除整个会话时，`GET /api/v1/sessions/{id}/deletion-preview` 会列出受影响的消息摘记。源消息删除或修订也会让相应摘记失效；与该会话无关的自由笔记不跟着删除。为支持核对与重试，可保留无正文的 ID/版本关系、幂等哈希和用量元数据；这些不是恢复被删原文的副本。外部删除状态按实际模型调用收据表示，不能把“没有调用”写成“外部已删除”。

## 7. 页面、接口与事实各归谁管

| 位置 | 负责的事 | 不应代替的事 |
|---|---|---|
| [records-page.tsx](../frontend/src/records-page.tsx) | 列表/详情、草稿编辑、选择记录、冲突和确认交互 | 不以浏览器本地状态当保存成功 |
| [records-api.ts](../frontend/src/records-api.ts) | 用 Zod 检查 API 返回的笔记、睡眠和卡片结构 | 不替服务端授予 owner 或 grant |
| [records.py](../backend/app/records.py) | 校验、本人 CRUD、摘记解析、记录上下文、删除入口 | 不运行长期记忆或画像提取 |
| [runs.py](../backend/app/runs.py) 与 [run_worker.py](../backend/app/run_worker.py) | 冻结 run 输入、预算、执行与发布复核 | 不自动把所有记录纳入上下文 |
| PostgreSQL | 保存版本、关系、幂等与删除处理事实 | 不用页面缓存推断最终状态 |

记录页桌面采用列表/详情，窄屏先列表后详情；备忘卡保持三个自愿分区。项目已有的 Tailwind 主题、TanStack Start/Router、Query、Form + Zod 和组件库交互继续复用；新增的 [Input 组件](../frontend/src/components/ui/input.tsx)有实际表单消费者。编辑中离开页面有放弃确认，失败时文字留在表单，删除后相关私人缓存失效并通知其他标签页。这些体验规则配合服务端事实，不能取代 owner、版本和来源检查。

## 8. 测试与证据各自证明什么

| 入口 | 主要验证 |
|---|---|
| [backend/tests/test_records.py](../backend/tests/test_records.py) | 三类记录、跨 owner、版本/幂等、时区与夏令时、摘记来源、当次 grant 和删除 |
| [frontend/tests/records.spec.ts](../frontend/tests/records.spec.ts) | 真实页面的保存重试、冲突、窄屏、卡片清空、摘记带入与删源预览 |
| [scripts/check_step03.py](../scripts/check_step03.py) 的 `--s2-step02` | 随机隔离 PostgreSQL、API/迁移、后端、前端、浏览器及数据库真实重启核对 |
| [本步执行记录](../PsyEvoAgent项目计划/阶段2/evidence/S2-STEP02/README.md) | 门禁输出、指纹、截图和明确的未验证范围 |

最终记录为 **143 项 PostgreSQL/API/迁移、188 项后端、41 项浏览器**通过，另有前端 `check`/`build`、迁移无漂移及重启前后六表行数/哈希一致。143 项中包括 26 项记录场景和 1 项记录迁移保留测试；浏览器中 6 条为本步新旅程、35 条为既有回归。受控模型捕获证明所选记录 ID、版本及内容实际进入 Support 输入，未选记录没有进入。它证明这条受控工程路径，不证明真实 Provider、SMTP、远程发布、长期记忆或专业内容评价。

学习时可只读[现成证据](../PsyEvoAgent项目计划/阶段2/evidence/S2-STEP02/README.md)。如需重新跑完整门禁，先按[DEVELOPMENT.md](../DEVELOPMENT.md)核对本机依赖和隔离环境；脚本会启动测试数据库与浏览器，不应对开发数据库做破坏性重置。

## 9. 用几个失败场景检查自己是否理解

### 场景 A：保存成功但响应丢失

页面先显示未确认，保留同次尝试的幂等键；查询 `record-requests` 并重新读取资源。不能因网络报错再用新键写第二条，也不能只凭按钮点击推断保存失败。

### 场景 B：用户选中摘记后修订了原消息

旧摘记的消息版本已失效，应显示需核对并拒绝继续带入模型。用户自写的 annotation 不能把失效原文变成新来源。

### 场景 C：两个标签页同时改备忘卡

一页成功后版本递增，另一页旧 `expected_version` 返回 409。后者保留编辑内容、展示最新版本，由用户核对后再保存。

### 场景 D：只知道睡眠日期，不知道醒来时间

保留 `wake_at=null` 和 `span_minutes=null`。不能根据常见作息、创建时间或时区补一个看似合理的醒来时刻。

### 场景 E：带入记录的 run 完成后再发一轮

前一轮的临时记录 grant 已结束；自动前文与标题不能让它借助手回答继续传播。新一轮要再次由用户选择来源。

### 场景 F：删源后清理消息事件失败

来源和关联摘记仍不可见，`DeletionJob` 保留待处理步骤并可重试。不能把“在线已阻断”显示为“全部清理完成”，也不能为了重试而恢复读取。

## 10. 建议的学习顺序与自测

1. 先在[records-page.tsx](../frontend/src/records-page.tsx)找笔记、睡眠、备忘卡的保存和错误展示，再看[records-api.ts](../frontend/src/records-api.ts)的返回结构。
2. 看[records.py](../backend/app/records.py)的 `NoteInput`、`SleepInput`、`dto()`、`mutation_receipt()` 和三类接口，分清正文、引用与未知字段。
3. 沿[chat-page.tsx](../frontend/src/chat-page.tsx)的发送路径到[api.py](../backend/app/api.py)的 `create_grant()`、[runs.py](../backend/app/runs.py)的 `start_run()`，最后看[run_worker.py](../backend/app/run_worker.py)如何调用 `record_context()`。
4. 对照[迁移](../backend/migrations/versions/l012_records.py)和[删除代码](../backend/app/deletion.py)，解释为什么要有 owner 复合外键、先阻断和可重试回执。
5. 最后读[测试](../backend/tests/test_records.py)与[执行记录](../PsyEvoAgent项目计划/阶段2/evidence/S2-STEP02/README.md)，分清受控输入捕获与真实模型观察。

自测时回答：为什么摘记正文必须为 `null`？为何 `Idempotency-Key` 和 `expected_version` 要同时存在？跨日跨度为何不能叫睡眠时长？记录 grant 为什么只服务本轮？源删除时怎样保证摘记不会在清理失败期间重新出现？能用“**本人记录保存 → 精确选版带入 → 运行中反复核源 → 下一轮不继承 → 删源先阻断再清理**”解释这些问题，就掌握了 STEP02 的主干。
