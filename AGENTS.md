# Repository Guidelines

2026-09-29 stage-1 frontend restyle: all stage-1 pages migrated to Tailwind utility styling (ChatGPT-like visual language); old semantic classes (`.support-shell`, `.composer`, `.user-message` …) remain as Playwright test hooks only — do not remove or restyle them. `style.css` is the single style entry: `@theme` tokens plus `@utility` controls (`btn`, `btn-primary`, `btn-danger`, `btn-ghost`, `btn-icon`, `field`, `card`, `link-inline`, `eyebrow`) and custom breakpoints `page:`/`side:`. Links have no default underline; only prose links use `link-inline`. New direct dependency `lucide-react` 1.48.0 provides 18px icons (real consumer = this restyle; shadcn/cn/Sonner still deferred). Chat sidebar now collapses on desktop (`data-sidebar-collapsed`, persisted in localStorage) and lists show a per-item delete entry reusing the existing confirm-delete flow. Accessible names and test hooks unchanged; verify with `pnpm check`/`pnpm build` before the STEP browser gates.

2026-09-29 S1 model-settings adds official/personal API selection, independently encrypted credentials, private per-run snapshots shared by reply/title, and automatic development config-file refresh. Ordinary start-dev manages API/Worker together; do not restore unmanaged sibling workers or pass secrets to frontend. Use test_model_config.py, isolated test_model_settings_api.py and scripts/check_model_settings.py. Current evidence: stage1/evidence/S1-MODEL-SETTINGS/README.md. Preserve staged changes and historical receipts; stage2 order, exercise and publication gates are unchanged.

2026-09-28 local chat repair: the user explicitly authorized real AI chat on the current local development database. The user also authorized AI enabled by default on ordinary local startup: `scripts/start-dev.ps1` (or `pnpm backend` without an explicit database) loads ignored `.env.step08.ps1`, enables live API and starts a separate Worker; `-DisableSupport` opts out, and `-PrepareOnly` skips Provider loading and Worker startup. Development live is restricted to loopback `psyevo_synthetic_dev` with credentials. Test databases, fake/exercise gates and publication restrictions remain unchanged. This supersedes the older test-only live restriction below for this authorized local development use only.

> 当前按[内部实验执行约定](EXPERIMENT.md)推进：可通过指定HTTPS地址分享；目标注册先完成邮箱验证码校验，登录后直接进入，无年龄或用途确认，不设公众资格、真人告知或期限审批前置。业务不设固定TTL。邮箱身份已实现；真实 SMTP 尚未配置，验证范围见阶段1 STEP03.5 记录。

## Project Structure & Module Organization

2026-09-28 STEP08 is COMPLETED for the user-confirmed internal-experiment engineering scope: real SMTP delivery confirmed, live full-buffer web journey and restart facts passed, 74 PostgreSQL/API/migration tests, 92 backend tests and 21 browser checks passed; WSL kernel gate passed. Canonical current records: STEP08/engineering-closeout.md, engineering-matrix.md and stage2-handoff.md. Provider terminal usage is deduplicated by identical input/output/total counters; conflicting counters fail closed. Historical totals may include SDK duplication and are not vendor billing evidence. Professional/clinical evaluation and safe public chunks remain unvalidated, not claimed passed. Earliest unimplemented step is S2-STEP01; do not broaden existing synthetic live or exercise gates implicitly.

2026-09-28 user-selected STEP08 completion scope is internal-experiment engineering acceptance (EXPERIMENT.md and stage1/03#step08-engineering-scope). Professional review/clinical evaluation remain unverified but are no longer prerequisites; the blank review template is removed. Full Buffer Review is the enabled path; safe public chunks remain unimplemented and must not be claimed tested. Do not widen live synthetic-database or test-only exercise gates because of this scope change. Current closeout, 21-case matrix and stage2 handoff are under STEP08/engineering-closeout.md. SMTP delivery is checked separately by app.smtp_probe using explicit authorized local configuration; never auto-send from PR tests. Preserve historical receipts and staged user changes.

2026-09-27 STEP08 continuation adds explicit live mode only for isolated synthetic test databases, through existing API/Worker/Support and full-buffer output. Provider credentials were supplied locally; initial real internal-stream PoC passed after adding compatible max_tokens, with usage checks retained. Use scripts/check_step08.py --live after explicitly loading local process configuration; never inject the key into browser/build processes. External deletion status derives from persisted call receipts, not current settings. Safe chunks/professional content/SMTP and full stage handoff remain unresolved; see STEP08/continuation.md for current evidence. Earlier entries below are historical slices.

2026-09-27 STEP08.1 is partially implemented: `app.provider` and `app.provider_probe` add an explicit synthetic internal-stream PoC through the existing Support graph. The user selected `https://ai.hybgzs.com/v1` / `grok-4.7` and will fill the ignored local `.env.step08.ps1` key. Live verification is BLOCKED until then; API/Worker remain disabled/fake, and webpage live integration, safe chunks and stage handoff remain unimplemented. Reuse `tests/test_provider.py` for controlled SDK tests and `scripts/check_step07.py` for regression; see STEP08 evidence and DEVELOPMENT for the separate explicit live command. Do not call controlled transport tests Provider observations or advance STEP08.2–.4 before .1.

2026-09-27 STEP07 implements owner-scoped history/archive, immutable input revision/regeneration branches, voluntary idempotent feedback and confirmed deletion with durable blocking/retryable cleanup. Reuse `scripts/check_step07.py` for isolated PostgreSQL + actual page acceptance. `h007_history_feedback` adds only feedback/run_branches; existing messages/run/SSE/Worker remain authoritative. No persistent checkpointer/backups/live Provider configured; deletion receipts state these as not applicable and retain content-free tombstones/usage metadata. Evidence: `PsyEvoAgent项目计划/阶段1/evidence/S1-STEP07/README.md`. STEP08 live integration/full-stage handoff remain unimplemented; below are historical slices.

2026-09-25 STEP06 implements chat/current-turn recovery, independent synthetic exercise/resources and preferences UI. Reuse `scripts/check_step06.py` for isolated PostgreSQL + real page acceptance; `backend/app/pages.py` adds only current-turn/static-resource read models. No new schema, dependencies, Agent loop or Worker. Unreviewed exercise steps are test-only; development returns unavailable. STEP07 history/revision/deletion/feedback remain unimplemented. Current evidence: `PsyEvoAgent项目计划/阶段1/evidence/S1-STEP06/README.md`; below are historical slices.

2026-09-24 STEP05 adds durable start/idempotency, native SSE replay/snapshot, cancel CAS, interaction dedupe and a standalone synthetic Worker in `backend/app/runs.py`, `run_stream.py`, and `run_worker.py`. Reuse `scripts/check_step05.py` for disposable PostgreSQL + real gateway acceptance; `app.worker --support` requires explicit test-only fake mode. Default live execution remains disabled. STEP06 chat UI and STEP07 deletion/history remain unimplemented. Current evidence: `PsyEvoAgent项目计划/阶段1/evidence/S1-STEP05/README.md`; earlier paragraphs describe historical slices.

2026-09-24 STEP04 adds `backend/app/support.py`: a synthetic-only single LangGraph, local LangChain fake adapter, budget ledger and fixed output rules. Live model execution, start/SSE APIs and the complete support product remain unimplemented. Use `scripts/check_step04.py`, or the existing WSL isolation entry with `--step04`, for this slice; keep live Provider capabilities unknown until independently verified.

This workspace contains planning documents, the S1-STEP02 engineering foundation, and the S1-STEP03 registration/login/account and experiment-default/source-link slice in backend/, frontend/, and scripts/. Model execution and the complete support product are not implemented. `PsyEvoAgent项目计划/阶段1/`–`阶段7/` and `阶段5A/` contain 32 documents: `01` for goals, `02` for technical contracts, `03` for acceptance, and `04` for ordered implementation steps and checks. Original, RSI, and audit requirements are integrated by topic; do not recreate separate upgrade or audit editions. Stage 5A specifies role collaboration.

Read the [project guide](README.md) and [shared contracts and implementation evidence](PsyEvoAgent项目计划/阶段1/02-技术方案与实施计划.md#missing-sources). The two historical overviews have been integrated into the stage documents, including core entities and source provenance. Submission/handoff materials remain unavailable; local engineering receipts exist under stage 1 evidence, but are not business acceptance; do not invent them. Historical source checks are not current execution evidence.

## Build, Test, and Development Commands

`rg --files` inventories documents. Application manifests and locks now exist. See DEVELOPMENT.md for Windows/WSL commands, the kernel-isolated engineering gate in scripts/check_step02_isolated.sh, and separate real PostgreSQL acceptance in scripts/check_step03.py. Compose runs PostgreSQL only; no deployment CI exists. Inspect actual scripts before documenting commands.

Once implemented, default to local Windows/WSL processes: TanStack Start through the actual `pnpm dev` script, FastAPI through uv with development reload, and an independent Python Worker when needed. Never start consumers during API import or reload.

Compose defaults to PostgreSQL only; application containers belong to separate CI, production, or explicitly selected isolation workflows. Python libraries are dependencies; pgvector is a PostgreSQL extension. Enable Kafka, object storage, and observability services only for demonstrated consumers and capability gaps. Preserve production assets and research isolation. These local-development rules override conflicting older plans; identify affected files before edits.

## Frontend Architecture and Consumer Gate

Before frontend work, read the [frontend responsibility contract](PsyEvoAgent项目计划/阶段1/02-技术方案与实施计划.md#frontend-stack-contract) and DEVELOPMENT.md, then inspect actual manifests, lockfiles, routes and consumers. React + TypeScript + TanStack Start/Router is the existing mainline; reference projects do not authorize Next.js, React Router or custom Vite SSR.

Add a dependency only when a current consumer needs it, no equivalent implementation exists, and it belongs to the agreed mainline. Query owns business server state; Form + Zod owns new business forms; Store is only for genuinely shared client state. The health probe currently uses a centralized fetch helper and component-local state; do not migrate it just to install these libraries. Lucide and Radix UI Select now have real consumers; additional shadcn/ui or Radix UI components must follow the consumer gate, while cn/Sonner remain deferred until needed. Do not prebuild empty feature folders, providers or adapters. Inspect existing conflicting dependencies and migration risk before proposing removal; do not uninstall business dependencies without authorization.

### 强制 UI 规范：禁止使用原生交互组件（2026-09-29）

**业务页面禁止直接使用浏览器原生交互控件，必须统一使用组件库组件。** 新增控件及修改现有控件时，优先复用 `frontend/src/components/ui/`，缺少时按实际需求接入 shadcn/ui / Radix UI 并沿用现有 Tailwind 主题。本规则优先于历史文档中“原生控件足够”或“组件库暂缓”的表述。

- 禁止在业务页面直接使用原生 `<select>` / `<option>`、`<details>` / `<summary>`、`<dialog>`，以及裸 `<button>`、`<input>`、`<textarea>`、原生复选框/单选框等交互控件；分别使用组件库的 Select、Accordion/Collapsible、Dialog/AlertDialog、Button、Input、Textarea、Checkbox/RadioGroup 等。禁止使用 `window.alert`、`window.confirm`、`window.prompt` 作为产品交互。
- 下拉、弹窗、折叠等复合交互必须使用组件库提供的行为，不能仅给原生控件加样式就视为完成替换。当前归档筛选复用 `components/ui/select.tsx`（`@radix-ui/react-select`），不要退回原生 `<select>`。保留可访问名称、键盘操作、焦点管理、确认流程及测试钩子；浏览器用例随组件交互同步更新。
- 本规则约束页面直接使用的交互组件；组件库内部实现所需的原生元素，以及 `<form>`、`<label>`、标题、段落、布局标签和 Router 链接等语义结构正常保留。不得用无语义的 `<div>` 模拟按钮来规避规则。存量原生控件在修改对应控件时迁移，不因本规则擅自扩大当前任务为全站重构。

In frontend/, `pnpm check` runs typecheck, lint, unit tests and Prettier checking. Build and E2E remain separate; this shortcut is not the full Windows/WSL isolation gate. Never hand-edit src/routeTree.gen.ts or remove its generator-owned type suppressions; do not add type-check bypasses to handwritten code. Update current implementation and verification records separately from historical receipts.

## Style & Naming Conventions

Preserve Chinese filenames, stage numbers, and terminology. Keep Markdown headings, tables, relative links, and fenced JSON consistent. Retain `S*-T*`/`S*-A*` identifiers; RSI tasks use `RSI-S*-T*`. Step IDs use `S*-STEPnn`, with `.1` etc. for atomic actions. Keep API/schema definitions in 02 and acceptance definitions in 03; 04 references them without duplicating contracts. Stage 5A owns the stage 5 MA handoff tasks and joint acceptance; stage 7 separates pilot and formal protocol freezes.

Code uses four-space Python and two-space TypeScript/JSON indentation. Ruff and mypy are configured in backend/pyproject.toml; frontend/.prettierrc.json configures Prettier with single quotes and no semicolons. Use frontend/.prettierignore for generated files and artifacts; do not format stage documents through the frontend script.

## Testing Guidelines

Check links, anchors, table columns, fences, JSON, identifiers, and cross-document consistency. The 153 business acceptance cases remain plans; S1-A13 has partial engineering execution only; no coverage percentage is established.

Future Python tests use pytest and `test_*.py`; run `uv run pytest` only after dependencies and tests exist. Use isolated test databases and synthetic fixtures. Distinguish mock results, real execution, and unexecuted checks.

## Commit & Pull Request Guidelines

Inspect current Git history and staged/unstaged changes before editing; preserve existing user changes. Prefer focused imperative messages, such as `docs(stage4): clarify optional Kafka`.

PRs should identify affected stages, contract changes, acceptance IDs, validation performed, and remaining limitations.

## Security & Agent Instructions

Inspect existing edits before writing. Never expose credentials or private conversations. Document configuration readers and loading rules; keep real credentials ignored. Preserve data during routine restarts; destructive resets, paid calls, and production changes require explicit authorization.

Honor review-only requests. Separate planned, implemented, and verified status. If ResearchVault guidance is available, read it once per session and update it only within authorized scope; it is absent from this checkout.

## Experiment Entry Contract

The email-code registration creates an account only after code verification; ordinary email/password login then goes directly to implemented features. Current code uses email/password login with email-code registration/recovery and authenticated password change. Historical username provisioning is disabled. Do not reintroduce age, per-purpose consent, notice, public eligibility or retention approval gates. Keep experiment-defaults/1 separate from historical user decisions; never synthesize granted records. Source links retain owner/version/run/deletion checks without consent prerequisites. Memory is planned to auto-save after extraction and validation, retaining inference labels. Important deletion/external effects still require confirmation. Use additive migrations, preserve historical receipts, and run tests only against isolated synthetic check/migration databases. A configured single HTTPS Origin and same-origin proxy support remote sharing; this does not authorize actual publication.
