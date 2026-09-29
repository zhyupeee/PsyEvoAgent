# 模型设置审查修复

日期：2026-09-29。阶段1增量修复；既有 verification 收据保留原样。

## 修改

- 标题入队通过 `VersionBinding` 读取旧执行绑定，缺少 `provider_ref` 时使用既有默认值；不改写历史绑定。回归覆盖旧会话继续回复、助手消息提交与标题任务创建。
- 连接测试在身份、版本及活动运行校验后捕获配置并提交事务，再调用 Provider。真实 PostgreSQL 回归在探测回调中以独立事务对同一 owner 执行 `FOR UPDATE NOWAIT`，并验证配置修改不改变已捕获的探测配置。
- live 运行在创建执行、消息与凭据快照前检查所选 Provider readiness；无官方密钥时返回 `503 provider_configuration_unavailable`，草稿不变。覆盖默认官方与显式官方模式，既有个人模式无官方密钥用例继续通过。

## 本次验证

测试使用本次新建的 disposable PostgreSQL 16.13 容器及合成数据库；未调用收费 Provider 或发送 SMTP。

| 命令（backend 工作目录） | 结果 |
|---|---|
| `uv run pytest` | 136 passed，104 deselected |
| `uv run pytest -m postgres tests/test_title_tasks.py tests/test_model_settings_api.py` | 23 passed |
| `uv run python ../scripts/check_model_settings.py` | 1 项实际页面旅程通过，受管理 API/Worker 正常退出 |
| `uv run ruff check app tests` | 通过 |
| `uv run mypy` | 63 个源文件通过 |
| `uv run ruff format --check app/titles.py app/model_settings_api.py app/runs.py tests/test_title_tasks.py tests/test_model_settings_api.py` | 5 个文件通过 |
| `git diff --check` | 通过 |

测试环境通过 `PSYEVO_TEST_DATABASE_URL` 显式指定隔离库，迁移使用同库的 `PSYEVO_DATABASE_URL` 与 `PSYEVO_ENV=test`。页面运行日志在 `.artifacts/model-settings-validation/browser.txt`。

中间验证：初版锁测试按模型名查找账号，在共享合成库中误选其他账号；已改为当前 run 的 owner。随后页面 Worker 与 API 测试并行共用测试库造成两项队列领取断言失败；页面退出后，在另一新建合成库独立复跑上述 23 项全部通过。没有将这两轮失败算作通过证据。

本次未执行完整 PostgreSQL 套件、真实 Provider 或完整 Windows/WSL 门禁；不改变既有阶段及发布边界。
