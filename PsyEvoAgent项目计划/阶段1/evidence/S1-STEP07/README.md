# S1-STEP07 历史修订、删除与反馈

后续三项P2评审修复及独立复验见[评审修复记录](review-fixes.md)；下文保留原交付时点。

日期2026-09-27；基线`b7ddd0e`，开始时Git工作区干净。仅实施STEP07，未进入STEP08或后续阶段。**COMPLETED（3项隔离合成工程交付）**；此结论不代表真实模型、专业内容或整阶段验收完成。

## 前置核对

STEP06实际代码为对话/偏好/资源页面、`pages.py`读模型，复用STEP05 run/SSE/独立Worker；无本步历史修订/反馈/删除执行。历史最新评审收据为54项PostgreSQL/API/迁移及5项STEP06页面通过，不把历史收据当本轮执行。

本轮先实跑`check_step06.py --web-port 3106 --api-port 8106 --tls-port 3446`：[首轮](preflight-docker/receipt.json)Docker引擎未启动，启动后发现[style.css格式门禁失败](preflight-format/receipt.json)；格式工具处理后，[完整前置门禁通过](preflight/receipt.json)。此预检期间开始增加STEP07文件，因此不以其结束时源码hash声明精确基线覆盖；最终STEP07门禁完整重跑全部前置，且逐文件核对最终源码。真实Provider配置/适配、专业内容审阅与SMTP仍未满足，不阻塞STEP07隔离合成域；真实模型由STEP08.1接入。

## 实现与边界

见[实现合同](../../02-技术方案与实施计划.md#s1-step07-implementation)和[验收协议](../../03-测试与验收标准.md#s1-step07-validation)。复用现有运行与身份存储；新增feedback/run_branches两张表的追加迁移、删除执行和回执、本人会话/历史/分支读模型及可选反馈。前端Query/Form/Zod接真实API，无新依赖或运行框架。

删除确认→持久屏障及取消→逐项独立事务清理→真实回执；正文清空，事件/反馈移除，来源停止使用；用量元数据、去重摘要及无正文墓碑保留。原LangGraph未配置持久checkpointer、应用未配置备份/真实Provider，本步明确为N/A，未伪造其清理证据。失败仍保留在线阻断，无法全部完成就显示剩余项。无远程发布、开发库迁移或开发数据清理。

## UI参考与差异

实际读取学生端S04反馈原图；采用回答后的自愿反馈、帮助度/误解纠正、可空补充说明与明确取消。复用STEP06蓝白主题及44px控件，以原生details减少首屏负担，原生dialog提供删除确认、Escape及焦点；窄屏会话列表采用可折叠区，不复制三栏挤压正文。未接入图中的后续记录能力、研究工作台或自动偏好修改。

## 最终验收与证据

根目录实际执行`backend/.venv/Scripts/python.exe -X utf8 scripts/check_step07.py --web-port 3107 --api-port 8107 --tls-port 3447`，[最终收据](windows/receipt.json)所有命令退出0。使用随机独立合成PostgreSQL容器，最终清理成功；未操作开发库。Python3.12.13、Node22.19.0、pnpm10.28.0及固定PostgreSQL16.13镜像沿既有门禁。最早未完成步骤为**S1-STEP08 全阶段联调及交接**，本轮未实施。

| 范围 | 实测结果与证据 |
|---|---|
| 数据库/API/迁移 | [65项通过](windows/postgres-tests.xml)：前置54项、本步9项及新增2项迁移；空库、增量保留/复跑/drift、拒绝有损回退、owner隔离、失败清理重试、运行中删除及unknown用量、来源传播、修订上下文与去重 |
| 后端工程 | [66项通过](windows/foundation.txt)；Ruff/format/mypy/锁通过，新增旧start fingerprint兼容测试；不改写原请求摘要 |
| 前端 | [check](windows/frontend-check.txt)与[build](windows/frontend-build.txt)通过；check包含7项启动器与2项前端unit |
| 本步页面 | [3项真实页面通过](windows/step07-browser.txt)：空理由反馈失败/丢回执重试、真实唯一ID；搜索/归档/修订/重新生成及刷新历史；手机删除/Escape/默认焦点、双标签清理、丢回执同key重试、退出/返回/重新登录阻断 |
| 前置页面 | [9项身份/工程](windows/browser.txt)、[1项HTTPS](windows/https-browser.txt)、[1项实际SSE网关](windows/step05-gateway.txt)、[5项STEP06页面](windows/step06-browser.txt)通过 |
| 数据库重启 | [本步直接查询](windows/step07-restart-facts.txt)：反馈唯一且无全文、偏好未被反馈改写、修订版本2/3各一次调用、已删正文/事件不可用且回执持久；STEP05/06重启事实也通过 |
| WSL内核隔离 | [原STEP04封装收据](wsl/receipt.json)与[工程收据](wsl/engineering.json)通过；66项后端、工程浏览器及额外[41项Support](wsl/runtime-tests.txt)。IPv4/IPv6 TCP/UDP、原生curl及WSL互操作拒绝；[普通环境负例](wsl-negative.txt)预期退出1，不允许降级 |
| 源码与文档 | [135个工程文件](source-verification.json)逐一匹配Windows最终收据；WSL除CRLF/LF外一致。32份阶段文档、153项定义及链接/表格、git diff --check通过 |

WSL沿用`--step04`封装，保留机器收据原step_id及历史limitations，不改名冒充STEP07数据库页面的内核隔离。实际装配包含本步源码；数据库/API和本步页面由Windows门禁执行，两域分列。检查点N/A同时由实际`graph.checkpointer is None`断言验证，未伪造检查点失败收据；本步在线清理失败通过真实执行函数故障注入验证。

已查看[桌面反馈](windows/feedback-desktop.png)、[桌面历史](windows/history-desktop.png)、[手机删除确认](windows/delete-mobile.png)与[手机删除回执](windows/deletion-receipt-mobile.png)。视口检查不冒充实体手机软键盘测试。合成截图只含测试文字和不透明ID；不归档测试邮件目录、凭据或证书私钥。

## 失败记录与修复

- [首轮API](failure-api/receipt.json)：更新追加表清单；fake测试显式关闭缓存；允许未发送旧draft的纯标题编辑但仍使其旧grant失效，运行中编辑仍拒绝。
- [类型检查](failure-types/receipt.json)：对JSON账本元数据先检查数值类型，不用类型绕过。
- [键盘首轮](failure-keyboard-first/receipt.json)、[二轮](failure-keyboard-second/receipt.json)：输入等待身份/会话就绪，测试等待输入框及发送按钮可用后再按Tab；焦点检查保留。
- [导航竞态](failure-browser-navigation/receipt.json)：退出/返回用例等待重定向完成及真实登录表单出现，再重新登录；不吞异常或跳过返回路径。
- 自检修正跨标签通知排除发起页自身，避免重命名后本页不必要重载；新增输入选择器保持STEP05 start序列化完全一致，避免升级后旧幂等请求误判冲突。
- WSL首次因验证副本CRLF启动失败，只规范化副本，不改写宿主源码；最终在同步副本重跑通过。

上述失败收据不覆写；最终完整门禁成功后只做文档/证据归档，没有继续修改工程代码。相关局部用例通过，不推导153项全通过。

## 外部未满足项

- 真实Provider精确配置/适配及能力实测：STEP08.1待实施；用户可提供模型，费用不是blocker。
- 专业支持/练习内容审阅、真实SMTP：BLOCKED（外部条件），不把合成内容或邮件替身当作真实验收。
- 整阶段153项业务验收、真实模型旅程与阶段2交接：尚未执行，不属于本轮STEP07完成声明。
