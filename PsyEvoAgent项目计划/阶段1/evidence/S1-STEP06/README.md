# S1-STEP06 对话、练习及偏好页面

日期2026-09-25，基线`fe5911c`，开始时工作区干净。实施者Codex；只推进STEP06，无STEP07历史修订、删除或反馈。

> 下文首次验收的“最终”指原STEP06实施时点；两项评审修复和当前源码复验见文末补记。原始收据不改写。

## 前置核对

STEP05四项合成工程交付已落地，代码为runs/run_stream/run_worker及持久化迁移；2026-09-24归档收据和2026-09-25审查修复记录可核。最新历史复验为50项PostgreSQL/API/迁移、65项后端及实际网关。本步门禁重新执行前置回归。真实Provider、专业内容审阅、SMTP仍BLOCKED，不阻塞隔离合成域。最早未完成步骤为STEP06。

## 实施范围

前端新增对话发送/停止/状态恢复、独立练习、资源空态和账号偏好，复用现有Query/Form/Zod。后端只补当前轮次和静态资源读模型，复用身份、来源核权、偏好接口、run/SSE。无数据库schema、依赖、Agent图或Worker消费者变更。详情见[技术合同](../../02-技术方案与实施计划.md#s1-step06-implementation)和[验收协议](../../03-测试与验收标准.md#s1-step06-validation)。

## UI参考与差异

实际读取S01–S03、S05–S07、S09原图。采用蓝白品牌、桌面左导航、消息层级、清晰输入区、独立步骤和资源空态。S01不增加确认门槛；S02/S03不提前开放历史搜索、带入记录和反馈；S05/S06不能把图中“已审阅”搬成事实，使用明确未审合成版本并在正常环境关闭；S07只开放练习/现实支持；S09不虚构学校与官方URL。移动端导航换行、输入区随页面滚动避免固定栏遮挡；原生按钮至少44px，跳转主要内容、可见焦点、练习步骤焦点和减少动画均有消费者。无计时器/动画，无退出后的后台练习任务。

## 验收状态

最终状态：**COMPLETED（STEP06三项隔离合成工程交付）**。Windows最终[收据](windows/receipt.json)所有命令退出0，125个工程文件hash与最终源码一致。本轮只使用随机独立合成数据库，测试容器和进程已清理，未迁移或改写开发库。Python3.12.13、Node22.19.0、pnpm10.28.0、固定PostgreSQL16.13镜像见收据。

| 检查 | 实际结果 |
|---|---|
| PostgreSQL/API/迁移 | [53项通过](windows/postgres-tests.xml)：50项前置回归及3项本步当前轮次核权/删源/模型关闭静态资源检查 |
| 后端工程 | [65项通过](windows/foundation.txt)，Ruff、mypy、锁、schema drift通过 |
| 前端 | [check](windows/frontend-check.txt)含类型/lint/2项unit/格式检查；[build](windows/frontend-build.txt)通过 |
| 既有浏览器 | [9项身份/工程](windows/browser.txt)、[1项HTTPS](windows/https-browser.txt)、[1项STEP05真实网关](windows/step05-gateway.txt)通过 |
| STEP06页面 | [4项真实页面](windows/step06-browser.txt)通过：丢响应原key重试、刷新恢复、跨账号不可读、停止与终态一致、断流不重发、偏好失败/保存/刷新、手机键盘、独立练习退出/跳过/刷新/完成及现实支持空态 |
| 重启持久事实 | [STEP05](windows/step05-restart-facts.txt)及[STEP06](windows/step06-restart-facts.txt)直接查库：偏好version=2且大字号/隐藏标题持久；丢响应重试只产生一条用户消息、一个run、一次调用、一次主动事件 |
| WSL内核隔离 | [封装收据](wsl/receipt.json)和[工程收据](wsl/engineering.json)通过；65项后端、2项unit、5项工程浏览器及额外[41项Support](wsl/runtime-tests.txt)。IPv4/IPv6 TCP/UDP、原生curl、WSL互操作均拒绝；[未隔离负例](wsl-negative.txt)预期退出1 |
| 文档 | 32份文档、153个验收定义及链接/表格检查通过，git diff --check通过 |

WSL复用`--step04`封装，机器收据保留其原step_id；本次实际装配包含STEP06源码，不把它改名冒充完整数据库/页面内核隔离。WSL不执行PostgreSQL业务验收或STEP06专用页面测试，这部分由Windows门禁验证。两端[85个源码文件比较](wsl-source-comparison.json)除CRLF/LF外全部一致；未把Windows依赖用于Linux进程。

## 可访问性与截图

- [桌面对话](windows/chat-desktop.png)：实际合成输入/回应和唯一终态，输入区与停止/查询操作分离；已人工查看。
- [手机大字号](windows/chat-mobile.png)：390px、隐藏标题、键盘Tab到发送焦点可见，DOM横向无溢出；已人工查看。浏览器视口/键盘检查不冒充实体手机软键盘测试。
- [独立练习](windows/exercise-desktop.png)：步骤、可跳过及始终存在的退出入口；完成焦点自动到标题；已人工查看。
- [手机现实支持](windows/resources-mobile.png)：未知状态，无编造电话或核查日期。减少动画为默认偏好，本步没有计时器或动画，因此退出后无残留计时/动画资源。

## 失败与修复

[首轮](failure-first/receipt.json)数据库与既有回归通过，两个页面测试失败：创建操作在身份数据未就绪时可点击，现显式禁用；select精确label定位未命中，改用实际combobox无障碍角色。另修正按owner分离QueryClient的开发StrictMode清理后重新注入身份，避免旧身份缓存。终端GBK不能输出Playwright符号的问题通过STEP06入口显式`-X utf8`解决。

[第二轮](failure-second/receipt.json)仅终态验证失败：独立HTTP客户端未带loopback浏览器的Secure Cookie，改为真实页面fetch查询，并断言响应成功后再核状态；不放宽终态断言。第三轮完整Windows门禁通过后，新增数据库重启直查本步持久事实，再完整执行最终门禁通过。

[首轮WSL](failure-wsl-docs/receipt.json)工程代码检查通过，文档表格把引用误写成新定义导致153项计数失败；改用原验收锚点链接，不增删编号，最终重新完整运行通过。历史收据未改写。归档仅含合成输出，不含凭据、证书私钥或真实对话。

## 边界与下一步

真实Provider/能力/价格、专业内容审阅、SMTP仍**BLOCKED（外部条件）**。合成练习在development关闭，不能声称真实学生内容可用或真实模型已验收。无远程发布；无数据库schema变更、新Agent或后台练习任务。反馈、历史搜索/修订、删除及完整153项业务验收仍未完成。

最早尚未完成步骤现在为**S1-STEP07 历史修订、删除与反馈**，本轮未实施。

## 评审修复补记（2026-09-25）

`backend/app/pages.py`的当前轮次查询现在排除软删除的run；新增回归先复现已完成run在`GET /runs/{id}`返回404、但当前轮次仍暴露输入/输出，修复后活跃会话的当前轮次返回null。`frontend/src/chat-page.tsx`在受权快照确认同一run已启动且输入一致后清理待发送状态与旧错误，保留用户已改写的下一条输入；结果仍未知或run仍为draft时，继续使用原幂等键重试。新增真实页面回归覆盖状态查询后发送不同消息，原有用例继续核对丢回执后的同键重试。

根目录实跑`backend/.venv/Scripts/python.exe -X utf8 scripts/check_step06.py --web-port 3106 --api-port 8106 --tls-port 3446`；[新收据](review-fix/receipt.json)全部命令退出0，[隔离PostgreSQL/API](review-fix/postgres-tests.xml)54项、[后端工程](review-fix/foundation.txt)65项、[STEP06真实页面](review-fix/step06-browser.txt)5项通过，前端[check](review-fix/frontend-check.txt)与[build](review-fix/frontend-build.txt)、数据库重启持久事实、文档检查也通过。新收据及其文本日志另存`review-fix/`；旧`windows/`及失败收据保留原样。临时数据库已清理。此处仍仅是隔离合成工程验证，不扩大业务验收或真实Provider、内容审阅、SMTP的状态。
