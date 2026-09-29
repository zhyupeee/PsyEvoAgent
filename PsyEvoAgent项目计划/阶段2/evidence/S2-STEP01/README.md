# S2-STEP01 来源与用途合同：执行记录

日期：2026-09-29；执行者：Codex；开始基线：`f7704b8`，工作区无暂存/未暂存修改。仅实施S2-STEP01.1～.4，未进入S2-STEP02。当前结论：**COMPLETED（合同与合成材料范围）**；无阻塞本步或记录CRUD设计入口的未解决项。阶段2业务功能仍未实现，原RSI验收不整体标通过。

## 开始前检查

| 用户要求 | 实际结论及证据 |
|---|---|
| 上一个STEP | [S1-STEP08收尾](../../../阶段1/evidence/S1-STEP08/engineering-closeout.md)为内部实验工程完成；真实SMTP、整稿Provider、数据库/浏览器及WSL记录存在，历史专业评价/分块未验证边界保留 |
| 代码是否落地 | 存在api/models/runs/run_worker/run_stream/support/provider/history/deletion、对应页面和测试；最新迁移k011_provider_tests。STEP08之后还有多轮、模型设置和输出规则修复，不能只使用旧STEP08版本 |
| 历史测试是否执行 | [质量修复](../../../阶段1/evidence/S1-AUDIT-REPAIRS/README.md)114项数据库、160项后端、35项浏览器；[最新规则跟进](../../../阶段1/evidence/S1-AUDIT-REPAIRS/review-followup.md)188项后端、55项数据库。组合两份收据后185个工程文件SHA-256与本次开始源码一致，均非本次重新执行 |
| 本次前置复验 | 随机隔离PostgreSQL16.13，迁移至head；test_registration/test_step03/test_runs/test_history共**53项通过**。现有API→Worker→数据库覆盖来源归属、历史决定、版本、取消、删除/迟到写及幂等；非真实Provider调用 |
| blocker | 未发现阶段1工程缺陷阻塞本步。LangMem兼容、中文校准、公共安全分块及专业质量仍未验证；当前合同不消费这些运行能力，不伪记passed |
| 最早未完成STEP | 开始时S2-STEP01；完成本次后为S2-STEP02。本次没有运行任何后续产品消费者 |

## 四项产出

权威合同统一写入[阶段2技术方案](../../02-技术方案与实施计划.md#s2-step01-contract)，没有另一份产品API或事实库。

| 子项 | 产出与核查 |
|---|---|
| .1 | 所有权矩阵：真实Conversation/Message/Run/ContextGrant与未实现note/sleep/support_card等分列；现有FK只指会话，记录来源必须后续追加约束迁移 |
| .2 | support/memory/profile/evaluation/optimization配置与purpose/消费范围映射；默认true不意味着已实现、不改写历史consent；记忆、画像、评测不互授 |
| .3 | s2-annotation/1：11维、33条支持/反证/未知示例，5类冷启动/缺失/冲突/频率/严重影响预期；共同封套、证据/画像、claim_type、保留/失效字段与责任步骤明确 |
| .4 | 字段/来源映射：现有代码/迁移、阶段1交接更新、原版复用R编号与RSI研究分域，静态来源/许可与真实装配证据分开；未导入外部代码、题项或私人材料 |

修正两处会影响后续实施的文档歧义：未启动draft范围只适用于current_run创建，不约束后台job为draft；expires_at必填可空且不作业务TTL，保留约定不再要求期限审批。没有因此启用新purpose、任务或写入入口。

## 当前验收

本步[完成判据](../../03-测试与验收标准.md#s2-step01-checks)由本阶段03维护。合成材料在[fixtures](../../fixtures/S2-STEP01/scenarios.json)；其中复用的source ID是独立样例的引用封套，不表示33段示例来自同一条真实消息或一个真实人的时间线。

| 检查 | 结果与证据范围 |
|---|---|
| 合同检查 | 28条来源/用途关联按预期允许或拒绝；11维/33条示例、5组画像预期完整；15个损坏材料反例均拒绝。仅本地材料引用比较和结构检查，不是服务端授权或Assessor执行 |
| 前置数据库 | [机器收据](prerequisite/receipt.json)、[53项输出](prerequisite/postgres-tests.txt)、[JUnit](prerequisite/postgres-tests.xml)、[清理](prerequisite/database-cleanup.txt)；原始目录`.artifacts/s2-step01-prerequisite-8a68d8c1327c/`。随机容器已移除，没有访问开发库 |
| 文档/脚本 | 检查本步链接、锚点、表格、JSON和追溯；32份阶段文档、92项任务、153项验收定义保持原计数。脚本使用既有Python标准库，无新增依赖 |

最终[合同收据](contract-check-20260929T144211-340db8ea.json)、[文档检查](documents.txt)、[Lint](lint.txt)、[格式检查](format.txt)及[最终检查收据](verification.json)在本目录独立保存；包含版本/hash与实际结果，历史阶段1收据未改写。未运行前端build/浏览器、完整Windows/WSL门禁、真实Provider/SMTP；本步没有对应产品改动，不以历史执行冒充本次执行。

## 交付边界

前端、后端业务接口、数据库迁移、AI/Agent/Worker均未新增；本步仅新增离线合同检查脚本、合成材料及当前文档。没有第二套来源服务、memory store、运行状态机或身份系统。

后续S2-STEP02按已有顺序实现笔记/睡眠/备忘CRUD及必要来源/删除闭环，复用原身份、幂等、版本和context_grants；未支持用途继续拒绝。STEP03/04接job/LangMem，STEP05接真实读取，STEP06接画像，STEP07验证派生删除。这里只登记责任，不提前实施。

RSI-S2-A02/03/04本步合同切片通过，端到端产品结果仍planned。中文标注一致性/阈值、实际模型输入、LangMem提取/保存/检索、job恢复与派生清理须在各自步骤提供真实证据；不能使用本次合成预期当模型观察或临床结论。

首次Lint发现13处行长超限，格式化后最终Lint/格式检查通过；该中间检查不记为产品测试失败或最终门禁通过。最终结果以本目录当前收据为准。
