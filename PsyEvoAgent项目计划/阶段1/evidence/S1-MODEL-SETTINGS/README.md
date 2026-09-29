# S1-MODEL-SETTINGS：模型来源与自动配置

日期：2026-09-29。阶段1工程增强，不推进阶段2。

## 实现

- 设置 → 模型配置：官方模型或每账号一组个人 OpenAI Chat Completions 兼容 API；支持保存、显式合成测试和确认删除。
- 独立 Fernet 主密钥保存在忽略的 `.env.local.json`，数据库只存密文，绑定 owner 和用途；浏览器不回显 Key、不保存到 localStorage。
- 每次已接受运行保存私有加密配置快照；聊天和来源标题从同一快照取模型、地址、凭据。新配置不重启 API/Worker，不修改在途调用，不隐式回退官方。
- 官方 `.env.step08.ps1` 由显式开发入口启用读取，500ms 轮询/防抖；独立 PowerShell 子进程使用私有管道，非法保存继续使用最后有效配置。显式 `-MaxOutputTokens` 才覆盖文件。
- `app.dev --support-worker` 管理独立 Worker、源码重载及退出；旧 Worker 按仓库、命令和开发数据库精确识别。API import 不启动消费者。
- 自定义地址只允许公网 HTTPS，连接到校验后的数字 IP，保留原 Host/SNI 与证书校验，关闭重定向和环境代理；拒绝私网、混合 DNS 和地址转换范围。
- 删除个人配置清除当前及历史个人密文，撤销相关在途任务与待生成标题；会话删除清除对应运行快照。
- `i009` 后追加 `j010_provider_settings`；有配置/快照时拒绝破坏性 downgrade。

## 验证进度

- 后端136项常规测试通过；前端 check 和 build 通过。
- 29项定向 PostgreSQL/实际 SDK 替身测试通过，包括配置版本绑定、标题、撤销和多轮。
- 首轮全量数据库：97 passed / 1 failed。失败为新绑定测试单次领取全局标题队列可能拿到其他测试遗留任务；已限定该测试任务，队列语义仍由既有 title_tasks 测试覆盖。最终复验单独记录。
- 页面实际登录、保存、刷新恢复、密钥不回显、切换、删除及移动端检查通过；API/Worker 在 stdin EOF 后均退出。Windows 后代进程退出增加最多5秒等待，仍对存活进程断言失败。
- 独立真实聊天合成 PoC：`glm-5.2-200k` passed，input/output/total=125/43/168。标题适配器格式/usage检查通过，104/80/184；不将独立适配器检查称为完整网页旅程。
- 当前产物：`.artifacts/model-settings-validation/`。最终结果以完成后追加记录为准。

## 边界

无发布，无真实用户消息重发，不改历史失败 run。测试按钮发送固定合成内容，可能收费且不自动重试。无专业内容/临床验证；标题失败仍保留默认标题，手动标题优先。加密主密钥不可丢失；存在密文时初始化器拒绝另造新密钥。

## 最终复验

**当前工程结果：通过。** [机器收据](verification/receipt.json)记录本次隔离验收。

- [136项后端测试](verification/backend.xml)与[100项PostgreSQL/API/迁移测试](verification/postgres.xml)全部通过；mypy、Ruff lint/format通过。
- 前端check（类型、Lint、7项启动入口测试及5项前端单元测试、格式）和build通过；[页面旅程](verification/browser.txt)验证实际登录、保存/恢复、模式切换、删除与无密钥回显，[移动端截图](verification/model-settings-mobile.png)已目视检查。API与Worker受监督退出通过。
- [真实完整API/独立Worker链路](verification/live-journey.json)：新建隔离合成账号与会话，`glm-5.2-200k`回答completed，AI标题succeeded（6字符）；两次调用，私有加密配置绑定存在，监督进程与Worker均正常退出。此项通过不等价于任意自定义供应商兼容。
- 当前本地开发库已增量迁移并启动新监督进程，旧独立Worker已退休，健康接口200；没有删除原数据或重发原失败消息。
- 文档检查通过（32份阶段文档、153项既有验收定义保持不变）。真实模型检查未发SMTP、未公开发布、未进入阶段2。
