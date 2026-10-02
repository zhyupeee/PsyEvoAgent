# S2-STEP04 审查修复（2026-10-02）

本轮在现有暂存/未暂存改动上修复四项审查意见，不推进STEP05。保留原STEP04及更早的全部收据；本轮检查只使用隔离合成数据库、fake模型和Chromium合成页面数据。

## 实现

- 记忆保存事务冻结摘记底层消息引用；后续改链或删源清理后，遗忘仍抑制提取时的原消息，不误抑制新引用。新增增量迁移 `o015_memory_sources`，不修改既有迁移。
- 删除会话时，外部调用回执覆盖删除范围内的关联摘记任务；只要持久调用记录表明发生过外部调用，就保留 `unknown`，清理和重试不使它变成 `not_applicable`。
- 遗忘冲突后，用户核对最新内容、再次确认，提交核对后的版本号；来源不可用的记忆也允许核对并遗忘。
- 更正、停止、遗忘弹窗关闭时返回调用入口；条目移除或入口禁用后，返回状态筛选。放弃更正的二次弹窗返回编辑区。

## 验证

完整门禁通过。新增6项PostgreSQL行为回归、1项升级/保留测试及9项Chromium恢复/焦点用例，接入原测试入口。

最终轮为 `.artifacts/psyevo-step07-646f1ac612ee`；[机器收据](review-repairs/windows/receipt.json)记录 `passed: true`，没有复用历史PG结果。完成后核对[219个工程文件SHA-256](review-repairs/windows/source-verification.json)，与本轮收据全部一致。

| 检查 | 本轮实际结果 |
|---|---|
| PostgreSQL/API/迁移 | [217/217通过，无跳过](review-repairs/windows/postgres-tests.xml)；包含快照回填、来源改链/清理后遗忘、摘记外部回执及失败重试 |
| 后端基础与静态检查 | [190/190通过](review-repairs/windows/foundation.txt)；[Ruff](review-repairs/windows/lint.txt)、[格式](review-repairs/windows/format.txt)、[mypy](review-repairs/windows/types.txt)、[增量迁移](review-repairs/windows/migration.txt)、[结构无漂移](review-repairs/windows/schema-drift.txt)通过 |
| 前端 | [pnpm check](review-repairs/windows/frontend-check.txt)及[build](review-repairs/windows/frontend-build.txt)通过，含7项Node和7项Vitest |
| 浏览器 | 63/63通过：入口10、HTTPS 1、记录14、SSE 1、聊天/锚点18、历史5、模型设置1、[记忆13](review-repairs/windows/s2-step04-browser.txt)。记忆包含9项新增合成API恢复/焦点测试与4项实际API/fake Worker页面旅程 |
| 真实进程恢复与重启 | 原job probe及记忆Worker各3处强杀恢复通过；[PG重启前](review-repairs/windows/memory-before-restart.txt)/[重启后](review-repairs/windows/memory-after-restart.txt)全列指纹一致，包含新增source_snapshot |
| 文档与清理 | [文档](review-repairs/windows/documents.txt)、[差异](review-repairs/windows/diff.txt)检查通过；隔离容器已[清理](review-repairs/windows/database-cleanup.txt) |

初次类型检查失败的[收据](review-repairs/initial-type-failure/receipt.json)和格式检查失败的[收据](review-repairs/initial-format-failure/receipt.json)均保留。前者确认共享扁平引用类型不能放嵌套快照，最终采用增量独立字段；后者为编辑后的换行格式，已由Ruff规范化。失败轮未作为通过证据。

完整命令：

```powershell
backend/.venv/Scripts/python.exe -X utf8 scripts/check_step03.py --s2-step04 --web-port 3204 --api-port 8204 --tls-port 3504
```

## 边界

迁移只能从仍匹配提取版本的同owner摘记回填旧快照。升级前已改写或清理且未保存历史引用的记忆，其旧底层来源无法可靠重建；不将当前引用当作旧版本证据。新提取快照覆盖本次报告的改链及清理场景。

未读取或迁移开发数据库，未调用真实Provider、发送SMTP或发布服务。回执测试中的USD是合成持久账本夹具，不代表真实外部调用或外部删除成功。未复跑WSL内核隔离；历史live收据不作为本次改动的重新验证。
