# S2-STEP04 LangMem提取、校验与自动保存：执行记录

2026-10-02 后续四项审查修复单列于[审查修复记录](review-repairs.md)。下方验收及历史失败记录保持原时点。

日期：2026-10-02；执行者：Codex；开始基线`fe610f4`，工作区干净。只实施S2-STEP04.1～.4。当前状态：**COMPLETED**；无本步未解决blocker，最早未完成S2-STEP05，本次未进入。

## 开始前核对

- STEP03已合并：`b093d6b`经`fe610f4`合入，真实存在app.jobs、job_worker、m013_background_jobs与原Worker入口。
- 历史180项PG/API/迁移、190项后端、49项浏览器、三处强杀及PG重启收据完整；后续修复另有69项job/记录和190项后端通过。STEP02原收据及后续150/188/49修复收据均保留。
- 最早未完成为STEP04，无上步未解决blocker。开始时没有LangMem依赖和正式记忆表/接口/页面；按01目标、02技术、03验收、04步骤接入。
- 本轮复跑STEP03/记录69项，67项通过、2项失败是旧测试仍断言“记忆表不存在”；改为验证probe不生成记忆，不覆盖STEP03历史事实。

## 实现与边界

详见[实现合同](../../02-技术方案与实施计划.md#s2-step04-implementation)。复用jobs/Worker、来源、幂等、预算、配置加密及DeletionJob。S15保留来源/推断信息层级，按现行自动保存合同实现，遗忘仍确认。

STEP05检索/摘要/ContextManifest、STEP06画像、自评/关心及后续阶段未实现。未迁移开发库、未发布、未发送SMTP；真实模型只消费隔离合成资料。

## 过程观察

- LangMem0.0.30/Trustcall0.0.39与既有Core1.6.4、OpenAI适配器1.6.6、LangGraph1.2.12已实际装配。Trustcall旧Send别名弃用告警明确登记。
- 首次live采用本机当时配置的openai/gpt-oss-20b，并非历史grok配置；两句合成笔记提取user_statement/user_feeling各一条并保存，重复复用job，总tokens=1465。密钥不入证据。
- 专项22项PG记忆/迁移检查通过，包括三个真实独立Worker强杀点。完整回归仍需另行完成。
- 首轮完整门禁900秒超时，后段3个失败，不推定完成。新迁移降级须恢复旧ck_*_typed约束名称；同时原空库迁移测试的预期表清单须增加四个本步表。只修新迁移和当前测试，旧迁移及历史收据不改。
- 第二轮900秒超时；逐项诊断证实完整组需超过17分钟，整组验收上限改为1800秒，job自身120秒/2次调用限制不变。一次格式门禁失败已按Ruff修正。
- 诊断及并行完整组均复现阶段1标题任务“领取后、调用前已过期仍停留running”的边界：204项通过、1项失败。修复原titles.execute的前置失效终态，保持零模型调用；新增明确调用前过期反例，标题14项专项通过。此前启动的测试进程使用旧已导入代码，因此保留该失败并重新运行最终门禁，不将运行中修改的源码冒充已验证。
- 新增页面4项独立验收通过：自动保存/更正重开/确认遗忘并核原笔记保留、390px停止筛选与错误重试、保存失败保留编辑、实际并发冲突核对；桌面/窄屏截图已检查。

以下过程记录保留其当时时点；最终结论以末尾验收表为准。

2026-10-02完整数据库组已实际通过210项（979.17秒），后端190项与前端check/build通过；其后HTTPS浏览器原5秒就绪断言失败。单独复现证实首屏及刷新需更长加载时间，改为15秒有界等待/60秒用例总限额后，实际HTTPS注册、Secure Cookie、刷新、图标、错误Origin与退出均通过（31.6秒）。不改产品权限或Cookie规则。

续验使用`--reuse-postgres-evidence`核验上述210项与全部后端文件哈希，重新创建隔离库并执行恢复/记忆专项及全部后续门禁；原HTTPS失败整轮保留failed。此方式避免在仅浏览器等待变化后重复16分钟的同版PG组，复用记录与本轮结果分别登记。

浏览器续验另暴露原检查的图片解码竞态与长旅程总时限：图片改为轮询实际complete/naturalWidth；摘记两轮/删源、跨账号恢复、历史修订/删除等已超时的长流程增加有界总时限；21轮旅程由180秒调整为300秒，聊天组总限额720秒、记录组480秒。业务deadline、预占、断言内容和重试次数没有放宽，不以超时阶段的成功进度代替最终结果。早期额外预检未完整准备旧页面合成账号，因此其登录失败不充当产品结果，采用正式检查器的完整种子与最终收据。

分页完整旅程还真实发现锚点跳动：先出现3741px偏移，保留请求锚点后仍有焦点引起的4px残差。最终在激活前捕获、按实际页数释放并补偿外层滚动容器；两种高度专项和真实21轮检查均满足原小于2px判据。该必要前置修复没有放宽误差，也没有进入STEP05。

## 最终验收与交付

最终轮：`.artifacts/psyevo-step07-a97226260cc8`；[机器收据](windows/receipt.json)、[源文件核验](verification.json)。**217个工程文件SHA-256全部一致**，之后仅更新状态/证据文档。执行命令：

```powershell
backend/.venv/Scripts/python.exe -X utf8 scripts/check_step03.py --s2-step04-live --reuse-postgres-evidence .artifacts/psyevo-step07-a2c990dd030b/receipt.json --web-port 3194 --api-port 8194 --tls-port 3494
```

| 检查 | 实际结果及证据 |
|---|---|
| PostgreSQL/API/迁移 | **210/210通过**，[JUnit](windows/postgres-tests.xml)、[输出/耗时](windows/api-migrations.txt)。来自[已通过PG但HTTPS失败的原轮](postgres-passed-https-failure/receipt.json)；102个后端文件清单/hash一致后才复用，原轮整体仍failed |
| 新库恢复/记忆复验 | **38/38通过**，[JUnit](windows/postgres-recovery-recheck.xml)、[输出](windows/postgres-recovery-recheck.txt)。重新建立本轮实际任务/记忆事实，不以复制JUnit冒充新库执行 |
| 后端与迁移 | **190/190通过**，[基础](windows/foundation.txt)、[Ruff](windows/lint.txt)、[格式](windows/format.txt)、[mypy](windows/types.txt)、[锁文件](windows/lock.txt)、[升级](windows/migration.txt)、[无漂移](windows/schema-drift.txt) |
| 前端 | [check](windows/frontend-check.txt)、[build](windows/frontend-build.txt)通过，含7项Node及7项Vitest；无新前端依赖 |
| 浏览器 | **54/54通过**：入口[10](windows/browser.txt)、HTTPS[1](windows/https-browser.txt)、记录[14](windows/s2-step02-browser.txt)、SSE[1](windows/step05-gateway.txt)、聊天及锚点[18](windows/step06-browser.txt)、历史[5](windows/step07-browser.txt)、模型设置[1](windows/model-settings-browser.txt)、记忆[4](windows/s2-step04-browser.txt) |
| 真实记忆Worker强杀 | [领取后](windows/memory-crash-after_claim.json)、[提交前](windows/memory-crash-before_commit.json)、[提交后](windows/memory-crash-after_commit.json)：每个最终一条候选/记忆，前两种attempt/token增至2，提交后不重做；提交前旧调用预占保留unknown。原STEP03 probe三处强杀也复验通过 |
| 真实LangMem/Provider | [live收据](windows/memory-live.json)：本机配置openai/gpt-oss-20b，经原Provider及LangMem生成2条真实合成候选并保存；一次调用1737 tokens，重复返回同job。初次1465 tokens另保留[原始收据](step04-live-initial.json)；二者不是供应商账单 |
| 真实PG重启 | [重启前](windows/memory-before-restart.txt)、[重启后](windows/memory-after-restart.txt)、[指纹](windows/memory-restart.json)：13条memory、13条candidate、13条来源关系、6条抑制，以及44个job、43个budget、44个job grant、3条probe结果的数量/hash一致。包括清理后的空正文墓碑，不等于13条均有效 |
| 文档与清理 | [文档](windows/documents.txt)、[差异](windows/diff.txt)通过；随机测试容器已[清理](windows/database-cleanup.txt)。原阶段1和记录重启事实也由本轮检查器核对 |

S2-STEP04.1～.4及本步S2-A04、S2-A09/A10、S2-A11/RSI-S2-A01/A04记忆切片通过；没有把父用例的画像/摘要/检索部分或阶段2整体标为完成。前端采用S15来源/推断层级，实际[桌面](windows/memory-desktop.png)与[390px](windows/memory-mobile.png)截图和操作已核对。

未决限制：未实施STEP05长期检索/摘要、STEP06画像或后续跟进；未验证临床效果/公共安全分块、外部Provider删除或供应商计费，地区/保留策略未知；无持久checkpoint/应用备份，本步未重跑WSL内核隔离。未迁移开发库、未发送SMTP、未发布服务。这些不被本步工程结果推定通过；当前范围无未解决blocker。

收尾：本轮辅助隔离容器`psyevo-s2-step04-work-20261002`（ID前缀1857d2781ca4）亦已核对身份并清理；开发库未触及。状态更新后再次通过文档链接/编号检查与git diff --check，工程文件哈希仍为217项一致。
