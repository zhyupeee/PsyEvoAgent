# 阶段1 · STEP08 学习文档：真实模型怎样接入整稿对话

> 对应项目步骤：**S1-STEP08「全阶段联调及交接」**。本文面向第一次接触模型 Provider、内部流、预算账本和网页联调的读者，依据当前源码、[真实模型接入合同](../PsyEvoAgent项目计划/阶段1/02-技术方案与实施计划.md#live-model-integration)、[验收补充](../PsyEvoAgent项目计划/阶段1/03-测试与验收标准.md#live-model-acceptance)及[STEP08 续作证据](../PsyEvoAgent项目计划/阶段1/evidence/S1-STEP08/continuation.md)编写。文中的账号和输入均为合成示例。下文描述的是 **2026-09-27 已实现并验证的 STEP08.1 局部工程结果**，不是整个 STEP08 的完成声明。

## 0. 先明确：这一步做成了什么

STEP05～07 已经有登录、草稿、run、独立 Worker、SSE、历史和删除，但对话生成使用隔离的 fake 模型。本轮先用固定合成输入验证真实模型的**内部流**，再让原有网页、API 和 Worker 通过同一张 Support 图调用它。实际网页旅程验证了发送、回答、SSE 与快照一致、刷新不重复调用、跨账号拒绝、取消和确认删除。

当前公开回答仍走**整稿检查**：模型可以在内部逐块返回，网页却要等完整回答通过结构、用量和输出规则检查后，才收到一条 `message.delta`。这能解释为什么“Provider 支持 stream”不等于“用户已经看到安全的逐块回答”。可靠的安全分块准入与跨块检查尚未实现；专业支持内容审阅、真实 SMTP、STEP08.2～.4 的验收矩阵及交接冻结也未完成。因此 STEP08 整体仍为 **BLOCKED**。

## 1. 不懂代码时，先看一条回答怎样流动

```text
浏览器 /chat/{session_id}
  → 创建草稿和来源授权 → POST /api/v1/runs/{run_id}/start
  → PostgreSQL：run 排队；冻结模型、来源版本、预算和截止时间
  → 独立 Worker 领取 run，写入 ModelCall 预占回执
  → 唯一 Support 图：meta → support → output_policy
       support → LangChain/OpenAI 兼容 Provider 的内部流 → 私有 Buffer
       output_policy → 完整 JSON、usage、finish、tool/refusal 和整稿规则检查
  → Worker 复核身份、来源、取消与 generation
  → 同一事务写 assistant Message + 一条完整正文 delta + completed
  → SSE / 快照 → 浏览器显示已持久化的回答
```

**私有 Buffer** 是模型运行时暂放原始块的地方，不是用户消息或公开事件。SSE 只读取 Worker 已提交的公共事件；页面刷新后读快照，不再启动模型。若检查失败、取消或来源失效，未授权的 Buffer 不会变成网页正文。

### 1.1 六个容易混淆的名字

| 名称 | 在本步代表什么 | 容易误解之处 |
|---|---|---|
| `Provider` | 实际调用 `grok-4.7` 的兼容接口适配器 | 协议兼容不代表所有能力均已实测 |
| 内部流 | SDK 逐块接收模型输出，放入私有 Buffer | 不是公开的 `message.delta` |
| `RunExecution` | 某次 run 的身份、来源、版本、预算与截止时间绑定 | Worker 重启或配置变化不能放大这次预算 |
| `ModelCall` | 调用前预占、调用后结算或记录未知结果的持久账本 | `actual_tokens=null` 不等于零消耗 |
| 公共 `message.delta` | 已授权、已提交、可由 SSE 重放的正文 | 当前整稿路径只有一条完整正文 delta |
| 删除回执 | 在线清理进度与外部 Provider 状态 | `completed` 只说明本应用在线清理完成 |

### 1.2 主要代码位置

| 文件 | 从哪里读起 |
|---|---|
| [backend/app/config.py](../backend/app/config.py) | `load_settings()`、live 开关和隔离测试库限制 |
| [backend/app/provider.py](../backend/app/provider.py) | `open_provider()`、`InternalStreamProvider.ainvoke()` 与私有流边界 |
| [backend/app/provider_probe.py](../backend/app/provider_probe.py) | 固定合成输入的显式单次真实 PoC |
| [backend/app/support.py](../backend/app/support.py) | `SupportRuntime._support()`、`_output()`：预占、终局检查和整稿规则 |
| [backend/app/runs.py](../backend/app/runs.py) | `start_run()`：冻结配置、来源和预算 |
| [backend/app/run_worker.py](../backend/app/run_worker.py) | `execute_one()`、`execute()`：独立领取、调用、取消和事务发布 |
| [backend/app/deletion.py](../backend/app/deletion.py) | `receipt()`：根据持久调用记录判断外部状态 |
| [frontend/src/history-page.tsx](../frontend/src/history-page.tsx) | 删除处理记录中展示外部状态 |

## 2. 完整例子：一条合成输入从页面到回答

假设测试账号在 `/chat` 输入“今天有点累，想先把事情说清楚”。这个句子只用于隔离合成验收，不代表专业支持内容已经审阅。

### 第一步：页面创建并启动 run

页面沿用 STEP06 的发送流程，建立会话、草稿及来源授权，再调用 `POST /api/v1/runs/{run_id}/start`。`start_run()` 先检查 owner、会话状态和版本、来源授权、重复消息键及是否已有活动 run，然后把这次调用的模型 ID、Provider base URL、一次调用预算、输出上限和 deadline 写入既有 `RunExecution`。本次 live 的 `max_calls` 为 1，默认输出上限 1024 token、deadline 60 秒；真实金额未知，费用字段保留 `null`。这一步只是**持久排队**，API 请求本身不执行模型。

### 第二步：独立 Worker 调用内部流

Worker 领取排队 run 后，按冻结的预算构造原来的 `SupportRuntime`，仍使用 `meta → support → output_policy` 一张图。它先把 `ModelCall` 预占写入数据库，再通过 `open_provider()` 建立显式 SDK 客户端。兼容请求同时携带 `max_completion_tokens` 和 `max_tokens`，SDK 不自动重试。Provider 的块被限制在私有 Buffer：最多 32,768 UTF-8 字节和 4,096 块；触限即停止，不能因为攒满了就向网页放行。

本轮第一次真实 PoC 收到了模型流，但模型报告的输出用量超过 1024 上限，运行判为 `usage_over_reservation`，没有返回正文。补上兼容参数后，第二次**独立** PoC 才通过。失败和通过各有自己的收据，不能把首次失败改写成成功，也不能据此推断供应商以后每次都遵守输出上限。

### 第三步：整稿检查后才发布

内部流结束后，Support 图检查完整 JSON 是否符合候选结构、usage 是否存在且在预占内、`finish_reason` 是否为正常结束，并拒绝 tool call、refusal 和不合规正文。这里的固定输出规则只是工程检查，**不能替代中文语义安全或专业人工审阅**。

Worker 在提交前再次核对 run 仍在运行、generation 未变化、deadline 未过期且来源授权仍有效。通过后，同一数据库事务写入 assistant 消息、一条完整正文 `message.delta` 和 `run.completed`。浏览器从 SSE 收到事件，再读取权威快照；刷新后显示同一段已持久化正文，不再次请求模型。实际页面收据记录了 SSE、快照、DOM 一致，刷新后调用次数仍为 1。

## 3. 为什么内部流和公开流要分开

模型的原始块可能只是半截 JSON、尚未闭合的转义、工具参数，或后来才被整体语义推翻的句子。把 SDK 回调直接变成 `message.delta`，用户就可能先看到未授权内容。因此当前整稿路径在完整检查前，公共正文数始终为零；检查通过后才一次发布。

[双路径设计](../PsyEvoAgent项目计划/阶段1/02-技术方案与实施计划.md#safe-output-streaming)规划了将来可验证的 Safe Chunk Streaming：先判断输入是否允许分块，再结合已发布前缀、上下文和候选块逐块审查，并处理取消、重连、回滚和终局失败。当前没有可靠的准入与跨块策略，不能用“未命中几个关键词”把输入归为安全。对应[双路径验收](../PsyEvoAgent项目计划/阶段1/03-测试与验收标准.md#safe-output-streaming-acceptance)仍待执行；本轮页面的一条整稿 delta 不能算分块通过。

真实模型的能力也要按**观察范围**记账：本轮真实观察包括文本、内部 stream、JSON 文本解析、终局 usage 和网页取消；401、429、500、断流、缺 usage、tool/refusal 等故障主要由受控 SDK 传输替身验证。受控替身证明应用怎样处理这些输入，不证明真实 Provider 曾经产生这些情况。价格、地区、保留条件、远端取消与删除状态仍为 `unknown`。

## 4. 取消、来源失效和删除怎样阻止迟到回答

用户按“停止”时，API 的取消状态和 generation 会变化；Worker 周期性检查权限，取消本地任务并关闭流。即使 Provider 随后送来剩余块，提交事务前的状态复核也会拒绝迟到正文。实际网页验收中，取消轮持久状态为 `cancelled`、没有回答；调用账本的实际用量为 `null`。本地关闭流不能证明供应商已经停止远端计算或计费。

来源授权被撤销、来源消息被删除或会话被确认删除时，也要在运行和最终提交边界重新核对，不能沿用启动时的一次成功授权。删除仍遵循 STEP07 的顺序：先持久阻断在线访问，再逐项清理消息、事件、反馈与来源关联。STEP08 在删除回执中增加 `external_provider_status`：若历史 `ModelCall` 表明发生过 live 调用，就显示 `unknown`；没有 live 调用才显示 `not_applicable`。这个判断来自**持久账本**，所以 API 重启为 disabled 后，旧调用也不会被误标为“不适用”。

在线删除回执的 `completed` 表示本应用负责的在线正文和事件已清理。供应商是否保留了请求、何时删除，以及取消后是否计费，当前都没有证据；页面把外部状态单独展示。无正文墓碑、幂等摘要和用量元数据仍按既有删除合同保留，用于防止重放和解释调用事实。

本轮复用已有的 run、消息、事件、调用账本和删除任务表；新增冻结字段放在既有执行记录的 JSON 中，没有新数据库迁移，也没有新建第二个 Worker 或 Agent 循环。

## 5. 开关和密钥：怎样保持实验隔离

`load_settings()` 只读显式进程环境变量，不自动读取 `.env`。默认 `PSYEVO_SUPPORT_MODE=disabled`；`live` 只允许 `PSYEVO_ENV=test`、本机独立的合成 check/migration 数据库和非空密钥。模型与 base URL 由当前配置指定，本轮登记的是 `grok-4.7` 和 `https://ai.hybgzs.com/v1`。密钥只交给 API、Worker 或单独 PoC 进程，网页与前端构建进程不持有它。

若需要复现，本仓库的[开发说明](../DEVELOPMENT.md)列出显式加载本地配置后运行 `scripts/check_step08.py --live` 的命令和环境限制。它会调用真实模型，可能产生费用；现有收据已经记录了本轮执行结果，**阅读本教程不需要重新运行**。普通 fake 回归和 PR 门禁不会自动发起 live 请求。PoC 使用 `PSYEVO_LIVE_PROBE_ENABLED=true` 与 `--live` 单独启用，不能把 PoC 开关当成网页 live 开关。真实密钥、原始回答和提示词不写入代码、前端或普通收据。

## 6. 测试与证据各自证明什么

| 入口或记录 | 已验证范围 | 不能推出什么 |
|---|---|---|
| [首次 PoC 失败收据](../PsyEvoAgent项目计划/阶段1/evidence/S1-STEP08/continuation/poc-output-limit-failure/receipt.json)与[修复后通过收据](../PsyEvoAgent项目计划/阶段1/evidence/S1-STEP08/continuation/poc-passed/receipt.json) | 真实内部流、终局 usage、超限拦截与兼容参数修复 | 不能说所有模型能力均 tested |
| [backend/tests/test_provider.py](../backend/tests/test_provider.py) | 实际 SDK 配合受控传输替身，覆盖流、取消和故障输入 | 不能说这些故障由真实 Provider 产生 |
| [backend/tests/test_live_runs.py](../backend/tests/test_live_runs.py) | 真实 PostgreSQL 加受控 SDK，检查发布前零公共正文、取消和删除状态持久化 | 不能替代真实网页或远端删除证明 |
| [frontend/tests/live.spec.ts](../frontend/tests/live.spec.ts)与[页面收据](../PsyEvoAgent项目计划/阶段1/evidence/S1-STEP08/continuation/windows/step08-live-browser.txt) | 实际网页发送、SSE/快照/DOM、刷新、跨 owner、取消及删除 | 不能证明任意中文支持内容安全 |
| [最终门禁收据](../PsyEvoAgent项目计划/阶段1/evidence/S1-STEP08/continuation/windows/receipt.json)与[续作记录](../PsyEvoAgent项目计划/阶段1/evidence/S1-STEP08/continuation.md) | 隔离合成数据库中的工程联调、前置回归及重启直查 | 不能把 STEP08.2～.4 或全部业务用例标为通过 |

最终 Windows 门禁中，70 项数据库/API/迁移、83 项后端检查、20 项前置页面和 1 项 live 完整页面旅程通过；数据库重启后又直查成功轮与取消轮各只有一次调用、删除后正文已清空且外部状态仍为 `unknown`。WSL 内核隔离验证的是工程与 fake Support 回归，**真实 live 调用不在禁外连的 WSL 域执行**。本轮未访问开发数据库、未发布远程服务，也没有把失败收据覆盖成成功收据。

## 7. 当前还差什么，下一步应按什么顺序读

| 项目 | 当前状态与原因 |
|---|---|
| STEP08.1 真实模型整稿工程链 | 已有真实 PoC 和隔离网页旅程收据；完整能力矩阵、可靠安全分块和专业语义材料仍缺，`.1` 尚未关闭 |
| 安全公共分块 | 未开放；需要可靠准入、跨块审查、逐块持久化与重连/取消验收 |
| 专业支持、练习及高风险内容 | 缺独立审阅材料，不能把固定规则或合成页面测试标为业务语义验收 |
| 真实 SMTP、供应商数据条件 | SMTP 未配置；供应商地区、保留、价格和远端删除/取消结果未知 |
| STEP08.2～.4 | 阶段1逐例验收矩阵、阶段2合同冻结与完整交接尚未执行 |

这也说明为什么[实施清单](../PsyEvoAgent项目计划/阶段1/04-分步实施与检查清单.md#s1-step08)仍保留 `.1～.4` 未勾选：工程域的真实联调是重要进展，但后续独立检查仍有未满足项。既有 STEP04～07 的 fake 收据只证明各自当时的范围，不会因这次真实调用自动升级。

## 8. 用几个失败场景检查自己是否理解

### 场景 A：模型已经送来几个内部块，随后 JSON 不合法

这些块只在私有 Buffer。终局结构检查失败时，Worker 不写 assistant 消息或 `message.delta`，网页不能显示“先收到的几句”。把 SDK 块直接送到 SSE 会越过当前授权边界。

### 场景 B：模型报告的用量超过预占

账本记录实际报告值和 `usage_over_reservation`，本轮不发布正文。不能删掉预算检查以换取一次成功，也不能把未知费用改成零。首次 PoC 就是这个反例。

### 场景 C：用户取消时，模型请求可能仍在远端处理

本地 run 进入 `cancelled`，Worker 不提交迟到回答；`actual_tokens` 可以保持 `null`。这证明本应用的发布边界有效，不证明远端停止运算或不收费。

### 场景 D：删除后重启 API，默认模型开关变成 disabled

删除回执仍查持久 `ModelCall`。已有 live 调用的 `external_provider_status` 继续为 `unknown`；不能因为当前进程没有配置 Provider 就把历史调用改称 `not_applicable`。

### 场景 E：网页刷新后又看见同一段回答

页面读已持久化快照；SSE 重放的是同一 run 的公共事件，模型调用数不增加。若只是前端把已显示的文本重新播放成动画，也不能算真正的安全公共分块。

## 9. 建议的学习顺序与自测

按一条 run 从创建到删除跟读，比先读 SDK 全部接口更容易：

1. 先读 [runs.py](../backend/app/runs.py) 的 `start_run()`，找出哪些配置在启动时冻结。
2. 再读 [run_worker.py](../backend/app/run_worker.py) 的 `execute_one()` 和 `execute()`，标出调用前预占、取消检查与最终事务。
3. 读 [provider.py](../backend/app/provider.py) 的私有 Buffer，再对照 [support.py](../backend/app/support.py) 的 schema、usage、tool、finish 和输出规则检查。
4. 读 [deletion.py](../backend/app/deletion.py) 的 `receipt()`，解释重启后为何仍知道发生过 live 调用。
5. 最后对照[续作证据](../PsyEvoAgent项目计划/阶段1/evidence/S1-STEP08/continuation.md)、[双路径合同](../PsyEvoAgent项目计划/阶段1/02-技术方案与实施计划.md#safe-output-streaming)和[实施清单](../PsyEvoAgent项目计划/阶段1/04-分步实施与检查清单.md#s1-step08)，区分观察、受控测试和未执行项。

可以用这些问题自测：

1. Provider 已经 stream，为什么当前网页仍只收到一条完整正文 delta？
2. 为什么 `ModelCall` 要在真正调用前预占？缺失 usage 和超限 usage 应如何记账？
3. 取消后为何还要在数据库提交前复核 run 与 generation？
4. 在线删除完成后，为什么外部 Provider 状态仍可能是 `unknown`？
5. 受控 SDK 故障测试、真实 PoC、实际网页旅程分别证明什么？
6. 要把 STEP08 标为完成，还需要哪些独立证据？

能按“**启动时冻结预算 → Worker 预占 → 模型内部流进入私有 Buffer → 整稿检查 → 事务发布 → SSE/快照恢复 → 删除回执保留外部未知状态**”说清一条 run，就抓住了本轮 STEP08.1 的工程主线。
