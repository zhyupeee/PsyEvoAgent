# 本地工程开发（S1-STEP02～08内部实验工程交付）

## 2026-09-30 S2-STEP02 审查修复

发送恢复清除当次记录附件，明确缺失的记录可移除；保存恢复保留后续编辑并继续更新同一记录；删除确认每次重新核对关联摘记。睡眠顺序和跨度按 UTC 瞬时值计算，笔记日期按记录时区筛选。未新增依赖、迁移或配置读取方式。本次实现及独立验证记录见[审查修复](PsyEvoAgent项目计划/阶段2/evidence/S2-STEP02/review-repairs.md)，历史 STEP02 收据保留。

## 2026-09-29 审查回归修复

侧栏与会话管理共用 Radix Dialog 删除确认组件（锁定 `@radix-ui/react-dialog` 1.1.23）。确认后先阻断对应会话的正文、历史、SSE 订阅和输入；请求未确认时保持隐藏，关闭再打开弹窗仍使用原幂等键。保留取消、键盘焦点约束与关闭后的焦点恢复。修订入口复用现有 Collapsible，收起保留草稿。

聊天容器恢复短视口下的纵向滚动兜底，禁用外层自动锚定以配合时间线自身分页定位；输入复用 Textarea，字号相对当前偏好缩放（普通 15.2px，大字体 19px）。公共 SSE 帧上限随完整响应上限调整为 132 KiB（128 KiB 响应加 4 KiB 事件封装余量），仍只发布整稿检查通过的答案，不改变 token 预算、发送超时、核权或公共事件序号。

回归用例位于 `frontend/tests/chat-regressions.spec.ts` 与 `backend/tests/test_live_runs.py`，覆盖删除响应丢失与重试、弹窗焦点、320×500px 可操作性、实际字体大小、修订草稿与分页锚点，以及长 ASCII、接近 128 KiB 的 UTF-8/JSON 转义响应经 Worker 持久化、SSE 完成事件和游标重放。使用合成内容与受控 SDK 传输，未调用真实 Provider 或使用开发数据库；本次验证结果另列，不覆盖下方历史记录。

Windows `scripts/check_step07.py --web-port 3137 --api-port 8137 --tls-port 3437` 通过：107 项 PostgreSQL/API/迁移测试、145 项后端测试、27 项浏览器检查、数据库重启事实核对、Ruff/mypy、`pnpm check`/`pnpm build` 及文档/补丁检查。新收据为 `.artifacts/psyevo-step07-1cdbb6449a1a/receipt.json`。另在 3138 端口以合成 API 运行 5 项聊天回归和 1 项反馈回归，全部通过，配置与截图在 `.artifacts/review-playwright.config.ts`、`.artifacts/review-browser-results/`。首次门禁发现并修复外层滚动锚定偏移，失败收据 `.artifacts/psyevo-step07-b26b5c222a66/receipt.json` 保留；本次未复跑 WSL 内核隔离门禁。

## 2026-09-29 反馈板块组件替换

“反馈或纠正 · 可跳过”整体改用 `components/ui/collapsible.tsx`，新增锁定依赖 `@radix-ui/react-collapsible` 1.1.20；两个下拉复用已有 Radix Select，文本框与按钮使用共享 Textarea / Button。保留 `.feedback-panel`、可访问名称、TanStack Form/Zod 和幂等提交逻辑。收起保留草稿，取消清空草稿并将焦点返回折叠入口；未扩展到其他板块。Radix 内部用于表单集成的隐藏原生 select 属于组件库实现。

`pnpm check`（7 项 Node、7 项 Vitest）、`pnpm build`、`git diff --check` 通过。新增 `feedback-ui.spec.ts` 纳入默认 Playwright 组，Chromium 合成 API 拦截检查通过：1280/320px 键盘展开/下拉/焦点、草稿保留、取消重置且不提交、空理由提交、503 后同幂等键/同内容重试及合成回执展示；截图复核无横向溢出。结果及截图位于 `.artifacts/feedback-ui-review/`。`history.spec.ts` 的原 PostgreSQL 反馈用例同步改用 combobox/option；本轮未重跑完整 STEP/WSL 门禁，未连接数据库或 Provider。

## 2026-09-29 会话归档筛选组件

搜索框右侧的会话范围选择改用 Radix UI Select，新增锁定依赖 `@radix-ui/react-select` 2.3.7；实际消费者为 `history-page.tsx` 的会话列表。`components/ui/select.tsx` 提供当前使用的控件组合，沿用 Tailwind 主题、Lucide 图标和唯一 `style.css` 入口。菜单通过 Portal 展示，支持选中标记、键盘/触摸选择、Esc/外部点击关闭和焦点返回。保留“会话范围”名称、搜索词及筛选时重置分页的行为；既有历史浏览器用例改为点击 combobox/option。未初始化其他 shadcn 组件或添加 cn/Sonner。

`pnpm check`（7 项 Node 启动检查、7 项 Vitest 测试）、`pnpm build` 通过。Chromium 合成 API 拦截检查通过：1440/390/320px 布局、入口展开坐标不变、菜单无裁切/横向溢出、键盘/触摸选择、关闭/焦点恢复及搜索与分页筛选。脚本、截图与收据位于 `.artifacts/archive-select-review/`；未连接数据库或 Provider，未运行完整 STEP/WSL 门禁，历史记录保持原时点。

## 2026-09-29 对话操作展开位置修复

“修订最后输入”保持在回答操作行，编辑区单独在下方占满宽度，展开不再强制入口换行；收起或按 Esc 保留未提交草稿，并提供展开状态和键盘操作。“管理此对话”改为标题栏下方的有界浮层，不再撑宽工具栏；支持点击外部或 Esc 关闭，与旧版本面板互斥，删除仍使用原确认对话框。沿用现有 Tailwind 控件、表单和 API，无新增依赖。

`pnpm check`（7 项 Node 启动检查、7 项 Vitest 测试）、`pnpm build` 通过。Chromium 合成 API 拦截验证 1440/1024/390/320px 下入口展开前后坐标不变、标题栏尺寸不变、无横向溢出，并覆盖长对话、折叠侧栏、键盘操作、草稿保留、浮层关闭/互斥、删除确认、修订失败保留输入及改名/归档/恢复请求。脚本、截图及收据在 `.artifacts/disclosure-review/`；本次未连接数据库或调用 Provider，未重跑完整 STEP/WSL 门禁，历史收据保持原时点。

## 2026-09-29 长回答误判修复

Support 回答不再复用用户输入的 4000 字符上限；用户输入上限不变。Provider 流式拼接与 Support JSON 解析前共用 128 KiB（131072 UTF-8 字节）整稿上限，包含 JSON 包装、空白及转义字符。旧 32 KiB 上限提高四倍；不再按 SDK chunk 数量判定截断，字节上限约束缓冲，既有运行期限约束空块流。token 预算、用量校验、正常结束标记及整稿规则检查继续生效。

超出整稿字节上限返回 `output_too_large`，前端显示长度超限；`truncated`、`partial_stream`、`usage_over_reservation` 分别显示未完整生成、传输不完整与预算超限。历史失败 run 保留原事实，不自动重发。

受控 SDK/Support/多轮/模型配置回归覆盖 4000/4001/6000 字符、中文及 JSON 转义、旧缓冲上限以上正文、128 KiB 精确边界与超限、超过 6000 个内容块及结束/用量块。95 项通过，6 项 PostgreSQL 用例按默认标记排除；Ruff、mypy（63 个源文件）、前端 `pnpm check`、`pnpm build` 和 `git diff --check` 通过。测试使用合成内容和受控用量计数，不代表真实供应商 token 测量；未调用真实模型或使用开发数据库，未执行浏览器或完整 Windows/WSL 门禁。

## 2026-09-29 AI 回复 Markdown 展示

当前聊天时间线与旧版本回答共用 `frontend/src/markdown-message.tsx`，新增锁定依赖 `react-markdown` 10.1.0 与 `remark-gfm` 4.0.1；支持标题、强调、列表、引用、代码块、表格、任务列表与删除线。排版由唯一 `style.css` 中的 `markdown-content` 工具类维护，沿用现有颜色和字体；用户输入仍显示原文。保留接口与存储中的 Markdown 原文，仅渲染获准的 `output.text`，不改变整稿发布、SSE 恢复或来源检查。禁用原始 HTML，保留解析器默认 URL 过滤，链接使用 `noopener noreferrer`；模型图片只显示替代文字，不自动请求远程图片。

本次 `pnpm check`（7 项 Node 启动检查、7 项 Vitest 测试）、`pnpm build` 通过。Chromium 合成 API 拦截验证正文语义与样式、1440/390/320px 布局、表格/代码横向滚动、用户输入原文、旧版本与刷新恢复，以及 HTML/危险链接拦截和无图片外连；脚本、截图及收据位于 `.artifacts/markdown-review/`。此次未连接数据库或调用 Provider，未重跑完整 STEP/WSL 门禁，历史收据保留原时点。

## 2026-09-29 对话起始页与设置导航优化

按钮最终调整：以文字本身相对按钮水平居中，加号绝对定位在文字左侧、间距 6px，不占据文字居中布局；保留 18px 图标和 20px 文字行高。`pnpm check`、`pnpm build` 通过；Chromium 合成 API 下验证 1280/390px 文字中心、图标垂直中心及 6px 间距，截图复核通过，材料在 `.artifacts/new-chat-label-center-review/`。此项取代下方“加号固定左侧”的布局方案；下方截图与测量仍为前一版本记录。

新建对话按钮视觉补充：侧栏按钮改用 `components/ui/button.tsx` 共用基础组件，采用左右等宽图标槽，文字相对整按钮居中、18px 加号固定左侧，文字行高统一为 20px；创建、禁用状态和可访问名称保留，无新增依赖。`pnpm check`、`pnpm build` 通过；Chromium 合成 API 下验证 1280/390px 的文字水平/垂直中心与图标垂直中心偏差均小于 1px，并复核按钮截图，材料位于 `.artifacts/new-chat-button-review/`。未连接数据库或 Provider，未执行完整 STEP 门禁。

刷新身份加载补充：身份查询等待及未登录跳转期间复用无账号数据的 `SupportLayout` 顶部导航，主区域标记 `aria-busy`；“正在确认登录状态”改为屏幕阅读器专用提示，登录/注册页同步处理。身份成功前不挂载账号业务页面或查询偏好，不持久化登录身份来绕过校验；失败隐藏内容与重试规则保留。

本轮 `pnpm check`、`pnpm build` 通过；`account-recovery.spec.ts` 的两项 Chromium 合成拦截测试通过，覆盖 1280/320px 首次访问与刷新时主动挂起身份响应、入口位置不变、未发起业务请求/未显示密码表单，以及 503 重试后 401 跳转登录。本地结果为 `.artifacts/identity-refresh-review/results.json`；未连接数据库或 Provider，未执行完整 STEP/WSL 门禁。

后续设置入口布局修复：对话、设置与资源统一顶部导航，设置链接始终位于右上角；窄屏将主要导航放在第二行。移除按路由切换顶栏/左侧栏的布局变化，设置和资源内容独立滚动并预留滚动条空间，保留路由、可访问名称及历史测试钩子。未新增依赖。

本次 `pnpm check`（7 项 Node、7 项 Vitest）、`pnpm build` 通过。Chromium 合成 API 拦截在 1280/390/320px 下验证首次进入设置的逐帧入口位置、滚动后导航位置、无横向溢出、页面切换无身份闪现/布局卸载、标签草稿保留及身份保护，并复核截图；脚本、截图和收据位于 `.artifacts/settings-layout-review/`。`frontend/tests/support.spec.ts` 增加入口与导航边界不变断言；本轮未执行完整 STEP/WSL 门禁，未连接数据库或 Provider。下方为此前时点记录。

对话起始页改为居中的轻量欢迎区，突出标题与开始按钮；支持资源保留次级入口，服务说明与删除处理记录放在底部。原创建会话行为、错误重试和可访问名称保留。`/me` 及旧 `/me/privacy` 路由现归入 `_support`，与对话、资源共用身份缓存和布局；设置标签、旧地址跳转、首次身份检查与退出行为保持原约定。

`pnpm check`、`pnpm build` 通过。Chromium 合成 API 拦截检查通过：欢迎区桌面/手机/短屏布局、创建失败重试及两个链接；桌面/手机跨设置导航全过程无登录提示闪现或布局卸载、设置标签草稿保留、旧地址跳转、身份失败重试及退出后保护。本地截图和收据分别在 `.artifacts/welcome-review/`、`.artifacts/settings-navigation-review/`；并扩展 `frontend/tests/support.spec.ts` 的导航回归用例。本次定向检查未连接数据库或 Provider，未重跑完整 STEP 门禁，历史收据保持原时点。

## 2026-09-29 会话侧栏背景与滑动优化

侧栏面板填满工作区高度，整列统一使用 paper 底色。`style.css` 的 `sidebar-rail` / `sidebar-panel` 工具类维护固定面板宽度、外轨收缩与滑动，保留原测试钩子和折叠持久化。桌面及窄屏使用 280ms 过渡；应用“减少动态效果”下仅保留 140ms 导航位移，系统 `prefers-reduced-motion` 下关闭过渡。未新增依赖。

本次 Chromium 使用合成 API 拦截验证整列高度/底色、折叠中间帧、快速反向点击、刷新持久化、两种减少动态设置及窄屏无横向溢出，并检查桌面/窄屏截图；本地脚本、截图及收据在 `.artifacts/sidebar-review/`。这属于前端视觉交互检查，未连接数据库或调用 Provider，不替代下方历史 STEP 门禁收据。

## 2026-09-29 支持资源切换与删除会话刷新修复

`/chat`、`/resources` 及其子路由共用无路径 `_support` 布局和身份查询实例，站内切换不再重建登录状态；首次访问仍验证身份。删除会话成功后只取消和移除该会话的查询、更新列表与删除处理记录；删除当前会话通过 Router 替换为 `/chat`，保留公共布局和登录缓存，删除其他会话保留当前草稿。确认、幂等重试、跨标签删除通知及退出后的身份检查沿用既有机制。

回归入口为 `frontend/tests/support.spec.ts` 的导航全过程 DOM 监测、直接资源访问身份检查，以及 `frontend/tests/history.spec.ts` 的侧栏删除与原删除重试用例；后者检查无主文档导航且原布局节点仍连接。隔离验证使用 `scripts/check_step07.py`（包含 STEP06），不读取开发库、不调用真实模型。此次未修改后端接口或数据库结构。

最终验证：`pnpm check`、`pnpm build` 及 `scripts/check_step07.py --web-port 3106 --api-port 8106 --tls-port 3446` 全部通过；包含 10 项 STEP06、5 项 STEP07 浏览器用例及数据库重启后删除内容/回执核对。最终本地收据：`.artifacts/psyevo-step07-27a74770c9ff/receipt.json`。验证过程中为 21 轮合成对话用例增加总时间余量、等待回执数据加载后再展开，并让新增侧栏删除用例使用独立合成账号，保留原回执计数断言；早期失败收据保留原样。未执行 WSL 内核隔离或真实模型验证。

## 2026-09-29 模型配置页面与自动生效

普通 Windows 启动仍用 `scripts/start-dev.ps1` 或 frontend 中 `pnpm backend`（无显式数据库变量）。一次启动完成增量迁移、独立加密主密钥初始化和 API/Worker 统一管理。随后保存 `.env.step08.ps1` 自动影响新运行，无需手动重启；在途回答与标题使用原私有配置快照，文件错误保留上次有效配置。仅显式 `-MaxOutputTokens` 覆盖文件输出上限。

用户在“设置 → 模型配置”选择官方或个人 API。个人模式按账号加密保存；缺少官方 Key 时仍可使用个人模式。Key 不回显，换地址必须重新输入 Key。保存不调用模型；测试按钮执行一次固定合成请求，可能收费，不重发用户对话。

`app.local_model_key` 首次本地启动生成独立 Fernet 主密钥，保存于 Git 忽略的 `.env.local.json` 的 `provider_encryption_key`，启动脚本注入 `PSYEVO_PROVIDER_ENCRYPTION_KEY`。存在密文时不得另造密钥；必须恢复原配置。不要向前端进程传入 Provider 或加密变量。`PSYEVO_PROVIDER_CONFIG_FILE` 仅由普通本地入口设置；配置读取由 `app.provider_config` 负责，`app.config` 仍只读显式进程变量，显式测试库不自动读取本地文件。

`-DisableSupport` 关闭 live；`-PrepareOnly` 只准备数据库，不加载 Provider、不初始化模型密钥、不启动 Worker。源码重载先排空 Worker 当前任务；模型配置变化使用新运行快照，不触发源码重载。旧失败回答需用户主动重新生成。

定向检查：backend 中运行 `uv run --no-sync pytest tests/test_model_config.py`；数据库/API 检查使用隔离 `PSYEVO_TEST_DATABASE_URL` 并运行 `pytest -m postgres tests/test_model_settings_api.py`。根目录 `backend/.venv/Scripts/python.exe -X utf8 scripts/check_model_settings.py` 使用同一显式隔离测试库，端口8110/3110，不读取真实 Key、不发真实模型调用。

当前状态见 [S1-MODEL-SETTINGS](PsyEvoAgent项目计划/阶段1/evidence/S1-MODEL-SETTINGS/README.md)。下方旧配置和收据保留原时点。

## 2026-09-28 本地真实聊天启动修复

最新修复：普通 `pnpm backend`（无显式数据库变量）或 `scripts/start-dev.ps1` 默认启动 live API/独立 Worker，`-DisableSupport` 关闭，`-PrepareOnly` 不启动模型。开发启动输出上限默认为 4096，可用 `-MaxOutputTokens` 降低；总预算仍为 8192，供应商超额仍失败，不裁掉 usage 或发布未通过检查的回复。隔离 test 配置仍限 1024。此处取代下文早期“默认 disabled”的启动说明。

两条用户报告的失败 run 原因为 `usage_over_reservation`，总用量 2411/2648 未超总预算，但输出超过原 1024 上限。反馈/修订组件 sibling key 已加独立前缀。73 项后端定向测试、前端 check 通过；使用重启后开发配置的固定合成输入真实 Provider 探针通过，未重发用户原消息。历史失败 run 保留原预算及失败事实，新请求才使用新预算。

用户已明确授权当前本地开发库使用真实模型。日常需要 AI 回复时，在根目录执行 `powershell -NoProfile -File scripts/start-dev.ps1 -LiveSupport`，或在 frontend 执行 `pnpm backend -LiveSupport`（未显式设置数据库变量时）。该显式选项读取 Git 忽略的 `.env.step08.ps1`，向 API 和独立 Worker 注入 Provider 配置，启用 `PSYEVO_SUPPORT_MODE=live`。脚本结束时停止其 Worker 并恢复环境变量；API 导入和 reload 不启动消费者。前端仍在另一个终端执行 `pnpm dev`，不要向前端加载密钥。

默认启动仍为 disabled。development live 仅接受 loopback 的 `psyevo_synthetic_dev` 库和非空密钥；test 仍强制隔离合成库，fake 与练习限制不变。保留开发数据，使用增量迁移。配置测试不连接开发库；真实聊天会向已配置服务商发送内容并可能产生费用。此授权仅覆盖本地开发，不代表发布授权。

本轮验证：配置/Provider 30 项、基础/进程 11 项、Node 启动入口 7 项通过，Ruff 与配置 mypy 通过。实际开发 API 和独立 Worker 均为 development/live 且凭据已加载，3001 同源健康请求返回 200；报错 run 经只读检查仍为 draft/version 1，可重试原消息。本轮未代发用户保留的消息，未将运行配置检查记为该消息回复成功。

## 2026-09-28 STEP08内部实验工程验收

**状态：COMPLETED（限定内部实验工程范围）**。最终74项数据库/API/迁移、92项后端、21项页面及真实模型旅程、重启直查、WSL内核隔离通过；真实SMTP邮件经用户回传测试标识确认送达。无需再次填写内容审阅表或重复发送测试邮件；后续重新验证才运行下列显式命令。

当前采用[工程完成标准](EXPERIMENT.md)，专业审阅不再作为STEP08工程前置，事实仍为未审阅。Full Buffer Review为启用路径；安全公共分块未实现，不冒充通过。live仍限独立合成test数据库，development练习仍关闭；本次没有新业务API/迁移。最新结果、21项矩阵及阶段2合同见[收尾记录](PsyEvoAgent项目计划/阶段1/evidence/S1-STEP08/engineering-closeout.md)。下方历史状态保留原时点。

SMTP配置放在Git忽略的`.env.step08-smtp.ps1`，只由操作者显式dot-source向当前进程注入；API、SMTPMailer及探针仍由`app.config.load_settings`读取进程变量，不自动读文件。既有配置为`PSYEVO_SMTP_HOST/PORT/FROM/USERNAME/PASSWORD/TLS_MODE`及`PSYEVO_EMAIL_CODE_KEY`。新增探针变量`PSYEVO_SMTP_TEST_TO`为操作者自有收件邮箱，`PSYEVO_SMTP_TEST_SEND_ALLOWED=true`为向该邮箱发送一封合成测试邮件的显式授权，仅`app.smtp_probe`消费，不是业务身份字段。

```powershell
# 一次运输/送达检查；不要混入PR门禁或反复重发
. ./.env.step08-smtp.ps1
Push-Location backend
try { uv run --no-sync python -m app.smtp_probe --send } finally { Pop-Location }
# 收件后，从backend目录对上述命令生成的实际receipt路径确认：
# uv run --no-sync python -m app.smtp_probe --confirm <实际receipt.json路径>
# 按提示输入邮件里的测试标识；不会再次发送邮件
```

无授权/缺收件邮箱/CI或网络隔离环境拒绝发送；不就地创建业务账号。探针收据位于`.artifacts/step08-smtp-*/receipt.json`，只记录TLS模式、接受/送达状态、测试标识散列、源hash和时间；不记录收件地址、密码、邮件全文或原始SMTP错误。确认错误返回1且不改送达状态；正确标识才标delivery_confirmed。SMTP服务器接受不能等价邮箱送达。此次真实发送与确认已执行，不需再填内容审阅表。

模型工程门禁继续显式加载`.env.step08.ps1`，执行`scripts/check_step08.py --live`；该入口不读取SMTP密码也不发送邮件。普通Windows/WSL gate仅受控测试；真实SMTP收据独立附入最终验收。SMTP业务验证码注册/恢复/改密仍由原隔离数据库+邮件替身回归，不能把独立运输检查称为真实账号完整注册实测。

当前兼容适配会对重复终局usage的input/output/total三个相同计数去重，可选细分字段差异不重复计账；计数冲突、提前usage、终止后正文、畸形工具片段和错误choice均停止。`tests.live_diagnostics`在门禁清理合成数据库前导出无正文调用/终态记录，避免失败原因被清理掉。历史收据数字保留原观察，不能拿此前SDK可能累计的重复usage当供应商实际账单；价格仍unknown。

## S1-STEP08.1 内部流PoC（真实验收BLOCKED）

2026-09-27续作：用户已本机填写密钥，内部流PoC已有真实通过收据；以下“密钥留空/产品live未接入”为首次切片时点。当前新增隔离合成库的网页live装配与验收入口：

```powershell
. ./.env.step08.ps1
backend/.venv/Scripts/python.exe -X utf8 scripts/check_step08.py --live --web-port 3108 --api-port 8108 --tls-port 3448
```

此入口先复用STEP07完整fake门禁，再向独立API/Worker注入live配置，浏览器/前端进程不接收密钥。`PSYEVO_SUPPORT_MODE=live`仅允许`PSYEVO_ENV=test`、既有独立loopback合成check/migration库和非空密钥；不启动开发库live。`app.config.load_settings`由API和独立Worker读取，API import不启动消费者。PoC仍需`PSYEVO_LIVE_PROBE_ENABLED=true`；独立Worker显式live模式不依赖PoC开关。验收器生成并清理随机数据库，不将真实密钥放进命令行、收据或前端。

当前正式适配链仍采用整稿路径：原始流只在私有Buffer中，终局schema/usage/输出规则通过后，由既有Worker事务写message/delta/completed，页面复用原SSE与快照。start冻结模型、`provider_ref`、原deadline、输出上限及单次调用预算；费用上限/实际费用为null，不沿用fake价格。Worker重新装配按冻结预算裁剪，不随进程新配置扩大单次预算。供应商兼容请求同时发`max_completion_tokens`与`max_tokens`；每次仍检查实际usage，不能凭一次通过声明任意请求都会尊重限制。

删除回执根据持久调用账本判断是否涉及live，不随当前开关改写历史事实。在线清理成功仍为completed；新增`external_provider_status=unknown`时页面明确供应商保留/删除状态未知，不能宣称远端已删除。无真实调用时该字段为not_applicable。无需新数据库迁移。

新增`PSYEVO_STEP08_ARTIFACTS`仅由检查器给页面验收进程指定输出目录；`tests.step08_receipt`在数据库重启后核对完成/取消各一次调用、删除阻断与费用unknown，并输出无正文账本。live检查失败不自动重调模型；失败收据与成功收据分别保留。STEP08整体状态与未满足项见本步续作记录，不以此命令的工程通过替代专业内容审阅或安全分块验收。

用户指定`https://ai.hybgzs.com/v1`与`grok-4.7`，Chat Completions兼容协议仍待真实验证。`app.provider`通过LangChain把内部流缓冲后送回原`SupportRuntime`的schema、usage和整稿规则检查；没有公共增量或数据库写入。API/Worker仍只支持disabled/fake，真实PoC完成后才接网页旅程。

新增直接依赖`langchain-openai==1.6.6`、`openai==3.19.2`、`httpx2==2.13.1`；后者是SDK要求的显式传输客户端，已有HTTPX业务消费者及LangChain Core/LangGraph版本保持原样。先在backend执行`uv sync --locked --group dev`。

本地忽略文件`.env.step08.ps1`已留空密钥，参考模板为`scripts/step08-live.env.ps1.example`。在本机填写后，根目录显式执行：

```powershell
. ./.env.step08.ps1
Push-Location backend
try { uv run --no-sync python -m app.provider_probe --live } finally { Pop-Location }
```

不自动加载环境文件；`app.config.load_settings`只读进程变量：

| 变量 | 默认/范围 | 消费者 |
|---|---|---|
| `PSYEVO_LIVE_PROBE_ENABLED` | false；需显式true | PoC及适配器工厂，不开放产品live |
| `PSYEVO_PROVIDER_BASE_URL` | 上述HTTPS地址；禁止URL凭据/查询/片段 | SDK工厂 |
| `PSYEVO_PROVIDER_MODEL` | grok-4.7 | SDK、绑定、收据 |
| `PSYEVO_PROVIDER_API_KEY` | 空 | SDK工厂，不进入收据 |
| `PSYEVO_PROVIDER_DEADLINE_SECONDS` | 60，最多120秒 | SDK与原图总deadline |
| `PSYEVO_PROVIDER_MAX_OUTPUT_TOKENS` | 1024，范围1～1024 | SDK输出限制与账本 |

PoC只发送代码内固定合成输入；一次调用，无SDK/图重试，预占整个8192 token信封，不沿用fake字节估算。实际usage超界判失败；未知tokenizer不构成精确请求token上限保证。价格/币种/地区/保留条件unknown，费用预占和实际费用均null，没有已验证金额上限。原始流上限32768字节/4096块，超限停止，不强制发布。SDK禁重定向和环境代理，不回退`OPENAI_API_KEY`。本地取消不证明远端停止计费。

`--live`、显式开关和非空密钥缺一不可；检测到`CI`或`PSYEVO_CHECK_NETWORK`拒绝入口。缺配置退出2，调用/检查失败退出1，单次PoC通过退出0。收据位于`.artifacts/step08-live-*/receipt.json`，含版本、源码hash、run、账本、流观察，不含正文/密钥/原始错误。不自动执行真实请求，不将其加入PR门禁。

受控SDK检查：backend中运行`uv run --no-sync pytest tests/test_provider.py`；完整前置复验仍用根目录`scripts/check_step07.py`，会收集新增后端测试。测试使用内存传输替身，不是Provider实测。真实流完整能力矩阵、网页旅程、安全分块和阶段交接仍未完成，见[本步记录](PsyEvoAgent项目计划/阶段1/evidence/S1-STEP08/README.md)。

## S1-STEP07 历史、修订、删除与反馈

`/chat`新增本人标题搜索、归档/恢复；会话内有管理、历史分支、修订/重新生成、可选反馈。`/me`提供会话管理及删除处理记录。删除先确认并持久阻断访问，再串行清理在线正文/事件/反馈/来源使用；中途失败不显示完成，可按回执重试。当前未配置持久LangGraph检查点、应用备份、真实Provider，其清理在回执中标不适用；用量元数据及无正文墓碑保留。没有新增Agent、Worker消费者或依赖。

已有开发库只做增量迁移：在backend运行`uv run --no-sync alembic upgrade head`；新增`h007_history_feedback`，保留旧会话/run/消息及历史决定，有本步数据时拒绝有损降级。不要删卷或重置开发库。

根目录运行`backend/.venv/Scripts/python.exe -X utf8 scripts/check_step07.py --web-port 3107 --api-port 8107 --tls-port 3447`。入口复用原随机独立PostgreSQL门禁，执行前置回归、真实API/迁移、fake Worker、STEP07页面及数据库重启直接核对；仅处理本次合成库。`PSYEVO_STEP07_ARTIFACTS`仅由检查器注入，读取者`frontend/tests/history.spec.ts`保存合成截图，不是产品配置；不新增产品环境变量、.env加载或邮件/模型外发。WSL仍使用独立Linux依赖和`check_step02_isolated.sh --step04`做工程/Support内核出口检查，不冒充STEP07数据库页面已在内核隔离执行。

STEP07执行结果以[本步记录](PsyEvoAgent项目计划/阶段1/evidence/S1-STEP07/README.md)为准；下文为历史实施时点。

## S1-STEP06 对话、资源与偏好页面

`/chat`、`/chat/$sessionId`、`/resources`、`/resources/exercises/$exerciseId`和`/me`偏好已接现有API。普通开发仍使用本页已有Windows/WSL进程，不启动假Worker；真实Provider默认disabled，发送显示未确认/服务不可用。练习静态合成内容未经专业审阅，仅在既有隔离test环境返回；development只显示待审阅。页面没有长期记忆、历史管理、反馈、删除或练习历史。

根目录执行`uv run --directory backend --offline --no-sync python -X utf8 ../scripts/check_step06.py --web-port 3106 --api-port 8106 --tls-port 3446`。脚本扩展现有STEP03/05门禁，用随机独立PostgreSQL、独立fake Worker、真实同源页面检查发送响应丢失重试、停止/断流/刷新、偏好失败与持久化、手机键盘、独立练习和账号隔离；数据库重启后直接核对偏好版本与唯一发送/调用。测试截图、JUnit与收据写入`.artifacts/psyevo-step06-*/`，不访问开发库。

新增`PSYEVO_STEP06_ARTIFACTS`只由检查器注入，读取者是`frontend/tests/support.spec.ts`，指定截图目录；不是产品配置。没有新增产品环境读取器或.env加载。API静态练习检查复用`settings.environment`，不依赖support_mode，因此模型disabled仍可在隔离合成域验证。WSL仍以`check_step02_isolated.sh --step04`运行非数据库工程/Support及内核出口门禁，数据库业务验收单列。

当前证据见[STEP06记录](PsyEvoAgent项目计划/阶段1/evidence/S1-STEP06/README.md)。下方历史时点说明不代表当前页面仍未实现。

## S1-STEP05 持久run与真实网关验收

根目录执行`uv run --directory backend --offline --no-sync python ../scripts/check_step05.py --web-port 3105 --api-port 8105 --tls-port 3445`。复用STEP03随机独立PostgreSQL容器及网络保护，执行迁移/API/后端/前端/身份浏览器/HTTPS，再启动独立fake Worker做原生EventSource断流重放、快照、取消终态与撤销来源检查，最后重启数据库核对唯一run/调用/主动发起。仅清理本次创建的容器和测试进程，不操作开发库。收据位于`.artifacts/psyevo-step05-*/receipt.json`。

配置读取沿`app.config.load_settings`，不自动加载.env。新增`PSYEVO_SUPPORT_MODE`默认disabled；fake只允许`PSYEVO_ENV=test`与独立loopback合成check库。显式`uv run --no-sync python -m app.worker --support`消费该库；不加--support仍为原生命周期探针。API导入/reload无消费者。普通开发库即使配置fake也拒绝，不以固定假回答冒充可用心理支持。

本步无聊天页面。浏览器验收位于`frontend/tests/runs.spec.ts`；仅测试工厂`tests.run_gateway:create_gateway_app`挂载合成游标淘汰夹具，正式工厂不含测试路由。`check_step02_isolated.sh --step04`继续复用完整工程与Support隔离门禁，同时收集本步非数据库回归；真实PostgreSQL门禁单列，不能混称全链内核隔离。详情见[STEP05记录](PsyEvoAgent项目计划/阶段1/evidence/S1-STEP05/README.md)。

> 当前按[内部实验执行约定](EXPERIMENT.md)推进：可通过指定HTTPS地址分享；目标注册先验证邮箱，登录后直接进入，无年龄或用途确认，不设公众资格、真人告知或期限审批前置。业务不设固定TTL。邮箱身份已实现；真实 SMTP 尚未配置，验证范围见阶段1 STEP03.5 记录。

## S1-STEP04 单Support隔离合成验收

后端内部`app.support.SupportRuntime`执行唯一LangGraph；仅接LangChain本地fake，不注册HTTP/start/SSE接口，不启动Worker，也不修改数据库schema。现有网页不新增聊天入口。运行输入由可信调用方提供身份、来源快照及核权函数；实际数据库run绑定与事件交付在STEP05实现。本步合同与局限见[STEP04技术](PsyEvoAgent项目计划/阶段1/02-技术方案与实施计划.md#s1-step04-implementation)。

新增消费者所需锁：LangGraph 1.2.12、langchain-core 1.6.4；langsmith 0.14.0仅用于显式关闭SDK追踪。`uv.lock`还将websockets从17.1解析为16.1.1以满足新增依赖；其余已有直接业务依赖未移除。先在backend执行`uv sync --locked --group dev`，然后在根目录执行：

```powershell
backend/.venv/Scripts/python.exe -X utf8 scripts/check_step04.py
```

WSL独立源码副本先准备Linux依赖与浏览器，再执行`bash scripts/check_step02_isolated.sh --step04`。入口复用原工程门禁、内核隔离与外连负例探针，再输出本步JUnit、13场景正反例、fake账本和能力矩阵，位于`.artifacts/step04-*/`。命令不安装依赖、不访问开发库、不发送真实邮件或模型请求。没有内核隔离时`--require-os-isolation`仍拒绝运行，不降级。

本步运行配置由显式Pydantic参数提供，不增加环境配置读取器；不读取Provider密钥或`.env`。Budget/ModelProfile/VersionBinding在单次运行内冻结；拒绝共享模型缓存、外部callbacks、verbose/debug和未计量SDK重试，LangSmith tracing显式关闭。fake价格使用SYNTHETIC币种，usage未知保留预占且actual为null；不能拿fake金额估算真实费用。规则评分不代表语义安全审阅，真实Provider及支持内容审阅仍BLOCKED。未实现组件不冒充已批准版本。

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

Windows 也可直接在 `frontend/` 执行 `pnpm backend`：未设置 `PSYEVO_DATABASE_URL` 且环境未指定或为 `development` 时，`scripts/start-backend.cjs` 自动调用上述 `scripts/start-dev.ps1`，读取已有本地配置、等待 PostgreSQL 就绪、完成增量迁移并启动 API。每次新开终端都可使用，无需手动恢复变量；首次配置仍需运行上面的 `-Initialize` 命令。已有显式数据库变量时直接继承并启动 API，不覆盖连接、不自动迁移该数据库；WSL 仍按下文设置变量，test/production 缺变量时拒绝回退到开发库。可传 `pnpm backend --port 8001` 等 `app.dev` 参数。启动回归运行 `node --test scripts/start-backend.test.cjs`（仓库根目录），无需数据库。

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

2026-09-25 启动入口修复专项验证：7项不连接数据库的启动回归通过，并接入 `pnpm test:unit` / `pnpm check`；Windows 未设置连接变量时，`pnpm backend --port 8127` 实际复用本地配置、完成数据库准备及增量迁移、启动 API，健康接口返回200，未登录会话接口返回401。临时 API 验证后停止，保留原数据库和数据卷。本次未执行WSL实机启动或完整业务验收，不替代阶段历史收据。

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

2026-09-29 阶段1页面整体美化（对齐 ChatGPT 网页版观感）：样式统一收敛为 Tailwind utility 写法，旧手写语义组件类（`.support-shell`/`.composer`/`.message` 等）保留为测试钩子但不再携带样式；`style.css` 新增 `@utility` 公共控件（`btn`/`btn-primary`/`btn-danger`/`btn-ghost`/`btn-icon`/`field`/`card`/`link-inline`/`eyebrow`）、颜色 token（`accent`/`status-strong`/`user-bubble` 等）与两个自定义断点 variant `page:`（≥720px，页面导航布局）和 `side:`（≥900px，会话侧栏布局）。链接一律无默认下划线；只有正文段落内链接使用 `link-inline`（单下划线）。新引入直接依赖 `lucide-react` 1.48.0 用于 18px 细线图标（AGENTS.md 允许有真实消费者时接入；shadcn/cn/Sonner 仍不引入）。会话侧栏新增桌面端折叠/展开（状态持久化到 localStorage 键 `psyevo.chat-sidebar-collapsed`，属性 `data-sidebar-collapsed`，与窄屏抽屉 `data-sidebar-open` 互不影响）；会话列表项 hover/focus 显示删除入口按钮，复用既有确认删除流程（`SessionDeleteDialog`，当前会话删除后仍回 `/chat`）。所有测试依赖的语义 class 钩子与可访问名称保持不变。

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
# 同会话多轮增量检查

2026-09-29页面交互调整：有效轮次直接显示在聊天区，旧版本单独折叠；最新回答下可直接重新生成。发送/停止未确认时才提供带进度和结果的状态检查。浏览器组新增“start请求未送达→检查结果→幂等重试”，保留回执丢失、历史分页和旧分支隔离测试；不调用真实Provider。

普通回归复用 `backend/.venv/Scripts/python.exe -X utf8 scripts/check_step03.py --step07 --web-port 3127 --api-port 8127 --tls-port 3427`；新增受控模型与PostgreSQL用例自动参与原门禁，连续消息页面用例纳入STEP06浏览器组。

仅显式执行真实两轮合成验证时，在独立PowerShell进程加载ignored配置：`. ./.env.step08.ps1`，再执行 `backend/.venv/Scripts/python.exe -X utf8 scripts/check_step03.py --multiturn-live --web-port 3127 --api-port 8127 --tls-port 3427`。该入口先跑fake回归，再在隔离合成库启动live API和独立Worker；前端/build/browser不接收Provider密钥。新live用例替代该次门禁的历史STEP08 live旅程，手动命名测试会话以避免额外标题调用，固定两次support调用，不自动重试。原 `--step08-live` 行为不变；本次收据写入新.artifacts目录，不覆盖STEP08历史记录。
## 2026-09-29 第一阶段质量审查修复

新增迁移`k011_provider_tests`为显式模型配置测试保存无正文回执。普通启动沿用已有增量迁移入口；手动启动前在backend执行`uv run --no-sync alembic upgrade head`。保留原数据库和历史回执，有测试记录时拒绝破坏性降级，不引入新配置文件或凭据读取方。

模型配置测试要求`Idempotency-Key`，相同owner/键/配置版本只执行一次；同账号仅一个在途测试，启动间隔至少10秒。测试运行中不接收新聊天，已有聊天运行中也拒绝新测试。删除个人配置撤销相关测试，退出/密码操作撤销该身份的测试；超时和未知结果保留预占，不自动重发。`GET /api/v1/me/model-settings/test/{request_key}`核对本人的状态和无正文调用回执。原独立CLI合成probe仍沿显式调用流程，不自动执行。

输出规则版本为`behavior-rules/2`；身份、来源、整稿发布、取消及普通run预算不变。第一阶段统一回归使用`backend/.venv/Scripts/python.exe -X utf8 scripts/check_step03.py --step07 --web-port 3197 --api-port 8197 --tls-port 3497`，额外需要模型设置检查的8110/3110空闲。所有服务顺序检查，避免多个Vite实例同时修改依赖优化缓存；`scripts/check_model_settings.py`每次生成新的`model-settings-check-*`产物目录。

当前实现与验证状态见[本次修复记录](PsyEvoAgent项目计划/阶段1/evidence/S1-AUDIT-REPAIRS/README.md)，历史记录保持原时点。

## 阶段2 STEP02记录验收（2026-09-30）

在仓库根目录执行：

```powershell
backend/.venv/Scripts/python.exe -X utf8 scripts/check_step03.py --s2-step02 --web-port 3198 --api-port 8198 --tls-port 3498
```

复用现有随机隔离PostgreSQL容器、白名单测试环境、fake Worker及浏览器入口；端口需空闲，不接管开发服务。追加迁移`l012_records`，不重置数据；普通开发启动继续由既有启动脚本升级到head。本次没有向开发库应用迁移；手动启动者应按既有流程先执行`uv run --no-sync alembic upgrade head`。

入口执行143项数据库/API/迁移和188项后端测试、前端check/build、本步6条及既有35条浏览器检查，另比较真实PostgreSQL重启前后记录、来源关联和删除收据的行数/哈希。最终输出在独立`.artifacts/psyevo-step07-*`目录，目录名沿用已有门禁；receipt.step_id为S2-STEP02。`PSYEVO_S2_STEP02_ARTIFACTS`仅由检查器提供给测试保存截图，不是产品配置，也不读取Provider密钥。没有新依赖、配置文件、SMTP或模型凭据读取方；不可将fake输入捕获称为live兼容验证。实际证据见[本步记录](PsyEvoAgent项目计划/阶段2/evidence/S2-STEP02/README.md)。

## 阶段2 STEP01合同检查（2026-09-29）

在仓库根目录运行`backend/.venv/Scripts/python.exe -X utf8 _check_s2_step01.py --receipt`；WSL使用已有`backend/.venv/bin/python`。脚本仅用标准库读取本阶段合成JSON和01～04文档，不读取环境凭据、网络、数据库或模型，不需启动开发服务。`--receipt`写本步evidence下的独立时间戳文件，不覆盖历史结果；省略该参数则只检查。

本步没有新产品配置读取方、依赖或迁移。来源/用途schema和后续扩展责任见[技术映射](PsyEvoAgent项目计划/阶段2/02-技术方案与实施计划.md#s2-step01-contract)，实际执行见[证据](PsyEvoAgent项目计划/阶段2/evidence/S2-STEP01/README.md)。`_check_docs.py`检查文档合同；两者都不代替新增来源API/DB/模型输入验收。
