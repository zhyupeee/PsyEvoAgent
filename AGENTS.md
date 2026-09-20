# Repository Guidelines

## Project Structure & Module Organization

This workspace contains planning documents, not application code. `PsyEvoAgent项目计划/阶段1/`–`阶段7/` and `阶段5A/` contain 32 documents: `01` for goals, `02` for technical contracts, `03` for acceptance, and `04` for ordered implementation steps and checks. Original, RSI, and audit requirements are integrated by topic; do not recreate separate upgrade or audit editions. Stage 5A specifies role collaboration.

Read the [project guide](README.md) and [shared contracts and implementation evidence](PsyEvoAgent项目计划/阶段1/02-技术方案与实施计划.md#missing-sources). The two historical overviews have been integrated into the stage documents, including core entities and source provenance. Submission/handoff materials and actual implementation evidence remain unavailable; do not invent them. Historical source checks are not current execution evidence.

## Build, Test, and Development Commands

`rg --files` inventories documents. No application manifests, lockfiles, Compose configuration, or verified build/start commands exist here. Inspect actual scripts before documenting commands.

Once implemented, default to local Windows/WSL processes: TanStack Start through the actual `pnpm dev` script, FastAPI through uv with development reload, and an independent Python Worker when needed. Never start consumers during API import or reload.

Compose defaults to PostgreSQL only; application containers belong to separate CI, production, or explicitly selected isolation workflows. Python libraries are dependencies; pgvector is a PostgreSQL extension. Enable Kafka, object storage, and observability services only for demonstrated consumers and capability gaps. Preserve production assets and research isolation. These local-development rules override conflicting older plans; identify affected files before edits.

## Style & Naming Conventions

Preserve Chinese filenames, stage numbers, and terminology. Keep Markdown headings, tables, relative links, and fenced JSON consistent. Retain `S*-T*`/`S*-A*` identifiers; RSI tasks use `RSI-S*-T*`. Step IDs use `S*-STEPnn`, with `.1` etc. for atomic actions. Keep API/schema definitions in 02 and acceptance definitions in 03; 04 references them without duplicating contracts. Stage 5A owns the stage 5 MA handoff tasks and joint acceptance; stage 7 separates pilot and formal protocol freezes.

Future code should use four-space Python and two-space TypeScript/JSON indentation, following actual formatter configuration. Ruff and mypy are planned, not configured.

## Testing Guidelines

Check links, anchors, table columns, fences, JSON, identifiers, and cross-document consistency. The 153 acceptance cases are plans, not executed tests; no coverage percentage is established.

Future Python tests use pytest and `test_*.py`; run `uv run pytest` only after dependencies and tests exist. Use isolated test databases and synthetic fixtures. Distinguish mock results, real execution, and unexecuted checks.

## Commit & Pull Request Guidelines

Inspect current Git history and staged/unstaged changes before editing; preserve existing user changes. Prefer focused imperative messages, such as `docs(stage4): clarify optional Kafka`.

PRs should identify affected stages, contract changes, acceptance IDs, validation performed, and remaining limitations.

## Security & Agent Instructions

Inspect existing edits before writing. Never expose credentials or private conversations. Document configuration readers and loading rules; keep real credentials ignored. Preserve data during routine restarts; destructive resets, paid calls, and production changes require explicit authorization.

Honor review-only requests. Separate planned, implemented, and verified status. If ResearchVault guidance is available, read it once per session and update it only within authorized scope; it is absent from this checkout.
