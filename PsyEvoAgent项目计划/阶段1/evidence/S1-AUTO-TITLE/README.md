# 阶段1新增增强：对话自动标题

日期：2026-09-28。关联F-CHAT-002、S1-A04；这是STEP08关闭后用户确认的新功能，历史收据和阶段2顺序不变。

## 实现

- `backend/app/titles.py`在普通聊天成功后为默认标题排入唯一后台任务；选择最早有效的已完成消息对，复用Provider适配器，单次生成简短主题。
- `i009_conversation_titles`增量迁移保存标题来源、独立修订、状态及无正文任务。旧自定义标题按手动标题保护；旧默认标题在后续成功聊天时补充，不批量调用模型。
- Worker分别处理支持回复和标题；标题调用有独立预算和回执，不阻塞回复。失败保留默认标题、不自动重试；已开始但结果未知的任务过期后不会重发。
- 手动命名优先；来源修订、删除或手动改名使迟到结果失效。自动命名不改变会话内容版本；删除清理移除任务，全部模型调用仍参与外部删除状态判断。
- 前端Query同步详情/列表/搜索，有限轮询并复用跨标签页通知；改名增加标题修订校验，冲突刷新后保留用户输入，允许再次保存。

## 验证状态

**状态：已实现，Windows隔离工程门禁通过；真实模型标题效果未验证。** 最终[收据](windows/receipt.json)为`passed=true`，原产物目录`.artifacts/psyevo-step07-84fc2662f818`。

实际命令：根目录执行`backend/.venv/Scripts/python.exe -X utf8 scripts/check_step07.py --web-port 3157 --api-port 8157 --tls-port 3497`，退出0。

| 验证 | 结果及证据 |
|---|---|
| 隔离PostgreSQL/API/增量迁移 | [87项通过](windows/api-migrations.txt)，含新增标题任务和受控SDK测试；[schema drift通过](windows/schema-drift.txt) |
| 后端受控回归 | [111项通过](windows/foundation.txt)，类型、lint和格式检查通过 |
| 前端 | [check通过](windows/frontend-check.txt)，[build通过](windows/frontend-build.txt) |
| 真实浏览器与同源网关 | 共21项：基础9、HTTPS 1、运行网关1、[支持/导航6](windows/step06-browser.txt)、[历史4](windows/step07-browser.txt) |
| 数据库重启 | [标题/偏好持久化及唯一调用](windows/step06-restart-facts.txt)、[历史删除事实](windows/step07-restart-facts.txt)通过 |
| 文档 | 32份正文、2247条本地链接检查无错误；diff空白检查通过，收尾文档另行复查 |

新增测试覆盖格式策略、持久化/检索、手动命名与删除竞态、消息来源失效、失败/重启、重复投递、旧会话补标题和增量迁移。受控SDK传输测试使用实际适配器与合成回包，无真实网络模型请求。[桌面对话](windows/chat-desktop.png)、[首页列表](windows/navigation-home-desktop.png)、[移动端设置](windows/navigation-settings-mobile.png)截图已人工核对相同页面的前一轮产物；最终同路径截图保留供复核，页面自动断言通过。

中间门禁`.artifacts/psyevo-step07-298ffa253107`通过86项数据库/API/迁移、111项后端测试及5项支持页面检查；导航测试因精确标签选择器无法匹配字号下拉框失败，已改为可访问角色定位，须以后续完整收据为准。更早的`.artifacts/psyevo-step07-04ef9a07d3de`停在Worker关闭测试，原因是新增标题消费分支未接测试替身，已修正；不将这些失败收据记为整体通过。

`.artifacts/psyevo-step07-2f2c95e1830a`通过87项数据库/API/迁移、111项后端和6项支持页面测试，历史页面测试在重新生成后等待旧按钮实例失败；快照显示新回答已完成、操作面板已重新收起。测试改为核对新run的API终态后刷新快照并展开当前面板，保留产品的折叠行为。

## 使用与边界

先在目标环境按既有升级流程执行`uv run --no-sync alembic upgrade head`（backend目录），再启动原API和独立`python -m app.worker --support`。本次自动验证只迁移随机隔离合成数据库，未操作开发或生产数据。

配置继续由`app.config.load_settings`读取进程环境，未增加密钥文件读取或浏览器配置。fake模式标题是明确的合成测试主题；live模式复用已配置模型且继续受既有独立合成数据库限制。不扩大development/live/练习门禁，不自动发送SMTP。

真实模型标题效果尚未验证，本次没有付费模型调用。有限格式/内容规则不能证明通用姓名、敏感信息或诊断语义识别能力。原STEP08付费页面测试先设置手动标题，保持两次support调用；新增标题效果必须单独显式验证，不借用历史live收据。未执行新的WSL隔离检查或发布。

合同：[02](../../02-技术方案与实施计划.md#conversation-auto-title-contract)；验收：[03](../../03-测试与验收标准.md#conversation-auto-title-acceptance)；实施：[04](../../04-分步实施与检查清单.md#conversation-auto-title-work)。
