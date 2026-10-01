# S2-STEP03 审查修复

日期：2026-09-30。范围为任务跨账号队列饥饿和探针幂等回执碰撞两项审查问题，涉及 S2-A09/S2-A10 的任务恢复范围。开始时 STEP03 实现已暂存；本次保留已有改动与历史验收收据。

## 实现

- `app.jobs.claim()` 仍按账号锁和 `SKIP LOCKED` 领取任务，每批最多读取 100 个候选；本批未领取到任务时，以可用时间和任务 ID 为游标继续扫描。只有候选耗尽才返回空闲；前面的候选退出活动队列时也不会因偏移分页而漏掉后续任务。
- `app.job_worker.commit_probe()` 继续复用共享 `Idempotency`，仅在已有回执的类型为 `job_probe`、资源 ID 为当前任务且请求哈希一致时接受复用。冲突沿现有 `schema` 失败分支终止，不标记成功、不自动重试，也不覆盖原有笔记回执。

没有新增依赖、迁移、任务类型或 Worker 入口；普通开发仍不入队或消费提取任务。

## 验证

修复前专项运行 `.artifacts/psyevo-s2-review-e102cc6a76c0/`：新增 7 项测试中，6 项负例均复现问题，1 项合法回执复用通过，见[原始输出](review-repairs/before/postgres-tests.txt)和[JUnit](review-repairs/before/postgres-tests.xml)。更早一次本地测试运行因队列 fixture 漏填 `Note.kind` 而失败，保留在 `.artifacts/psyevo-s2-review-87b26bfffee9/`，不作为队列问题复现依据。

修复后专项运行 `.artifacts/psyevo-s2-review-5f4d53980856/` 使用独立临时 PostgreSQL 16.13 容器、合成账号及 fake 模型，结果见[机器收据](review-repairs/receipt.json)：

| 检查 | 实际结果 |
|---|---|
| PostgreSQL job 与记录 API | [69 项通过](review-repairs/postgres-tests.txt)：36 项 job（新增 7 项）与 33 项记录回归；[JUnit](review-repairs/postgres-tests.xml) |
| 新增领取回归 | 同一账号锁阻塞前 100/201 个任务且可用时间相同，后续另一账号任务仍可领取；仅剩锁定任务时返回空闲，释放锁后原任务可领取 |
| 新增回执回归 | 实际笔记 API 占用 `job-probe:<job_id>` 后任务失败、笔记幂等重放仍有效；分别拒绝类型、资源 ID、哈希不匹配，接受完全匹配回执 |
| 真实 Worker 强杀恢复 | [领取后](review-repairs/crash-after_claim.json)、[提交前](review-repairs/crash-before_commit.json)、[提交后](review-repairs/crash-after_commit.json)均通过，每个任务最终只有一条结果回执 |
| 后端 | [190 项通过](review-repairs/foundation.txt)；[Ruff](review-repairs/lint.txt)、[格式](review-repairs/format.txt)、[mypy](review-repairs/types.txt)通过 |
| 数据库 | [迁移至 head](review-repairs/migration.txt)、[schema 无漂移](review-repairs/schema-drift.txt)通过；临时容器已[清理](review-repairs/database-cleanup.txt) |

机器收据记录本次三个修改代码文件的 SHA-256。未访问开发库、真实 Provider/SMTP 或发布服务。本次未重跑浏览器、真实 PostgreSQL 重启及 WSL 内核隔离；原完整 STEP03 门禁是历史证据，不作为修复后的全门禁结果。
