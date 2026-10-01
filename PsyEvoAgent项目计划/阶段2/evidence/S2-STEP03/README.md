# S2-STEP03 持久job与Worker恢复：执行记录

日期：2026-09-30；执行者：Codex；开始基线`6763f58`，开始时工作区干净。本次只实施S2-STEP03.1～.3。当前状态：**COMPLETED（持久job与Worker恢复范围）**。无本步未解决blocker；最早未完成为S2-STEP04，本次未进入。

2026-09-30 后续审查修复：跨账号锁阻塞时继续扫描后续候选批次，探针复用幂等回执前核验类型、资源 ID 和哈希。新增 7 项回归；69 项 PostgreSQL job/记录测试与 190 项后端测试通过，见[独立修复记录](review-repairs.md)。下方完整门禁及哈希保留原实施时点。

## 开始前检查

- 上一步S2-STEP02实现已合并：`e779ef7`经`6763f58`合入；实际存在records API/页面、`l012_records`、typed current_run来源与删除实现。
- STEP02历史README、PostgreSQL/API JUnit、浏览器、重启指纹和机器收据存在；其历史统计不替代本次执行。本次另跑当前源码的记录及聊天回归。
- 核定上一步最新依据为[STEP02审查修复](../S2-STEP02/review-repairs.md)：150项PG/API/迁移、188项后端及49项浏览器通过，198个工程文件哈希与其最终工作区一致；较早首页143/188/41统计保留原时点。六项审查问题已有修复及新增回归，未留下本步blocker。
- 真实仓库原Worker仅处理Support与标题，没有background_jobs、可回收lease或LangMem。最早未完成为S2-STEP03，按本阶段04推进。
- 未发现阻塞本步的前置缺陷或外部条件。LangMem真实兼容、画像校准和安全公共分块属于各自后续消费者/未验证域，本步不依赖它们。

## 实现与边界

实际范围见[技术合同](../../02-技术方案与实施计划.md#s2-step03-implementation)，判据见[本步验收](../../03-测试与验收标准.md#s2-step03-checks)。新增PG任务与预算账本，扩展原ContextGrant的互斥job范围，复用owner锁、来源校验、Budget、Idempotency及原Worker入口。前端无新增，普通开发不自动入队或运行提取。

测试probe只产生无正文恢复收据，未创建正式候选/记忆表，不是LangMem提取结果。本步不调用真实Provider/SMTP、不迁移开发库、不部署服务。

## 最终实际验收

最终门禁：`.artifacts/psyevo-step07-9d885633a77d/`；[机器收据](windows/receipt.json)与[汇总及源码核验](verification.json)已归档。204个工程文件SHA-256与本轮最终门禁一致，之后只更新状态/证据文档。随机PostgreSQL16.13容器已[清理](windows/database-cleanup.txt)，未访问开发库；前两轮失败原收据分别保留在下方。

| 检查 | 实际结果与证据 |
|---|---|
| PostgreSQL/API/迁移 | **180/180通过**：[输出及耗时](windows/api-migrations.txt)、[JUnit](windows/postgres-tests.xml)。包含29项job用例、1项新增迁移用例和上一步150项回归 |
| 后端基础 | **190/190通过**：[输出](windows/foundation.txt)；[Ruff](windows/lint.txt)、[格式](windows/format.txt)、[mypy](windows/types.txt)、[锁文件](windows/lock.txt)通过 |
| 迁移 | [升级](windows/migration.txt)、[无漂移](windows/schema-drift.txt)通过；老记录保留，空新增表可降级，有job/budget时拒绝丢失性降级 |
| 前端 | [check](windows/frontend-check.txt)及[build](windows/frontend-build.txt)通过；未新增页面/控件/依赖，check含原7项Node及7项Vitest |
| 浏览器回归 | **49/49通过**：入口[10](windows/browser.txt)、HTTPS[1](windows/https-browser.txt)、SSE[1](windows/step05-gateway.txt)、聊天[17](windows/step06-browser.txt)、历史[5](windows/step07-browser.txt)、记录[14](windows/s2-step02-browser.txt)、模型设置[1](windows/model-settings-browser.txt) |
| 真实Worker强杀 | [领取后](windows/crash-after_claim.json)、[提交前](windows/crash-before_commit.json)、[提交后](windows/crash-after_commit.json)。新进程恢复，前两者attempt/token由1到2；提交后保留1/1。三个场景各只有一条结果收据；提交前崩溃的旧预占仍是reserved/unknown，没有清零 |
| 续租、取消和错误 | 超过初始5秒租约仍只有一次调用；运行中撤销停止fake调用；旧token/generation、删源、改源、取消、配置改变拒绝迟到写；真实PG事务连接中断回滚副作用；断DB连续3次退出；参数/schema/权限/删除/未知mutation不自动重发；见29项job JUnit记录 |
| 真实数据库重启 | [重启前](windows/s2-jobs-before-restart.txt)、[重启后](windows/s2-jobs-after-restart.txt)、[指纹](windows/jobs-restart.json)：30条job、28条budget、30条job grant、6条结果收据的数量与哈希完全一致；原记录与阶段1事实重启检查同时通过 |
| 文档 | [检查](windows/documents.txt)通过，仍为32份阶段文档、92任务、153用例及61个STEP；状态更新后另核链接、编号与差异格式 |

S2-A09/S2-A10的本步任务范围通过。合成probe实际读取获准记录、经已锁定LangChain fake返回并校验形状，使用原Idempotency写唯一无正文副作用；它不等于正式候选保存。正式memory表仍不存在，因此错误/崩溃不能生成假记忆。没有扩大任何真实模型、研究或发布门槛。

之前的专项初测25项、扩展任务/迁移/记录专项75项及后端190项结果只作为过程验证；最终状态采用上表完整门禁。

### 中间失败与修复

首轮完整门禁真实结果为172通过/7失败，保留[原机器收据](initial-failure/receipt.json)、[原输出](initial-failure/api-migrations.txt)及[JUnit](initial-failure/postgres-tests.xml)。新增job grant的run_id为null，原历史上下文`NOT IN`子查询被null影响，导致正常多轮前文全被排除。修复为按当前run及current_run用途关联的`NOT EXISTS`；新增带job授权的正常聊天历史回归，既有临时记录回答的排除规则继续保留。该问题是本步scope扩展的兼容修复，不将旧STEP02历史收据改为失败。

第二轮数据库组在原240秒总上限内显示172项进度但未完成，记[超时失败](timeout-run/receipt.json)，不按未见断言错误判通过。检查器仅为`--s2-step03`的整组PG测试提高到有界480秒并记录最慢10项；任务自身的lease、deadline和重试预算不变。该轮容器已清理，最终验收使用之后的完整运行。

## 交付下一步与限制

- STEP04复用当前job/lease/预算/来源scope与提交事务，再实现LangMem适配、候选校验、正式保存及其真实模型验收；本步不提前安装LangMem、创建memory表或自动触发提取。
- 当前消费者仅支持显式test/fake恢复probe；没有新增Agent、生产任务kind、调度平台、Kafka、第二Store或新依赖。普通本地聊天/标题启动规则沿原实现。
- job预算为当前任务谱系的持久预算，fake成本明确为0。真实Provider、父run/experiment预算联动与真实提取usage仍需在真实消费者接入时验证，不能以本步恢复收据代替。
- Windows语言层网络保护不等于WSL内核隔离，本步未运行WSL门禁；未配置应用备份/持久checkpoint，不声称验证了旧备份恢复。外部Provider删除、专业心理效果与公共安全分块也不由本步结果推定。
- 步骤状态、01～04当前记录与AGENTS/README已更新；STEP01、STEP02及阶段1历史证据保持原时点。
