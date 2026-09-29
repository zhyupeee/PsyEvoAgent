# STEP08 内部实验工程验收收尾（2026-09-28）

执行者：本轮Codex。基线为`f783572`加用户已暂存的STEP08实现；未重置、提交或覆盖暂存区。用户确认采用[工程完成标准](../../03-测试与验收标准.md#step08-engineering-scope)，专业审阅模板删除；历史证据保留。本文是当前状态入口，前两轮README/continuation是历史时点。

## 本轮闭环

- 已补内部流协议检查：错误choice索引、SDK丢弃的畸形tool标记、终止后的新增正文、冲突/提前usage均受控停止；相同终局usage计数去重，不回传未审候选。
- 完成事务写入失败回滚正文和事件；commit成功但回执丢失时读取原completed，不追加正文或再调用；模型/Provider配置漂移在网络前失败。
- 真实SMTP复用SMTPMailer；一封固定测试邮件经TLS鉴权发送后，用户回传邮件独有标识，散列匹配确认实际送达。邮件不创建账号，测试标识不是注册/登录验证码。
- 无新数据库迁移、业务API、Agent循环或Worker。Full Buffer Review保持唯一启用公开路径。取消专业审阅门槛不改变live隔离合成库和未审练习test-only限制，不发布服务。

**最终状态：COMPLETED（S1-STEP08内部实验工程验收）。** .1整稿真实模型/SMTP与故障边界通过，.2逐例矩阵完成，.3合同冻结，.4共同来源与限制交接完成。下一步最早未实施为S2-STEP01，本轮未进入阶段2。此结论不代表专业心理支持质量、临床有效性、公共安全分块或远程部署通过。

## 最终执行与冻结

根目录显式加载本机Provider配置后执行`backend/.venv/Scripts/python.exe -X utf8 scripts/check_step08.py --live --web-port 3108 --api-port 8108 --tls-port 3448`。本地目录`.artifacts/psyevo-step07-7de628ba3bf0/`沿用旧前缀，收据step_id为S1-STEP08。36个命令全部退出0，随机合成容器清理成功。Python3.12.13、Node22.19.0、pnpm10.28.0、PostgreSQL16.13固定digest；既有锁未升级。

| 最终范围 | 实测证据 |
|---|---|
| 完整门禁 | [收据](closeout/windows/receipt.json)passed；历史失败分列保留 |
| 真实PostgreSQL/API/迁移 | [74项通过](closeout/windows/postgres-tests.xml)，包括4项新增live事务故障/配置漂移；未访问开发库 |
| 后端与前端工程 | [92项后端](closeout/windows/foundation.txt)，Ruff/格式/mypy/锁通过；[前端check](closeout/windows/frontend-check.txt)及[build](closeout/windows/frontend-build.txt)通过 |
| 前置页面 | [9项身份/工程](closeout/windows/browser.txt)、[1项HTTPS](closeout/windows/https-browser.txt)、[1项SSE](closeout/windows/step05-gateway.txt)、[5项资源/对话](closeout/windows/step06-browser.txt)、[4项历史/删除](closeout/windows/step07-browser.txt)通过 |
| 真实Provider旅程 | [1项通过](closeout/windows/step08-live-browser.txt)：SSE=快照=DOM，刷新不重新调用、跨owner拒绝、取消后零回答、确认删除后不可读 |
| 重启与账本 | [持久事实](closeout/windows/live-facts.json)：成功settled/1720 token，取消cancelled/actual=null，各一次调用；费用仍null。在线删除完成、远端删除unknown不随重启改变；[无正文诊断](closeout/windows/live-diagnostics.json)保留 |
| 最终源码 | [147个工程文件](closeout/windows/source-verification.json)与收据hash全部一致；之后只更新文档/归档证据 |

本次真实合成页面截图归档在closeout/windows/live-chat.png与live-deletion.png。页面测试不冒充专业评价；SMTP运输单独实测，不等价真实邮箱业务注册全流程。本步无持久checkpointer、应用备份/恢复或真实部署，明确未配置/未验证。

最终文档检查32份/153项定义与本轮`git diff --check`通过，交接manifest和147个工程文件hash核对通过。另做`git diff --cached --check`发现用户此前暂存的continuation/browser-cookie-failure/step08-live-browser.txt第7/23行原始失败日志有尾部空格；未改写历史日志或暂存区。本步未提交Git，暂存日志格式提示不混称新增业务失败。

## 验收与交接入口

- [21项工程验收矩阵](engineering-matrix.md)：沿既有编号，工程结果与专业未验证部分分开。
- [阶段2合同交接](stage2-handoff.md)：仅阶段1产物交付，不实施阶段2。
- 真实SMTP与fake邮件验收分列；专业内容、临床效能、供应商地区/保留/价格/远端删除仍未验证。

## 已取得的独立证据

| 检查 | 结果及边界 |
|---|---|
| SMTP真实运输与收件确认 | [收据](closeout/smtp/receipt.json)：smtp_accepted=true、delivery_confirmed=true、status=passed；用户回传12位测试标识散列匹配。仅一封测试邮件，不创建账号。配置/运输源码与最终版本[一致](closeout/smtp/final-source.json)，探针随后只重命名局部变量 |
| 协议修复后真实PoC | [收据](closeout/usage-poc-passed/receipt.json)：89块、一次调用、终局重复usage只计一次，actual_tokens=1934、actual_cost=null。不是公共安全分块或专业审阅证据 |
| WSL最终内核隔离 | [封装收据](closeout/wsl-final/receipt.json)、[工程收据](closeout/wsl-final/engineering.json)：92项后端、5项工程浏览器、锁/格式/类型/build与IPv4/IPv6 TCP/UDP、原生curl、WSL互操作拒绝通过；额外[41项Support](closeout/wsl-final/runtime-tests.txt)通过 |
| WSL源码一致性 | [50个后端文件](closeout/wsl-final/source-verification.json)与宿主忽略CRLF/LF后逐项一致；原收据STEP02/04 ID保留，不冒充live/数据库全链都在WSL内核隔离 |

前一次WSL通过收据在closeout/wsl保留，对应usage去重修复前版本，最终结论只取wsl-final。真实SMTP和Provider不进入禁外连PR门禁。

## 失败与处置

首次启动完整门禁时Docker引擎未运行，保留`.artifacts/psyevo-step07-415c71f46c9d/receipt.json`；启动现有Docker Desktop后使用随机合成数据库重新执行，没有重置开发数据。SMTP探针类型检查发现分支局部变量重复声明，重命名修复，不影响此前真实运输/送达事实。随后SMTP探针负例和收件确认行为另以受控测试验证。

前序真实模型token上限失败、Cookie测试错误、格式及WSL准备失败见[历史续作](continuation.md)与[首次切片](README.md)，不删除或改写失败分母。

本轮首个完整live页面门禁失败于终局usage重复检查，保留[失败收据](closeout/usage-browser-failure/receipt.json)，其74项DB和91项后端已通过，但不能记完整门禁通过。进一步PoC分别观察[partial_stream](closeout/usage-failure-1/receipt.json)、[duplicate_usage](closeout/usage-failure-2/receipt.json)、[conflicting_usage](closeout/usage-failure-3/receipt.json)；[无正文诊断](closeout/usage-failure-4/receipt.json)显示供应商两次input/output/total完全相同，仅可选细分字段不同。修复为三项权威计数相同去重、不同拒绝，并新增细分字段变化反例。修复后真实PoC通过：89块、重复usage报告1次，input1313/output621/total1934仅结算一次。

历史适配器可能将重复终局usage相加，因此历史收据中的总token只保留为当时SDK观察值，不再当作精确供应商账单；不回写旧收据或旧账本。本轮真实费用仍unknown。新增`tests.live_diagnostics`在临时库清理前导出无正文live终态/调用元数据，成功失败均保留；不能因清理容器而丢失后续失败原因。
