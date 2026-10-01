# 阶段2 · STEP03 学习文档：后台任务怎样在 Worker 崩溃后继续完成

> 对应项目步骤：**S2-STEP03「持久 job 与 Worker 恢复」**。本文面向第一次接触数据库任务、租约、重试预算和崩溃恢复的读者，依据[当前实现合同](../PsyEvoAgent项目计划/阶段2/02-技术方案与实施计划.md#s2-step03-implementation)、[本步验收范围](../PsyEvoAgent项目计划/阶段2/03-测试与验收标准.md#s2-step03-checks)、[执行记录](../PsyEvoAgent项目计划/阶段2/evidence/S2-STEP03/README.md)、[后续审查修复](../PsyEvoAgent项目计划/阶段2/evidence/S2-STEP03/review-repairs.md)及当前源码编写。例子中的用户、笔记和任务均为合成材料。记录与单次来源授权的基础可先读[上一篇](阶段2-STEP02-笔记睡眠与备忘卡-初学者学习文档.md)。

## 0. 先明确：这一步做成了什么

STEP02 已能保存笔记、睡眠和支持备忘卡，并把用户选定的记录带入一次对话。STEP03 为后续后台处理补上另一项基础：**任务与预算保存在 PostgreSQL，独立 Worker 领取执行；进程崩溃后，新进程能从原账本恢复，同时拒绝旧执行者的迟到结果**。

这一步的工程验收已于 2026-09-30 完成，随后又完成两项审查修复。当前实际消费者只有 `recovery_probe`，即专门验证恢复机制的合成探针。它读取获准的记录，调用现有 LangChain fake，校验返回结构，再写一条无正文结果回执。普通开发保存记录不会自动入队，原有聊天/标题 Worker 也不会自动消费这些任务。

因此，读到 `purpose=candidate_extraction` 时，应理解为已建立这一用途的 **job 授权范围**。LangMem、正式候选和记忆保存仍由 STEP04 实现；本步没有新增 Agent、依赖或前端页面，也没有执行新的真实 Provider 调用。三项原子动作分别落实了领取与续租（S2-STEP03.1）、重试/取消/迟到校验（.2）和真实进程崩溃注入（.3）。

## 1. 不懂代码时，先看任务与执行者怎样分工

```text
隔离测试服务：明确选择本人来源 ID 和版本
  → 同一事务保存 background_jobs、job_budgets 和 job 范围 grant
  → 独立 app.worker --jobs-probe 扫描数据库
  → 短事务领取任务，取得 worker_id / generation / lease_token
  → 核源并读取 → 持久预占调用预算 → 续租并调用 fake
  → 校验输出 → 同一事务写结果回执、结算预算、标记 succeeded

如果进程崩溃：任务、租约和预算仍在数据库
  → 新 Worker 扫描过期租约 → 有界退避 → 取得新租约
  → 再核来源与剩余预算；已成功的任务不重新领取
```

`job` 是需要完成的工作，`Worker` 是暂时执行它的进程。进程退出不意味着工作记录消失；进程还活着也不意味着它一直有权提交。PostgreSQL 保存可核对的状态，Worker 每次关键操作都必须证明自己仍是有效执行者。

### 1.1 几个容易混淆的字段

| 名称 | 本步含义 | 应记住什么 |
|---|---|---|
| `source_version` / `grant_version` | 原记录与来源许可各自的版本 | 记录改版或 grant 撤销后，旧绑定不能继续读取 |
| `generation` | 同一 owner、任务种类和来源集合的第几代工作 | 新一代使在途旧代失效，但继承预算与累计 attempt |
| `attempt` | 已领取执行的累计次数 | 领取时增加；它与模型调用次数不是同一个计数 |
| `lease_owner` | 当前领取任务的 Worker ID | 标识进程，不能代替用户的 `owner_id` |
| `lease_token` | 每次重新领取递增的租约编号 | 旧 token 不能续租或提交；正常续租不改变 token |
| `lease_until` | 当前执行者的租约到期时刻 | 用 PostgreSQL 时钟判断，过期后不能自行续回来 |
| `version` | job 行的乐观版本 | 状态或续租等修改会递增；取消请求用 `expected_version` 核对 |
| `budget_ref` / `deadline_at` | 任务谱系共用的预算账本与绝对截止时间 | 重试、换进程、换代均不能清零或延长 |

“任务谱系”指同一来源集合的一代代任务，共用一份预算账本。租约和 deadline 限制的是**执行**，并不是私人记录的业务 TTL，也不会在到期时自动删除笔记。

### 1.2 主要代码位置

| 文件 | 负责什么 |
|---|---|
| [backend/app/jobs.py](../backend/app/jobs.py) | 原子入队、来源准入、领取、租约核验、续租、预算、结果事务和状态 API |
| [backend/app/job_worker.py](../backend/app/job_worker.py) | 合成消费者、fake 调用、输出校验、调用期间续租及结果回执 |
| [backend/app/worker.py](../backend/app/worker.py) | 原独立 Worker 入口，显式选择 `--jobs-probe` 模式 |
| [backend/app/models.py](../backend/app/models.py) 与 [m013_background_jobs](../backend/migrations/versions/m013_background_jobs.py) | job/budget 表、互斥 run/job grant 及 owner 外键 |
| [backend/app/records.py](../backend/app/records.py) 与 [history.py](../backend/app/history.py) | 复用记录来源校验，兼容 job grant 后的聊天历史筛选 |
| [backend/tests/test_jobs.py](../backend/tests/test_jobs.py) | 并发、失效、预算、真实强杀、数据库中断和审查修复回归 |

## 2. 完整例子：一条笔记怎样成为可恢复的测试任务

假设合成用户甲有一条已保存的自由笔记，第 1 版内容是“睡前先把明天的事写下来”。下面演示的是隔离测试服务调用内部函数，当前页面没有“运行恢复探针”按钮，也没有公共入队接口。

### 第一步：把来源、grant 和任务一起保存

测试服务在数据库事务中调用 [jobs.py 的 `enqueue()`](../backend/app/jobs.py)，提供本人 owner 及笔记的类型、ID、版本。服务检查来源属于本人、当前可用，再建立 `BackgroundJob`、预算账本和 `ContextGrant`。job 保存结构化 `source_refs`，包括 `purpose`、grant ID 和 grant 版本；笔记正文仍由原记录表负责保存。

三者使用同一个事务。若调用方在保存后、提交前失败，新来源修改、grant 和任务一起回滚，不留下“任务已经入队，来源却不存在”的半成品。grant 沿用原有来源许可对象，不伪造用户同意记录，也不把上次聊天的 `current_run` grant 改作后台用途。

任务按 `owner/kind/来源集合/generation` 唯一。来源集合按类型和 ID 排序后计算标识，因此重复通知不会因为顺序不同另建任务。同代、同来源版本返回原任务；同代改了来源版本则冲突。下一代必须连续增加：建立第 2 代会使活动中的第 1 代 `invalidated`，并沿用原预算、deadline、重试上限和累计 attempt。

### 第二步：领取短租约，再读取来源

Worker A 扫描到这条 `queued` 任务。它按既有 owner 锁顺序在短事务中领取，写入 `running`、`attempt=1`、`lease_token=1`、自己的 Worker ID 和到期时间。默认租约为 5 秒，且不能超过任务 deadline；领取事务随即结束，不在模型等待期间一直持有数据库锁。

随后 `execute()` 使用 `fenced()` 再核任务、来源和 grant，才通过原记录解析器读取正文。这里的 `fenced` 可理解为“检查旧执行者是否已被挡在外面”：Worker ID、token、generation、租约、状态、来源和配置版本都必须仍然匹配。

### 第三步：先预占预算，再调用 fake

Worker 把获准记录编码为输入，在真正调用前持久保存预算预占，成功后再次续租核验。探针使用现有 `FakeMessagesListChatModel`，返回类似下面的完整测试结构：

```json
{
  "probe": "recovery-probe/1",
  "source_count": 1
}
```

`ProbeCandidate` 校验标识、整数范围和来源数量是否一致，还核对返回 usage 的计数关系。这里的名字虽然含有 Candidate，保存结果仍只是恢复测试回执，不是记忆候选。模型等待期间，Worker 持续尝试续租；续租失败会停止在途 fake 调用，不继续走结果提交。

### 第四步：把结果和成功状态一起提交

`complete()` 先核租约与调用预占，再在同一事务中执行结果回调、结算预算、设置 `result_ref` 并标记 `succeeded`。结果回调写入之后、事务提交之前还要再次核验；若已经跨越租约或 deadline，结果写入回滚。

当前 `commit_probe()` 复用原 `Idempotency` 表，以本人 owner 与 `job-probe:<job_id>` 为键记录结果类型、任务 ID 和请求哈希。恢复时以数据库终态为准：成功任务不再领取；复用已有回执时也必须核对其实际内容，不能只看“这个键存在”。

## 3. 租约：让新 Worker 接手，同时挡住旧 Worker

租约像一张有时限、带编号的执行凭条。假设 A 领取后卡住，数据库中的租约过期，新 Worker B 会先把该任务转为 `retry_wait`；退避结束后再领取，attempt 和 token 递增。A 后来恢复时，即使手里仍有旧任务 ID，也无法凭旧 token 续租、预占、提交或修改失败状态。

这里有三个分别起作用的限制。**owner 锁**保护短事务之间的状态修改顺序；**租约 token**区分新旧执行者；**grant 与来源检查**决定资料现在是否还能被使用。拥有未到期租约不等于拥有永久来源权限：用户撤销 grant、修改或删除笔记，新 generation 出现，或实验配置版本改变，都可能在下次领取、续租或提交核验时使任务失效。

所有到期判断使用 PostgreSQL 的 `clock_timestamp()`。它反映当前实际时间，适合发现事务执行期间已经到期的租约；不能只依据 Worker 本机时钟或事务开始时的时间决定是否仍能写结果。正常执行超过最初 5 秒并不必然失败，只要续租一直有效且尚未到达绝对 deadline，就仍可完成。

## 4. 预算：崩溃之后也不能重新得到一份额度

[JobBudget](../backend/app/models.py)复用原 [Support 的 `Budget`](../backend/app/support.py)限额结构，把限额、截止时间和每次调用的预占存入 PostgreSQL。`reserve()` 先检查累计调用数和已计入的 token，再保存 request ID、job/generation/token/attempt、预占量与状态；通过后才允许调用模型。

| 情况 | 账本如何处理 |
|---|---|
| 调用完成且 usage 合法、可知 | 成功事务中按实际 token 结算 |
| 调用完成但 usage 缺失 | 记为 `usage_unknown`，仍计全额预占 |
| 调用后、提交前崩溃 | 旧项仍为 `reserved`，实际用量未知，继续占用原额度 |
| 新 Worker 重试或建立下一代 | 读取同一账本，保留所有历史调用和预占 |
| 调用数、token 或 deadline 耗尽 | 停止任务，不能靠换进程或换代重置 |

例如测试中，第 1 代已预占 5000 token，建立第 2 代后再申请 4000，而默认总上限为 8192，就必须以 `budget_exhausted` 停止。不能因为旧进程没回报实际用量，就把那 5000 当成没有发生。

也要分清 **attempt 上限**与**调用上限**。领取后、调用前崩溃会消耗一次 attempt，却可能还没有调用预占；调用后的崩溃则两者都有记录。入队默认最多 3 次 attempt，可配置范围为 1～5；当前复用的 Budget 默认最多 2 次调用。这些限制同时成立，未到重试上限也可能先耗尽调用预算。

本步 fake 成本明确为 0，账本货币标识为 `SYNTHETIC`。输入字节长度加余量用于测试预占，不能把它当作真实 Provider tokenizer 或账单。真实 usage、费用及父 run/experiment 预算联动，需要后续真实消费者另行接入验证。

## 5. 重试与取消：失败原因决定能否再做

`retry_wait` 表示等待下一次有界尝试，`failed` 表示本任务不能继续自动执行。当前只有 `temporary_io`、`timeout` 和 `lease_lost` 三类瞬态原因进入重试，使用指数退避附小幅随机抖动，并同时受 attempt 与绝对 deadline 限制。参数、schema、权限、删除和 `unknown_mutation` 不自动重发；未知异常仅保存有限的 `execution_error`，不把异常原文或私人资料写入失败状态。

| 状态 | 含义 | 后续行为 |
|---|---|---|
| `queued` | 已持久保存，等待领取 | 合格且可用时领取 |
| `running` | 已领取，持有人和租约记录在库 | 仍须核对租约有效性；过期后由扫描处理 |
| `retry_wait` | 瞬态失败或丢租后等待 | 退避结束并通过检查后再领取 |
| `succeeded` | 结果与终态已合法提交 | 不重新执行 |
| `failed` | 不可重试错误或执行限制耗尽 | 不自动重试 |
| `cancelled` | 本人取消了活动任务 | 阻止后续读取、调用和提交 |
| `invalidated` | 来源、grant、配置或代次等已失效 | 旧执行不能继续 |

取消接口要求 `expected_version`。首次取消活动任务时核版本并保存 `cancelled`；重复取消返回同一状态。若合法结果已先提交，取消不会撤掉既有结果。取消与执行谁先取得 owner 锁并完成事务，决定可核对的结果，不能仅凭网页先点了按钮断言服务端已取消。

Worker 连续遇到数据库错误时，最多累计 3 次后以脱敏错误退出；重启仍读取原账本。若错误发生在结果事务附近，进程不能直接把“没有收到成功响应”当成“肯定没有提交”，更不能在当前进程中盲目重放未知结果写入。

## 6. 三个真实崩溃点为什么都要测

[测试](../backend/tests/test_jobs.py)启动真实独立 Worker 子进程，让它在指定阶段暂停，再强制杀死，随后启动一个全新的进程扫描恢复。数据库和进程终止都是真实动作，模型部分仍是受控 fake。三个位置覆盖了不同的持久事实：

| 强杀点 | 崩溃时已保存什么 | 恢复后的实际结果 |
|---|---|---|
| `after_claim`：领取后 | attempt/token 与租约；尚无调用预占 | 租约过期后接手，attempt/token 从 1 到 2；最终一条调用记录、一条结果回执 |
| `before_commit`：结果事务前 | 调用预占；fake 已返回，但结果尚未提交 | 新租约再执行，attempt/token 从 1 到 2；两条调用记录，旧预占仍未知；结果回执只有一条 |
| `after_commit`：结果事务提交后 | 结果、预算结算与 `succeeded` | 新进程不再领取；attempt/token 保持 1/1，调用和结果各一条 |

这证明的是**允许必要的执行重试，但已提交副作用不重复写入**。提交前崩溃的场景实际调用了两次 fake，所以不能把“一条结果回执”解释为“模型一定只调用一次”。未来即使接真实 Provider，这套本地事务也不能单独证明外部调用只发生一次。

另一个测试在结果事务里终止当前真实 PostgreSQL 连接，确认尚未提交的结果回执回滚；还有超过初始租约的续租、运行中撤销、旧 token 和事务内到期等反例。它们分别核对“执行者还能继续吗”和“副作用确实提交了吗”，不是只捕获一个 Python 异常就算恢复通过。

## 7. 数据库与原系统怎样接在一起

[m013_background_jobs](../backend/migrations/versions/m013_background_jobs.py)在 `l012_records` 之后追加 `background_jobs`、`job_budgets`，并给原 `ContextGrant` 增加 `job_id`。数据库 CHECK 将两个执行范围分开：

| grant 用途 | 必须有 | 必须为空 |
|---|---|---|
| `current_run` | `run_id` | `job_id` |
| `candidate_extraction` | `job_id` | `run_id` |

原 typed 来源外键继续存在，job 与 budget、grant 与 job 都有 owner 复合外键。这样不能把甲的任务指向乙的预算或来源，也不能同时给一个 grant 填 run 和 job 范围。公网创建 grant 的接口仍只接受已实现的 `current_run` 请求；后台范围由受限的内部入队服务建立。迁移保留原账号、记录与运行事实，已有 job 或预算时拒绝丢失性降级。

### 7.1 一个可空字段为什么会影响聊天历史

新增 job grant 的 `run_id=null` 曾触发旧历史筛选的 SQL 问题。原查询用 `NOT IN` 排除带临时记录 grant 的 run；子查询混入 NULL 后，普通 run 的比较也可能变成 unknown，被 WHERE 排除。结果是正常多轮聊天的前文一起消失。

当前 [context_history()](../backend/app/history.py)改用相关联的 `NOT EXISTS`：针对正在筛选的每个历史 Run，只检查是否存在 `run_id` 与它相等、`purpose=current_run` 且来源不是 conversation 的 grant。这样继续排除临时记录产生的上一轮回答，job grant 的 NULL 则不影响正常前文。新增回归验证了“有 job grant 时，正常聊天历史仍然可用”。

### 7.2 后续审查又修了哪两件事

第一件是**被锁住的一批任务不应挡住其他账号**。`claim()` 每批最多取 100 个候选，按 owner 锁配合 `FOR UPDATE SKIP LOCKED` 跳过争用。修复前如果前 100 个都属于被锁的账号，扫描可能直接返回空闲；当前以 `(available_at, job_id)` 为游标继续后面的批次，直到领到任务或候选耗尽。游标包含 ID，可区分相同可用时间；不用 OFFSET，也避免前面的任务离开活动队列后漏掉后续项。

第二件是**共享幂等表中的同键回执必须属于这次结果**。如果笔记 API 恰好使用了 `job-probe:<job_id>`，仅判断键存在会误把笔记回执当作任务成功。当前 `commit_probe()` 只有在 `resource_type=job_probe`、`resource_id=当前 job`、`request_hash=digest(job.id)` 全部相符时才复用；冲突沿 schema 失败分支停止，原笔记回执仍可正常重放。

这两项修复新增 7 项参数化回归，包括锁住前 100/201 个候选、不同回执字段不匹配，以及完全匹配的合法复用。修复范围与专项收据见[独立审查记录](../PsyEvoAgent项目计划/阶段2/evidence/S2-STEP03/review-repairs.md)。

## 8. 页面、API 与消费者各归谁管

本步没有新增前端页面，已有学生端入口保持原实现。新 API 只让已登录用户查看或取消本人的任务：

| 接口/入口 | 实际职责 |
|---|---|
| `GET /api/v1/jobs` | 各状态计数、最大 attempt、租约丢失数和最老等待秒数 |
| `GET /api/v1/jobs/{id}` | 返回无正文状态、版本、执行次数、租约及结果/预算引用 |
| `POST /api/v1/jobs/{id}/cancel` | 沿原身份、Origin/CSRF、owner 锁及版本规则取消 |
| 内部 `enqueue()` | 仅在明确的隔离 test/fake 装配中建立合成任务 |
| `app.worker --jobs-probe` | 独立进程扫描和执行探针，API import/reload 不启动消费者 |

跨 owner 的任务详情与取消返回 404，统计只包含本人任务。任务 API 和错误状态不返回笔记正文、prompt 或模型回答；`result_ref` 指向无正文测试回执，不能拿它当长期记忆详情接口。

`--jobs-probe` 与原 `--support` 必须分开调用。探针要求显式 test/fake 配置和合格的隔离数据库，拒绝 development/live 装配，不加载真实模型配置文件。普通本地启动仍按已有规则管理聊天与标题 Worker；未来 STEP04 应复用本步任务、来源、预算和提交事务，再接入真正的提取消费者。

## 9. 测试与证据各自证明什么

| 入口 | 主要验证 |
|---|---|
| [test_job_contracts.py](../backend/tests/test_job_contracts.py) | 无数据库检查：探针装配限制、来源结构拒绝正文和未开放用途 |
| [test_jobs.py](../backend/tests/test_jobs.py) | 真实 PG/API：原子入队、并发、租约、失效、重试、取消、预算、结果事务与强杀恢复 |
| [test_step03_migrations.py](../backend/tests/test_step03_migrations.py) | 追加迁移、历史数据保留与降级限制 |
| [jobs_receipt.py](../backend/tests/jobs_receipt.py) | 数据库重启前后 job、budget、job grant 和结果表的数量与哈希 |
| [scripts/check_step03.py](../scripts/check_step03.py) 的 `--s2-step03` | 复用隔离 PostgreSQL、API、后端、前端、浏览器及真实数据库重启门禁 |

完整实施门禁与后续专项修复是两个时点，阅读时分别核对：

| 执行时点 | 实际结果 | 结论范围 |
|---|---|---|
| [STEP03 完整实施门禁](../PsyEvoAgent项目计划/阶段2/evidence/S2-STEP03/README.md) | 180 项 PG/API/迁移、190 项后端、49 项浏览器通过；前端 check/build、三个真实强杀点及 PG 重启指纹通过 | 当时完整工程快照；180 项含 29 项 job、1 项新增迁移与上一步 150 项回归 |
| [后续审查修复专项](../PsyEvoAgent项目计划/阶段2/evidence/S2-STEP03/review-repairs.md) | 69 项 PG job/记录通过（36 项 job、33 项记录）；190 项后端、三个强杀点、迁移与静态检查通过 | 修复后的专项结果；未重跑浏览器、真实 PG 重启或 WSL 门禁 |

完整门禁的数据库重启前后，30 条 job、28 条预算、30 条 job grant 和 6 条结果回执的数量与哈希一致。它证明当时在线数据库的持久事实能经重启保留，不等于应用备份恢复或持久 checkpointer 验收。49 条浏览器用于验证原聊天、记录等功能的兼容性，没有新 job 页面旅程。

首轮完整门禁曾真实出现 172 通过、7 失败，保留在执行记录中；它推动了 NULL 历史筛选修复。另一轮在总时限内未完成，明确记录为超时失败。不能把过程中的进度、未见断言错误或旧收据算作新一轮通过，也不能把后续专项数字加到完整门禁上当成一次结果。

学习时可直接阅读上述证据。如需自行重跑完整门禁，先按 [DEVELOPMENT.md](../DEVELOPMENT.md)准备锁定依赖、Chromium、指定 PostgreSQL 镜像和空闲端口，再在仓库根目录执行：

```powershell
backend/.venv/Scripts/python.exe -X utf8 scripts/check_step03.py --s2-step03 --web-port 3199 --api-port 8199 --tls-port 3499
```

脚本使用随机独立测试容器、合成账号和 fake，产生新的 `.artifacts/psyevo-step07-*/receipt.json`；目录沿用原检查器命名，收据里的 `step_id` 才是 `S2-STEP03`。该命令会真实启动测试服务、杀死测试 Worker 并重启测试数据库，不应用开发数据库替代。本文编写仅核对已有实现与证据，不代表重新执行了这套门禁。

本步通过的是 S2-A09/S2-A10 的**任务恢复范围**；父用例中的 LangMem 兼容、正式候选保存及真实提取仍待 STEP04。真实 Provider 计费、外部取消/删除、专业心理效果、公共安全分块、远程发布和 WSL 内核隔离都不能由本步 fake 恢复结果推定。

## 10. 用几个失败场景检查自己是否理解

### 场景 A：旧 Worker 过期，新 Worker 已领取，旧进程又恢复

旧 token 不能再续租、预占或提交。任务 ID 相同、旧进程持有模型结果，都不能覆盖数据库中的新执行资格。

### 场景 B：笔记第 1 版已入队，用户改成第 2 版

旧 job 绑定的来源版本失效，在下次关键核验时停止。它不能自动改用新版继续；若明确建立下一代，仍须继承原预算和 deadline。

### 场景 C：fake 已返回，进程在结果提交前被杀

结果尚未保存，但旧调用预占仍存在且实际用量未知。新进程只有在剩余额度允许时才能重试，不能先把旧预占清零。

### 场景 D：成功事务已提交，响应丢失或进程马上退出

先核数据库中的 `succeeded` 与结果回执；新进程不会重新领取已成功任务。未收到响应不能作为再次写入的依据。

### 场景 E：模型返回错误结构，或者提交状态无法确定

schema 与未知 mutation 不属于可自动重发的瞬态错误。先按有限错误状态或数据库事实处理，不能把所有异常都归类为“再试一次”。

### 场景 F：队列前 201 条都属于被锁的账号

按游标继续扫描，后面的另一账号任务仍可领取；锁住的候选保持原等待状态。没有领到第一批不等于整个队列没有可做的任务。

### 场景 G：同一个幂等键已经对应一条笔记

探针应失败且保留原笔记回执。只有类型、任务 ID 和哈希都一致，才是合法的结果复用；同键不是同业务的充分证据。

## 11. 建议的学习顺序与自测

1. 先读[当前合同](../PsyEvoAgent项目计划/阶段2/02-技术方案与实施计划.md#s2-step03-implementation)，分清本步恢复探针与 STEP04 真实提取。
2. 在 [models.py](../backend/app/models.py) 和[迁移](../backend/migrations/versions/m013_background_jobs.py)中找 `BackgroundJob`、`JobBudget` 与 grant 范围 CHECK，解释每个 owner 外键保护了什么。
3. 沿 [jobs.py](../backend/app/jobs.py) 的 `enqueue()` → `claim()` → `fenced()`/`renew()` → `reserve()` → `complete()` 读一遍正常路径，再看 `retry()`、`fail()` 和 `cancel_job()`。
4. 看 [job_worker.py](../backend/app/job_worker.py) 的 `execute()` 与 `commit_probe()`，找出读取来源、预占、调用期间续租、输出校验和事务提交各发生在哪里。
5. 对照[测试](../backend/tests/test_jobs.py)的三个 `test_real_killed_worker_recovers_once` 参数场景，再读[完整证据](../PsyEvoAgent项目计划/阶段2/evidence/S2-STEP03/README.md)与[审查修复](../PsyEvoAgent项目计划/阶段2/evidence/S2-STEP03/review-repairs.md)，核对调用次数、结果数量和验证时点。

自测时回答：为什么租约不能代替来源 grant？`generation`、`lease_token` 和 `version` 各挡住哪种旧操作？为什么领取后崩溃与调用后崩溃消耗的预算不同？为什么一条结果回执不等于只调用一次模型？为什么新一代不能获得新预算？为什么 job grant 的 NULL 会要求修改历史查询？能用“**同事务入队 → 带租约执行 → 调用前持久预占 → 提交时再次核验 → 崩溃后按原账本恢复**”解释这些问题，就掌握了 STEP03 的主干。
