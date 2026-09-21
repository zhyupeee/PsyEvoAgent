# Repository Guidelines

## Project Structure & Module Organization

This workspace contains planning documents plus the S1-STEP02 engineering foundation in backend/, frontend/, and scripts/. Business features are not implemented. `PsyEvoAgent项目计划/阶段1/`–`阶段7/` and `阶段5A/` contain 32 documents: `01` for goals, `02` for technical contracts, `03` for acceptance, and `04` for ordered implementation steps and checks. Original, RSI, and audit requirements are integrated by topic; do not recreate separate upgrade or audit editions. Stage 5A specifies role collaboration.

Read the [project guide](README.md) and [shared contracts and implementation evidence](PsyEvoAgent项目计划/阶段1/02-技术方案与实施计划.md#missing-sources). The two historical overviews have been integrated into the stage documents, including core entities and source provenance. Submission/handoff materials remain unavailable; local engineering receipts exist under stage 1 evidence, but are not business acceptance; do not invent them. Historical source checks are not current execution evidence.

## Build, Test, and Development Commands

`rg --files` inventories documents. Application manifests and locks now exist. See DEVELOPMENT.md for verified Windows/WSL commands and the Linux/WSL kernel-isolated PR gate in scripts/check_step02_isolated.sh. No Compose or deployment CI exists. Inspect actual scripts before documenting commands.

Once implemented, default to local Windows/WSL processes: TanStack Start through the actual `pnpm dev` script, FastAPI through uv with development reload, and an independent Python Worker when needed. Never start consumers during API import or reload.

Compose defaults to PostgreSQL only; application containers belong to separate CI, production, or explicitly selected isolation workflows. Python libraries are dependencies; pgvector is a PostgreSQL extension. Enable Kafka, object storage, and observability services only for demonstrated consumers and capability gaps. Preserve production assets and research isolation. These local-development rules override conflicting older plans; identify affected files before edits.

## Frontend Architecture and Consumer Gate

Before frontend work, read the [frontend responsibility contract](PsyEvoAgent项目计划/阶段1/02-技术方案与实施计划.md#frontend-stack-contract) and DEVELOPMENT.md, then inspect actual manifests, lockfiles, routes and consumers. React + TypeScript + TanStack Start/Router is the existing mainline; reference projects do not authorize Next.js, React Router or custom Vite SSR.

Add a dependency only when a current consumer needs it, no equivalent implementation exists, and it belongs to the agreed mainline. Query owns business server state; Form + Zod owns new business forms; Store is only for genuinely shared client state. The health probe currently uses a centralized fetch helper and component-local state; do not migrate it just to install these libraries. shadcn/cn/Lucide/Sonner are deferred until real UI consumers, as explicitly selected in the frontend audit. Do not prebuild empty feature folders, providers or adapters. Inspect existing conflicting dependencies and migration risk before proposing removal; do not uninstall business dependencies without authorization.

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
