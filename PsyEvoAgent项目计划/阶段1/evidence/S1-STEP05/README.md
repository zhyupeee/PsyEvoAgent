# S1-STEP05 run、SSE与取消

日期2026-09-24；基线`e21bf1e`；开始时Git工作区干净。实施者Codex；只推进STEP05，无STEP06聊天/练习页面或STEP07删除/历史修订。

## 前置核对

STEP04代码、41项合成测试、Windows/WSL历史收据存在；本轮重新执行41项Support测试通过，见本步前置JUnit。STEP03身份/来源/PostgreSQL迁移已落地，完整回归随本步门禁执行。真实Provider/价格/数据条件、专业内容审阅及SMTP仍BLOCKED，不阻塞隔离fake域，不伪称真实模型或邮件可用。

## 实施范围

复用唯一Run、身份Cookie/CSRF、来源核权与Support/LangGraph；新增启动绑定、消息、公共事件、调用账本、互动事件。API事务入队，独立Worker消费，取消/完成以服务端CAS为准。原生SSE核权重放并支持同run快照；浏览器测试直接使用现有Vite网关，无新产品页面。追加迁移保留历史，拒绝丢弃已有执行记录。

合同见[02实际装配](../../02-技术方案与实施计划.md#public-events)，协议见[03](../../03-测试与验收标准.md#s1-step05-validation)。

## 验收状态

最终[Windows收据](windows/receipt.json)所有命令退出0；已核对其109个工程文件hash与最终源码一致。数据库只使用随机独立合成容器，门禁结束自动清理；原开发数据库未迁移或改写。[WSL隔离收据](wsl/receipt.json)与[完整工程收据](wsl/engineering.json)通过：65项后端、2项前端unit、5项工程浏览器、额外41项Support专项及29条fake运行结果。IPv4/IPv6 TCP/UDP、原生curl与WSL互操作全部被内核拒绝；[非隔离负例](wsl-negative.txt)预期退出1。WSL不包含PostgreSQL业务验收，不能混称数据库全链内核隔离。

WSL副本本次新增/变更的19个关键工程文件逐字节与Windows核对一致，隔离shell脚本仅在Linux副本规范化为LF。最终门禁后未改代码，仅更新文档和归档证据。收据入口复用STEP04封装，所以该封装step_id仍为STEP04；其内部工程门禁实际加载本步源码及4项本步非数据库用例，本页明确此范围，不改写机器收据名称以冒充另一协议。

| 检查 | Windows实际结果 |
|---|---|
| 前置Support复验 | [41项通过](prerequisite-support.xml) |
| PostgreSQL/API/迁移 | [42项通过](windows/postgres-tests.xml)：原18项、本步23项run验收及1项增量迁移保留验收 |
| 后端工程与Support | [65项通过](windows/foundation.txt)，含4项本步连接/慢消费/区间/Worker退出回归 |
| 锁、Ruff、mypy、schema drift | 全部通过；无新增依赖或锁升级 |
| 前端check/build | types/lint/2项unit/Prettier及构建通过 |
| 既有浏览器/HTTPS | [9项](windows/browser.txt)与[1项](windows/https-browser.txt)通过 |
| STEP05实际网关 | [1项浏览器全链](windows/step05-gateway.txt)通过；原生EventSource断流、重放、去重、终态取消、410快照及撤销grant阻断 |
| PostgreSQL重启 | [直接查库](windows/step05-restart-facts.txt)：唯一浏览器run、一次调用、一次主动发起、128条窗口事件仍在 |
| 文档/差异 | 门禁通过；收尾再次检查 |

Python3.12.13、Node22.19.0、pnpm10.28.0；PostgreSQL16.13固定镜像digest见收据。固定fake回答仅用于合成验收；没有真实Provider、SMTP外发或远程发布。Playwright直接操作测试浏览器的HTTP/EventSource消费者，不创建STEP06产品页面。

## 失败与修复

首次TestClient收集因锁定Starlette使用AnyIO弃用别名被warnings-as-errors拒绝，[失败JUnit](step05-first.xml)保留；仅精确豁免此第三方兼容别名，不升级依赖或关闭全部警告。首次运行中取消用例因前例留下queued合成run而claim另一条失败，[失败JUnit](step05-inflight.xml)保留；每个测试身份在结束时退出并终止自己的活动run，修复测试隔离。

完整门禁分别发现旧STEP03的“start不存在”断言和旧工程的“无start路由”断言不再适用，见[首次失败](failure-old-start-assertion/receipt.json)与[第二次失败](failure-old-import-assertion/receipt.json)。现分别断言非法start正文422，以及poison app.worker/app.run_worker后API导入仍成功、无engine/消费者且support默认disabled；没有放宽业务失败断言。最终完整复验通过。

初版可选事件落库异常可能阻断合法启动，现用保存点隔离并以故障注入验证对话仍完成。复核还补齐原deadline/预算持久绑定、消息版本/删除核验、改密停止活动run，以及Worker取消时先等待有界线程结束再释放连接池；最终门禁针对这些代码执行。

WSL准备阶段先因PATH未含既有pnpm失败，见[收据](wsl-missing-pnpm/receipt.json)；随后Windows到WSL副本打包过滤漏掉中文路径文档，文档检查失败，见[收据](wsl-missing-docs/receipt.json)。已复用既有Linux工具并用NUL分隔UTF-8路径重新打包，不放宽门禁。完整最终隔离门禁通过；此前失败保持原样。

## 边界

active_ms为null，报告区间合并不是注意力测量。单进程连接上限不冒充集群配额，本地网关不冒充远程发布。删源通过合成库状态注入验证阻断，不代表STEP07删除/物理清理完成。真实Provider、内容审阅与SMTP保持BLOCKED。153项整体验收不因局部通过而全部完成。

最终状态：**COMPLETED（S1-STEP05四项隔离合成工程交付）**。本步代码/数据库/API/实际网关与对应局部验收完成，无阻塞本步fake域的未解决项。live域继续BLOCKED。最早尚未实施的是S1-STEP06，本轮未推进。

## 2026-09-25 审查修复复验

修复运行中模型调用跨过deadline时误记`cancelled/source_unavailable`、合法的124–128字符`client_message_id`使发送事件键超出数据库列宽，以及关闭fake执行后无法重放已持久化start的问题。新增真实PostgreSQL回归覆盖运行中超时、123/124/128字符边界和disabled模式下的同key重放；原有来源核权与新启动503测试仍通过。

重新执行`check_step05.py`隔离合成门禁，50项PostgreSQL/API/迁移、65项非数据库后端、前端check/build、9项既有浏览器、1项HTTPS、1项STEP05实际网关、数据库重启持久化及文档/差异检查均通过；本次未重跑WSL内核隔离门禁。本机新收据位于忽略目录`.artifacts/psyevo-step05-7d26c399e751/receipt.json`；上文2026-09-24归档收据保持其原始代码与验证范围。
