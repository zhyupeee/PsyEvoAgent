# S1-STEP03.5 邮箱身份与品牌实施记录

日期：2026-09-23。仅第一阶段STEP03，包括STEP03.5；不实现其他STEP功能，不发布远程服务，不向真实邮箱发送邮件。

## 已实现

- 邮箱验证码注册、邮箱密码登录、验证码找回和登录后改密；发码不创建账号，验证后事务性创建账号、偏好与会话。
- 邮箱规范化与唯一性，验证码用途隔离、10分钟、5次尝试、单次消费、60秒重发及小时限额；保留PBKDF2、8小时会话、Origin/CSRF与账号隔离，改密撤销全部旧会话。
- `f033_email_identity`增量迁移保留旧账号、哈希及关联记录；旧用户名登录和provision停用。旧用户名迁移测试使用旧表结构，不伪造邮箱。
- 注册、登录、首页、账号、健康页复用现有蓝色Logo，新增找回/改密、移动端和键盘状态；根路由接入ICO、PNG、Apple图标及manifest。资源位于`frontend/public/`，无新增UI依赖。
- SMTP从显式进程环境读取，TLS验证证书；测试工厂注入隔离替身，正常API不提供取码接口。密码通知失败只记录脱敏状态，不恢复旧密码或会话。

## 本次已执行验证

最终Windows独立门禁执行目录：`.artifacts/psyevo-step03-fd32dae8f9c0/`，归档见[收据](windows/receipt.json)。所有数据库测试使用本次随机容器的合成check/migration数据库，与开发库分离，容器已清理。

| 检查 | 实际结果 |
|---|---|
| uv锁、Ruff lint/format、mypy | 通过 |
| 空库迁移、schema漂移 | 通过 |
| PostgreSQL API、验证码并发、会话撤销、历史迁移与清理事务回归 | 17项通过 |
| 非数据库工程测试 | 20项通过，含SMTP两种TLS模式的隔离替身检查 |
| 前端pnpm check | 类型、lint、2项单元测试与格式检查通过 |
| pnpm build | 通过；Zod依赖注释有非阻塞Rollup提示 |
| 浏览器STEP03/健康页 | 8项通过 |
| 本地同源HTTPS | 1项通过，含安全Cookie、Origin拒绝及图标资源 |
| PostgreSQL重启后的账号、偏好与无伪造consent | 通过 |
| 构建预览 | `/health`、`/login`、favicon及Apple图标HTTP 200；页面标题与品牌实际加载 |
| 浏览器标签图标 | 通过Chromium实际favicon缓存取得32px品牌图标并目视核对；不是仅检查link标签 |

已目视核对[桌面注册](register-desktop.png)、[手机错误状态](register-mobile.png)、[账号改密](account-desktop.png)和[浏览器缓存图标](browser-favicon.png)。账号截图等待实际账号标题后捕获。构建预览注册截图使用合成401会话替身，只证明页面及真实静态资源，不作为后端身份验收；[构建浏览器记录](built-browser.json)单列此边界。

最终完整门禁在文档检查处返回非零，仅有2个基线历史截图缺失，没有新增缺链。既有缺失为`privacy-desktop.png`与`privacy-mobile.png`；不伪造截图、不改写旧收据，也不将总门禁标为全部通过。

WSL在独立Linux工作副本、Linux依赖和内核网络命名空间中执行。首次发现既有`dev_instances.py`的`os.name`判断无法让Linux mypy排除Windows专属socket常量；改为等价的`sys.platform`判断，不改变启动行为或新增功能。修正后Windows类型检查及4项启动测试通过；WSL复测内核隔离探针、Python/Node外连拒绝、Ruff/mypy、20项工程测试、前端类型/lint/2项单元测试/build、5项工程浏览器回归和STEP01材料检查全部通过，仍仅文档缺图失败。见[WSL输出](wsl-isolated.txt)与[原始收据](wsl-receipt.json)。WSL工程入口不包含PostgreSQL业务验收，后者由Windows独立STEP03门禁提供。

## 本机开发库维护

先只读预检Compose标签、loopback绑定、实际库名/数据库角色、全部表及外键，再在独立事务中锁定并复核行数。目标为`127.0.0.1:55432/psyevo_synthetic_dev`，数据库角色`psyevo`，仅`email IS NULL AND username IS NOT NULL`账号。

| 表 | 预计清理 | 实际清理 |
|---|---|---|
| users | 1 | 1 |
| user_preferences | 1 | 1 |
| identity_sessions | 1 | 1 |
| context_grants / deletion_jobs / runs / conversations / consent_records / idempotency_records | 各0 | 各0 |

清理与增量迁移分开执行，无删卷，其他环境未操作。[维护收据](local-maintenance.json)来自`.artifacts/step035-local-20260923T130942949002.json`。已创建普通开发账号`admin@psy.com`，随机密码保存在Git忽略的`.env.step03-account.json`，不在本记录展示；使用合成邮件替身完成同一注册流程，不代表真实邮箱控制权验证，无管理员特权。

## 仍未完成与边界

- 真实SMTP主机、端口、发件人、认证账号/密码、TLS模式和独立验证码密钥尚未提供；未执行真实外发。配置变量见[开发说明](../../../../../DEVELOPMENT.md)。
- 未发布HTTPS站点，没有实现对话、记忆、练习、研究或其他STEP能力，153项业务验收仍不因本次局部工程检查而全部完成。
- Windows数据库门禁与WSL内核隔离检查各自记录，总状态均保留文档检查失败。
- 历史收据和两张缺失截图保持原样；本次记录与新截图使用独立目录。
- 最终工作区`git diff --check`通过；原有暂存区`EXPERIMENT.md`末尾空行仍使`git diff --cached --check`返回非零，保留用户暂存内容，未重写索引。详见[最终检查](final-checks.json)。
