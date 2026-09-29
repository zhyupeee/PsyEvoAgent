# 第一阶段同会话多轮聊天增量

2026-09-28用户授权：实现ChatGPT式会话列表与连续消息区，并一起实现同会话有效前文。范围只在阶段1；STEP08历史收据保持原样。

已实现分页时间线、有效主分支合并、会话侧栏与移动端展开、Worker成对前文选择与来源复核、live聊天32768预算和整轮截取。无数据库迁移，无新依赖，无阶段2记忆或跨会话召回。

## 2026-09-29聊天操作调整

后续布局调整已完成：“查看旧版本”移到标题右侧的小型菜单，展开为独立浮层，无有效旧分支时完全隐藏。history接口增加`old_only=true`，分页前筛选旧分支、跳过失效来源，不遗漏更早版本。完整Windows门禁再次通过（93项数据库、121项后端、23项浏览器及前端check/build），验证无分支入口隐藏、修订后标题栏入口和消息区无历史面板；测试容器已清理。见[布局调整收据](old-versions-menu/receipt.json)、[桌面](old-versions-menu/history-desktop.png)、[手机](old-versions-menu/multiturn-mobile.png)。下方保留前一轮交互记录。

有效历史继续直接显示在聊天区，“查看旧版本”仅显示被修订或重新生成替代的分支。最新轮次状态和操作放回对应消息下方，“重新生成”改为直接可见的小按钮。移除常驻的“查询运行状态”；发送或停止未确认时显示“检查发送状态”，提供等待和结果提示，避免重复查询相同状态却没有可见反馈。检查不调用模型，重新生成仍需主动点击。

浏览器回归增加start请求未送达后的状态反馈与幂等重试，保留回执丢失后的恢复、连续消息分页、刷新、失败/取消和旧版本隔离。仅使用隔离合成数据库与fake Worker；未重发私人消息或新增真实Provider调用。此前真实模型验证限制保持不变。

最终Windows门禁通过：93项数据库/API/迁移、121项后端、23项浏览器（含8项聊天及4项历史/删除），前端check/build、文档及数据库重启直查通过。见[本次收据](interaction/receipt.json)、[聊天用例](interaction/step06-browser.txt)、[历史用例](interaction/step07-browser.txt)、[桌面](interaction/chat-desktop.png)和[手机](interaction/multiturn-mobile.png)。原始目录为`.artifacts/psyevo-step07-48da7902edca/`，测试容器已清理。前两次回归暴露的测试滚动干扰、装饰图标混入按钮无障碍名称均已修正；本次未重跑WSL，下文WSL结果为上一轮记录。

## 已验证与限制

- 93项隔离PostgreSQL/API/迁移、121项后端单元测试通过；受控真实SDK捕获system/user/assistant/user顺序、整轮裁剪及当前消息超限，数据库覆盖分页、修订草稿替代、跨账号、撤销、删除及运行中版本变化。前端检查、5项单元测试、7项启动脚本测试、生产构建通过。
- 22项真实浏览器检查通过（9基础/身份、1 HTTPS、1 SSE网关、7聊天、4历史/删除）。聊天新增21轮真实fake Worker连续发送、默认20轮分页、滚动锚点、手机会话切换、超fake预算失败与刷新。修订、重新生成、跨标签页及确认删除回归通过。
- WSL内核隔离工程与Support检查通过，见[工程收据](wsl/engineering.json)及[运行收据](wsl/receipt.json)。仅源码和既有Linux依赖复制入独立验证目录，无Provider凭据。旧门禁探测首页200与现有首页重定向冲突，已改为探测现有`/health`页面；内核隔离不降级。原脚本收据内阶段名/限制文字是复用入口的历史标签，不扩展本次验证范围。
- **真实两轮验证未通过**：本机ignored配置实际选择`gemini-3.1-flash-lite-preview`。第一轮在7593ms后返回`provider_error`，actual usage未知，保留32768预占；第二轮未执行，没有自动重试或替换模型。见[实际调用元数据](live-failed/actual-provider-call.json)和[失败门禁收据](live-failed/receipt.json)。不得将受控SDK的成功结果当作真实供应商多轮观察。未暴露密钥或使用私人对话。

纯合成完整门禁已通过，见[Windows最终收据](windows/receipt.json)：`.artifacts/psyevo-step07-1b9a9540f88d/receipt.json`。数据库重启后消息、修订版本、单轮调用、反馈及删除清理事实通过原STEP05/06/07直查；隔离测试容器已清理。页面截图：[桌面](windows/multiturn-desktop.png)、[手机](windows/multiturn-mobile.png)。文档链接/结构检查及diff检查通过。

此前失败及定向调试门禁保留在.artifacts目录；本记录不会覆盖STEP08历史收据。本次未发布、未发邮件、未修改开发数据库正文，未实现阶段2能力。产品实现完成；真实供应商多轮效果尚待该供应商调用恢复后另行显式验证，不能标为本次全部验收通过。
