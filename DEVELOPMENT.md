# 本地工程开发（S1-STEP02/03）

> 当前按[内部实验执行约定](EXPERIMENT.md)推进：可通过指定HTTPS地址分享；目标注册先验证邮箱，登录后直接进入，无年龄或用途确认，不设公众资格、真人告知或期限审批前置。业务不设固定TTL。邮箱身份已实现；真实 SMTP 尚未配置，验证范围见阶段1 STEP03.5 记录。

## S1-STEP03 注册登录与实验入口

本节补充STEP02工程入口。`/register`、`/login`与`/me`已接服务端身份，登录后进入`/`，旧`/me/privacy`跳转账号页。主页只呈现已实现功能；没有聊天入口。API import/reload不建表、不迁移、不启动消费者，连接池在lifespan管理。

数据库依赖为 SQLAlchemy、Alembic、psycopg，精确版本见 `backend/uv.lock`。前端新的业务消费者使用 Query 维护服务端状态、Form + Zod 校验表单，沿用 Start/Router/Tailwind；健康探针保持原实现。路由文件由 Start 生成。

### 数据库与合成账号

Windows 日常启动推荐在仓库根目录执行：

```powershell
# 首次初始化：生成本地密码、启动独立开发库、增量迁移并启动 API
powershell -NoProfile -File scripts/start-dev.ps1 -Initialize
# 后续重启：复用原密码和数据卷
powershell -NoProfile -File scripts/start-dev.ps1
# 第二个终端
cd frontend
pnpm dev
```

打开 `http://127.0.0.1:3000`，未登录时进入登录页，可转到注册页。脚本显式读取根目录 `.env.local.json` 的 `postgres_password`，该文件由 `.gitignore` 排除，不能提交或分享；API 本身仍只读进程变量，不自动读取环境文件。脚本向子进程注入开发库连接及 `PSYEVO_ENV=development`，退出时恢复调用终端原变量；可选 `-PrepareOnly` 只准备数据库和迁移。已有开发数据卷但配置丢失时拒绝生成新密码，应恢复原配置，不能删卷解决。启动脚本不启动前端、Worker或远程代理。

`pnpm backend` 只用于已显式设置 `PSYEVO_DATABASE_URL` 的终端；缺少变量时会立即退出并提示正确入口，避免启动一个健康检查为 200、账号接口却为 503 的 API。Windows 日常开发使用上面的 `scripts/start-dev.ps1`，WSL 按下文显式设置连接变量。

首页若显示服务暂时不可用，先检查 API 终端及数据库配置：`/api/v1/health` 仅证明工程服务存活，不能证明账号数据库可用；`/api/v1/auth/session` 返回 `503 database_not_configured` 表示 API 没有加载连接配置。按上述入口重启后，未登录请求应返回 401，页面可点击“重试”恢复。现有 `55433` 的 `psyevo_synthetic_check` 验收库不用于日常开发。以下手动命令仍可用于 WSL 或显式配置场景。

2026-09-21 首页故障修复验证：实测原接口返回 `503 database_not_configured`；经新入口初始化并复用启动后，3000 同源代理和 8000 API 均返回正常未登录 401，真实浏览器从 `/` 跳转 `/login` 并显示登录表单及注册链接。缺配置、损坏 JSON 两种启动失败检查通过；API 日志未包含本地密码。前端 `pnpm check`、build 通过。独立合成库检查 `scripts/check_step03.py --web-port 3103 --api-port 8103 --tls-port 3443` 的 PostgreSQL 测试 13 项、工程测试 16 项、浏览器 7 项（含新增登录状态失败与重试恢复）、HTTPS 1 项及数据库重启持久化检查均通过；临时测试容器已清理。完整命令最终因既有阶段1实施清单引用的 `privacy-desktop.png`、`privacy-mobile.png` 历史文件缺失而退出非零，不能称为完整门禁通过；未补造历史截图，未执行 WSL 内核隔离门禁。本次本地收据位于 `.artifacts/psyevo-step03-097fc7795b96/receipt.json`，当前页面截图位于 `.artifacts/home-recovery/login.png`，均为本地验证产物，不替代历史业务验收。

根目录的 `compose.yaml` 只启动 PostgreSQL 16.13，镜像固定 digest；不启用 pgvector、Kafka、Redis、对象存储或应用容器。端口 `127.0.0.1:55432`，数据保存在本项目命名卷。先在当前终端设置本地密码变量 `PSYEVO_POSTGRES_PASSWORD`，再运行：

```powershell
docker compose -p psyevoagent up -d postgres
```

API/迁移终端显式设置 `PSYEVO_DATABASE_URL`，形状为 `postgresql+psycopg://psyevo:<URL编码的本地密码>@127.0.0.1:55432/psyevo_synthetic_dev?connect_timeout=3`。不把真实值提交到 Git 或聊天。`app.config.load_settings` 只读进程变量，不自动读 `.env`；运行时接受显式配置的PostgreSQL host和库名，驱动为psycopg；测试模式只接受独立loopback check/migration合成库，拒绝开发库。Compose 的变量替换由 Compose 读取，与 API 的加载规则不同。

在 backend/ 执行：

```powershell
uv sync --locked --group dev
uv run --no-sync alembic upgrade head
uv run --no-sync python -m app.dev
```

第二个终端在frontend/执行`pnpm dev`。注册使用邮箱、邮箱验证码、密码及重复密码；有效验证码提交后创建账号并自动登录。普通登录仅用邮箱和密码；找回与登录后改密均撤销全部旧会话并要求重新登录。新密码6～128位，邮箱去首尾空白并转小写；用户名登录和`app.provision <username>`已停用。Cookie继续Secure/HttpOnly/SameSite=Strict，远程必须HTTPS。

### S1-STEP03.5 邮箱身份与品牌（已实现）

接口与验证码策略见[身份合同](PsyEvoAgent项目计划/阶段1/02-技术方案与实施计划.md#email-identity-target)，本次验证与局限见[独立记录](PsyEvoAgent项目计划/阶段1/evidence/S1-STEP03/email-identity/README.md)。仅完成STEP03；没有新增对话、记忆、练习或其他STEP功能。

API只从显式进程环境读取以下邮件配置，不自动读取`.env`：

| 变量 | 内容 |
|---|---|
| `PSYEVO_SMTP_HOST` / `PSYEVO_SMTP_PORT` | SMTP主机、1～65535端口 |
| `PSYEVO_SMTP_FROM` | 发件邮箱 |
| `PSYEVO_SMTP_USERNAME` / `PSYEVO_SMTP_PASSWORD` | SMTP认证账号及密码/授权码 |
| `PSYEVO_SMTP_TLS_MODE` | `starttls`或`ssl`，验证服务器证书 |
| `PSYEVO_EMAIL_CODE_KEY` | 至少32字符的独立随机摘要密钥，不能复用SMTP密码 |

在API启动终端显式注入这些变量；`scripts/start-dev.ps1`只读取原有数据库本地配置，继承邮件环境，不自动读取邮件秘密文件。缺配置时发码统一503，邮箱密码登录不依赖SMTP。发码失败回滚新验证码；密码提交成功后通知失败只记录脱敏事件，不回滚密码或恢复旧会话。API import/reload不启动邮件消费者。

一次性本机维护工具为`backend/.venv/Scripts/python.exe scripts/step03_local_accounts.py`（默认只预检）。`--apply-cleanup --seed`仅用于本次明确授权的维护，核验Compose服务、loopback端口、实际数据库身份、表和外键，再事务性删除无邮箱的旧用户名账号及关联记录。不要放入启动脚本，不删除数据卷，不对其他环境运行。开发账号用同一注册流程与隔离合成邮箱创建，不代表真实邮箱控制权验证；凭据保存在Git忽略的`.env.step03-account.json`，无管理员权限，不在日志或收据公开密码。重新执行不重置已有邮箱账号密码。

根路由接入favicon、Apple图标和manifest；`frontend/public/brand/`复用设计目录的Logo与favicon，浏览器图标由同一资产生成。注册、登录、首页、账号、健康页统一品牌，工程健康页有独立标题。设计图中的未实现导航和旧默认同意文案不作为产品功能。

2026-09-24 审查修复：新增`g034_login_attempts`增量迁移，将已有账号的暂锁状态带入按规范化邮箱统一保存的登录失败计数；已注册与未注册邮箱均在第5次错密后暂锁1分钟。已有数据库启动更新代码前须先执行`uv run --no-sync alembic upgrade head`。前端验证码发送及冷却时间按邮箱保存，修改邮箱或旧请求晚返回时不会阻塞新邮箱。独立合成PostgreSQL门禁实测迁移与漂移检查、18项数据库测试、20项工程测试、前端check/build、9项浏览器测试、1项HTTPS测试和数据库重启持久化均通过；临时容器已清理。总门禁仍因既有`privacy-desktop.png`、`privacy-mobile.png`两张历史截图缺失而返回非零；本次记录不改写历史收据，也不声称完整门禁通过。本次本地收据位于`.artifacts/psyevo-step03-6764175ff630/receipt.json`。

正常停止仍用 Ctrl+C；数据库可用 `docker compose -p psyevoagent stop postgres` 停止并保留数据。不要在日常重启中执行删卷或重置。`synthetic-local/1`为既有记录兼容标识，实验资料保留至明确删除/清理；业务同意、draft和grant不设置固定期限；仅保留登录8小时安全失效。

### STEP03 检查入口

依赖和 Chromium 准备后，先显式准备锁定数据库镜像：

```powershell
docker pull postgres:16.13-bookworm@sha256:472efd9a66f2b2f1a5aeb18b28de74332e6ef88c2b93a1a5d812fb6db67a5f60
backend/.venv/Scripts/python.exe -X utf8 scripts/check_step03.py
```

门禁拒绝接管已有服务，默认检查3000/8000/3443端口；开发进程占用时可传`--web-port 3103 --api-port 8103 --tls-port 3443`；创建随机命名、带合成标签的独立 PostgreSQL 容器及随机 loopback 端口，只测试合成账号，结束仅删除本次容器及其临时卷。不会连接 Compose 开发库或已有其他项目数据库；不自动拉镜像。执行锁检查、Ruff/类型、空库迁移和漂移检查、真实 PostgreSQL API/迁移失败恢复测试、原工程回归、前端 check/build、真实网关浏览器、数据库重启后保存结果核对及文档检查。收据和各命令输出位于 `.artifacts/psyevo-step03-*/`。

`uv run --no-sync pytest` 默认仅运行无数据库工程测试，真实库用例以 `postgres` 标记分组；必须单独执行 `uv run --no-sync pytest -m postgres`，并显式设置 `PSYEVO_TEST_DATABASE_URL`。缺库变量会失败，不能跳过后声称 STEP03 验收通过。迁移测试仅用于隔离合成库，其 N/N-1 指本 STEP 的基础 schema 与追加所有权约束 schema，不宣称兼容未提供的历史业务产品。

业务浏览器使用 `pnpm exec playwright test --config playwright.step03.config.ts`，需明确隔离数据库、合成账号与`PSYEVO_TEST_MAIL_DIR`，通常由上述门禁统一准备。邮件替身仅在`tests.mail_support:create_test_app`使用，强制test环境、隔离库和.artifacts内收件目录；正常API无读取验证码接口。原 `pnpm test:e2e` 仍为 STEP02 健康页回归。STEP03 门禁继承 Python/Node/浏览器外连保护，**不替代 Linux/WSL 的内核隔离工程入口**。测试输出为合成开发证据，不代表后续功能或完整业务验收。

当前有注册登录、账号页、PostgreSQL身份与来源关联，以及独立工程健康页和Worker探针；没有Agent或真实模型调用。STEP02 的 Windows 与 WSL Ubuntu 完整工程检查均已通过；WSL 另验证内核级出口隔离，见阶段1实施记录。

## 工具与依赖准备

Python 3.12.13（backend/.python-version）、Node 22.19.x（frontend/.node-version）、pnpm 10.28.0；本次 uv 为 0.11.7。Python 以 backend/pyproject.toml 和 uv.lock 为唯一入口；前端以 frontend/package.json 和 pnpm-lock.yaml 为唯一入口。

在对应目录执行一次依赖准备；需要可用的包仓库或完整本地缓存。这些安装命令与离线检查分开。

```powershell
# backend/
uv sync --locked --group dev
# frontend/
pnpm install --frozen-lockfile
pnpm exec playwright install chromium
```

WSL 必须使用 Linux 版 Python/uv、Node 和 pnpm；在 Linux 文件系统的独立工作副本安装依赖，不共用 Windows 的 .venv 或 node_modules。Ubuntu 首次准备还需在 frontend/ 执行 `pnpm exec playwright install-deps chromium`（需要系统包安装权限），再安装 Chromium。本次实测 Ubuntu 24.04 / WSL2，工具版本与上文相同；缺 libnspr4 等系统库时 E2E 会失败，不能跳过浏览器检查。

## 前端样式

前端架构与依赖决策以[阶段1前端职责合同](PsyEvoAgent项目计划/阶段1/02-技术方案与实施计划.md#frontend-stack-contract)为准。STEP03账号页已按真实消费者接入Query、Form、Zod；Store和shadcn仍未接入，健康页保持Start/Router和局部状态。后续修改先核对实际消费者与锁文件。

前端使用 Tailwind CSS 4.3.3，通过 `@tailwindcss/vite` 4.3.3 接入现有 Vite 构建。`frontend/src/style.css` 是唯一根样式入口：导入 Tailwind 并用 `@theme` 维护项目字体与颜色 token；页面布局和组件状态使用可静态扫描的 utility classes。当前无需 `postcss.config.*` 或 `tailwind.config.*`，不要另建第二套样式入口。

## 启动与停止

分别在两个终端启动；前端 http://127.0.0.1:3000 的 /api/v1 由 Vite 开发代理转发到 API 8000。此代理不是生产网关。

```powershell
# backend/
uv run --no-sync python -m app.dev
# frontend/
pnpm dev
```

重复启动本地开发服务时，新实例会先停止**同一工作目录、同一服务及同一端口**的旧实例，再启动：后端入口为 `app.dev`（也包括 `pnpm backend`），前端在 Vite 启动钩子中执行检查，`pnpm dev --port <端口>` 同样适用。后端会清理旧热重载监督进程及子进程；前端只识别本项目安装的 Vite 开发进程。不会按端口无差别结束其他程序，不删除文件或数据库。普通本地开发遇到其他程序占用前端端口时，Vite 自动选择下一空闲端口并在终端显示地址；开发代理只对与实际监听端口完全一致的本地浏览器 Origin 转发为 API 默认的 `http://127.0.0.1:3000`，使账号写请求继续通过单一 Origin 校验。显式配置 `PSYEVO_BROWSER_ORIGIN` 或使用隔离检查端口时保持严格端口，不启用这一回退。后端端口被其他程序占用时仍会报错。

检查复用 backend 已锁定的开发依赖 `psutil`；因此 `pnpm dev` 也要求 uv 和已完成 `uv sync --locked` 的后端开发环境。Windows 的旧进程替换使用终止进程树，会中断正在处理的请求；普通 Ctrl+C 和源文件热重载仍沿用原有退出流程。`PSYEVO_ENV=test`、前端 `PSYEVO_TEST_WEB_PORT` / Vitest，以及后端 `--stop-on-stdin-eof` 监督入口不执行自动替换，工程检查继续拒绝接管已有服务。此逻辑不自动加载 `.env`，不改变数据库配置。

2026-09-21 本次启动替换专项验证：Windows 上 `uv run --no-sync pytest tests/test_dev_instances.py tests/test_processes.py` 的8项进程测试通过；补充其他工作目录占用保护后，4项替换测试再次通过。新增模块及测试的 Ruff / mypy、前端 `pnpm check` 通过；临时端口上连续两次 `pnpm dev --port <端口>` 实测旧 Vite 及子进程退出、新实例返回 HTTP 200，测试进程已清理。本次未执行 WSL、完整隔离门禁或数据库业务验收，不替代历史收据。

2026-09-23 本地端口冲突复核：3000 由另一工作目录的 Nuxt 进程占用；`pnpm dev` 实测改在 3001 启动，首页返回 HTTP 200，原 3000 进程未被终止。临时本地接收端实测：来自 3001 的同源 Origin 转发为 3000，其他 Origin 保持原值。前端 typecheck 与 Python 语法检查通过；当时运行中的 API 未配置数据库，账号请求返回 `database_not_configured`，因此未验证完整登录流程。验证用 Vite 与接收端已退出。

普通开发按 Ctrl+C 退出，不删任何数据。API import只定义工厂；lifespan管理数据库连接池与启停日志，不启动Worker。app.dev 使用已锁定的 watchfiles 与 Uvicorn Server API，通过进程事件请求旧 API 完成 lifespan 清理后再启动新进程；默认监视 backend/app、监听127.0.0.1:8000，可传 --port 和 --reload-dir。停止超时会报错，不能当作成功重载。原生 Uvicorn --reload 在本机自动化环境中曾等待退出超时，因此本地开发使用上述已验证入口。

自动化监督可追加 --stop-on-stdin-eof 并保持 stdin 管道打开；关闭管道触发清理退出。入口使用非阻塞读取，避免 Windows 阻塞管道读取影响子进程初始化。语法或导入错误导致 API 子进程退出后，监督进程继续监视，修正文件后重新启动 API。真实进程回归验证连续两次错误/修正重载、三次 API 启停、无 Worker 导入及无残留子进程；停止超时另有回归检查。

Worker 无任务消费者，正常开发无需启动。仅检查其独立生命周期：在 backend/ 执行 `uv run --no-sync python -m app.worker --check`；不带 `--check` 时等待 Ctrl+C。STEP03数据库按本页首节配置，不需要启动Kafka、对象存储或观测服务。

## 检查入口

前端日常检查在 `frontend/` 执行：

```powershell
pnpm format
pnpm check
pnpm build
pnpm test:e2e
```

`pnpm format` 使用 Prettier 格式化前端手写源码和配置，约定两空格、单引号、无分号；忽略生成路由、锁文件、依赖、构建产物、测试报告及缓存，不处理后端或阶段文档。`pnpm format:check` 只检查、不改写文件。配置由前端 `.prettierrc.json` 和 `.prettierignore` 维护。

`pnpm test` 是现有 `test:unit` 的别名；`pnpm check` 顺序执行 typecheck、lint、test 和 format:check，任一步失败即停止。构建和 E2E 单独执行。此快捷入口不替代下面的完整工程门禁或 Linux/WSL 出口隔离验收。

依赖准备后，在仓库根目录执行（WSL 使用 `.venv/bin/python`）：

```powershell
backend/.venv/Scripts/python.exe -X utf8 scripts/check_step02.py
```

Node 版本管理器的 shim 不可用时，增加 `--node-dir <已安装的Node及pnpm目录>`，不安装第二套工具。脚本使用工作区 `.artifacts/` 存放 uv 缓存、独立测试临时目录和每次执行的 `receipt.json`，不会覆盖历史收据。端口 3000/8000 被占用时失败，不接管已有服务。联调服务由脚本启动并清理；直接在 frontend/ 执行 `pnpm test:e2e` 时由 Playwright 管理服务。门禁分别检查未暂存、暂存和相对 PR 基准分支的补丁；默认从 PR 环境或 `origin/HEAD` 检测基准，必要时显式传 `--base-ref <目标分支>`。回执哈希包含 backend、frontend、scripts 下的配置点文件，显式排除缓存、构建产物和秘密文件。

门禁包含 uv 锁检查、Ruff lint/format、mypy、pytest、前端 lint/typecheck/unit/build、浏览器真实网关联调、Python/Node 外连拒绝探针、构建产物合成密钥探针、文档及 fixture 检查。失败返回非零，reload 回归不会跳过。各前端命令和 backend 的 `uv run --no-sync pytest` 也可独立运行，但只有统一入口启用完整测试隔离。

## PR 出口隔离检查入口（Linux / WSL）

依赖及浏览器准备完成后，在工作副本根目录执行：

```bash
bash scripts/check_step02_isolated.sh
```

此入口依赖系统已有的 bash、util-linux（unshare/setpriv/mount）、iproute2 和 curl，以及非特权 user/network/mount/PID namespace 支持。入口创建私有命名空间，仅启用 loopback；清除继承配置、移除进程 capabilities、禁止提权。WSL 内另在私有挂载中阻断 /init 互操作解释器，防止 Windows 子进程绕过 Linux 网络；退出后不改变宿主网络、挂载或互操作设置。

完整门禁在该命名空间内运行。开始前用隔离模式 Python（`-I`，不加载网络钩子）验证仅 lo 网卡、无 capabilities、IPv4/IPv6 TCP/UDP 均返回 ENETUNREACH，再验证原生 curl 及 WSL Windows 程序无法外连/启动。`--require-os-isolation` 只要求验证隔离，不自行建立隔离；在普通环境直接使用会返回非零并拒绝执行测试。缺少 namespace 能力时也直接失败，不能回退到普通入口作为 PR 隔离验收。

Windows 普通入口用于开发回归，PR 出口验收使用上面的 Linux/WSL 入口。该命令可接入本地或私有 PR runner，不要求当前配置云托管 CI。它是网络隔离，不是针对恶意代码的完整文件系统沙箱；验证副本只放源码与合成材料，不放真实凭据或业务数据。

## 配置读取与隔离

2026-09-21 前端审计补齐 Prettier 3.9.8 和上述快捷脚本后，在 Windows 实际执行 `pnpm format`、`pnpm check`（2项单元测试）、`pnpm build`、`pnpm test:e2e`（4项）及 `git diff --check`，均退出0。本次没有重跑完整 Windows 门禁或 WSL 隔离门禁；历史收据不证明新增格式化配置已通过完整隔离验收。执行边界见[阶段1补充记录](PsyEvoAgent项目计划/阶段1/04-分步实施与检查清单.md#frontend-audit-followup)。

- API 工厂及 Worker 入口调用 backend/app/config.py，只读取 `PSYEVO_ENV=development|test`；默认 development，拒绝其他值，不自动加载 .env。
- Vite 的 `envDir: false` 禁止自动读取 .env，应用不读取模型/数据库凭据；`.gitignore` 忽略真实环境文件。
- 检查器只继承操作系统/工具路径等白名单变量，再注入测试配置。`PSYEVO_CHECK_NETWORK`、`PYTHONPATH`、`NODE_OPTIONS` 用于加载检查专用网络保护；`PSYEVO_MANAGED_SERVERS=1` 使 Playwright 使用检查器已启动的服务。
- Python audit hook、Node socket/DNS 保护和浏览器路由分别限制测试路径外连；PR 入口叠加上述内核隔离，覆盖整个门禁及原生子进程。隔离收据同时记录内核探针和完整工程检查结果，不能只复制一个环境开关。
- fake Provider 只提供固定结果和错误，不构成 STEP04 的模型适配/重试/预算验收；健康检查停止也不构成业务 run 取消验收。

<a id="指定https地址配置准备不代表已发布"></a>
## 指定HTTPS地址（配置准备，不代表已发布）

API和前端终端都设置相同的 `PSYEVO_BROWSER_ORIGIN=https://<指定主机名>`（可含端口，不含路径、尾斜杠或多个Origin）。API先将配置规范化，再与浏览器Origin精确比较以校验写请求；前端Vite读取其hostname加入allowedHosts；均不自动加载.env。API继续读取`PSYEVO_DATABASE_URL`，不将数据库变量暴露到前端。正常运行不设PSYEVO_TEST_*变量。

反向代理示例：[scripts/Caddyfile.example](scripts/Caddyfile.example)。在已有Caddy环境配置进程变量`PSYEVO_PUBLIC_HOST`（同一主机名及可选端口）、`PSYEVO_TLS_CERT`、`PSYEVO_TLS_KEY`（证书与私钥文件），执行`caddy run --config scripts/Caddyfile.example --adapter caddyfile`。它将/api/v1原路径转发8000，其余页面转发3000；保留浏览器Origin，不改写为上游Origin。证书私钥不入Git。本次不安装或启动远程代理，不申请域名证书。

前后端仍按上文分别运行本地进程；该示例用于受控实验访问，不新增云平台流程。需要停止时Ctrl+C，PostgreSQL停止保留数据卷；迁移先执行`alembic upgrade head`，不清库。

## 当前入口专项验收

`scripts/check_step03.py`会创建独立随机容器和合成数据库，执行注册/旧账号/来源权限/迁移保留回归、类型与lint、单测、构建、浏览器和数据库重启检查。另用本地OpenSSL（Windows复用Git自带版本）生成一日合成证书，通过仅绑定loopback的测试TLS代理验证HTTPS注册、Secure Cookie、退出和错误Origin拒绝；此代理不用于部署。测试证书只在被忽略的.artifacts目录，忽略自签名证书仅在测试配置中开启。

`PSYEVO_TEST_WEB_PORT`、`PSYEVO_TEST_API_PORT`、`PSYEVO_TEST_TLS_PORT`由检查器注入，分别供Playwright/Vite测试代理使用；不继承开发数据库环境。常规工程健康页面移到`/health`，STEP02浏览器回归同步使用新地址。历史完整门禁收据不改写，新验收与32份修订清单见[本次复核记录](PsyEvoAgent项目计划/阶段1/evidence/S1-STEP03/registration-review.md)。
