# 本地工程开发（S1-STEP02）

当前只有 TanStack Start 工程检查页、FastAPI 健康接口、独立 Worker 生命周期探针，以及合成测试。没有身份、数据库、Agent 或真实模型调用。STEP02 的 Windows 与 WSL Ubuntu 完整工程检查均已通过；WSL 另验证内核级出口隔离，见阶段1实施记录。

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

前端架构与依赖决策以[阶段1前端职责合同](PsyEvoAgent项目计划/阶段1/02-技术方案与实施计划.md#frontend-stack-contract)为准。当前仅工程检查页，已采用 Start/Router；Query、Form、Store、Zod 和 shadcn 相关能力尚未接入，不应从规划技术栈推断已安装。未来 AI 修改前先核对实际消费者与锁文件，不能为“全家桶”预装依赖。

前端使用 Tailwind CSS 4.3.3，通过 `@tailwindcss/vite` 4.3.3 接入现有 Vite 构建。`frontend/src/style.css` 是唯一根样式入口：导入 Tailwind 并用 `@theme` 维护项目字体与颜色 token；页面布局和组件状态使用可静态扫描的 utility classes。当前无需 `postcss.config.*` 或 `tailwind.config.*`，不要另建第二套样式入口。

## 启动与停止

分别在两个终端启动；前端 http://127.0.0.1:3000 的 /api/v1 由 Vite 开发代理转发到 API 8000。此代理不是生产网关。

```powershell
# backend/
uv run --no-sync python -m app.dev
# frontend/
pnpm dev
```

普通开发按 Ctrl+C 退出，不删任何数据。API import 只定义工厂，lifespan 仅记录启动/停止，不启动 Worker。app.dev 使用已锁定的 watchfiles 与 Uvicorn Server API，通过进程事件请求旧 API 完成 lifespan 清理后再启动新进程；默认监视 backend/app、监听127.0.0.1:8000，可传 --port 和 --reload-dir。停止超时会报错，不能当作成功重载。原生 Uvicorn --reload 在本机自动化环境中曾等待退出超时，因此本地开发使用上述已验证入口。

自动化监督可追加 --stop-on-stdin-eof 并保持 stdin 管道打开；关闭管道触发清理退出。入口使用非阻塞读取，避免 Windows 阻塞管道读取影响子进程初始化。语法或导入错误导致 API 子进程退出后，监督进程继续监视，修正文件后重新启动 API。真实进程回归验证连续两次错误/修正重载、三次 API 启停、无 Worker 导入及无残留子进程；停止超时另有回归检查。

Worker 无任务消费者，正常开发无需启动。仅检查其独立生命周期：在 backend/ 执行 `uv run --no-sync python -m app.worker --check`；不带 `--check` 时等待 Ctrl+C。当前没有 Compose/数据库，不需要启动 Kafka、对象存储或观测服务。

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
