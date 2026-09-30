# S2-STEP02 审查修复

日期：2026-09-30。范围为本次审查的六项问题，涉及 S2-A01/S2-A02/S2-A03；原实施记录及历史收据保持原时点。本次开始时 S2-STEP02 改动已暂存，修复保留这些改动。

## 实现

- 发送响应丢失后，核对到已接受的同一运行时清除所选记录参数；后续发送必须重新选择才会携带记录。`404/not_found` 明确拒绝后可移除附件，网络错误等不确定结果仍保留保护。
- 保存时保留表单和保存状态快照。直接收到保存响应或核对收据后，对比当前编辑，保留后续改动和离开页面提醒；后续保存使用已创建记录的 ID 与提交后的版本，继续沿用乐观冲突检查。
- 睡眠顺序和跨度统一按 UTC 瞬时值计算，继续验证 IANA 时区与输入偏移并按记录时区展示。笔记日期筛选先转换到记录时区；未填写时区时使用 UTC，未填写时间的记录不匹配日期筛选。
- 每次打开会话删除确认重新查询关联摘记；查询期间及失败时禁止首次确认。已确认但响应丢失的删除仍可用原幂等键重试。

未增加依赖、迁移、Agent、后台任务或凭据读取方式。

## 验证

复用 `backend/.venv/Scripts/python.exe -X utf8 scripts/check_step03.py --s2-step02 --web-port 3198 --api-port 8198 --tls-port 3498`。只使用随机隔离 PostgreSQL、合成账号和 fake Worker，不连接开发数据库或调用真实 Provider/SMTP。

新增 API 回归覆盖笔记本地日期、空时区/空时间，以及 DST 重复小时、跨夜、春季跳时的创建与 PATCH/GET 一致性。浏览器回归覆盖四种编辑场景的丢失回执恢复、成功响应等待期间的保存状态修改、附件仅用于一轮、404 后移除，以及删除预览的等待/刷新失败。

最终完整门禁 `.artifacts/psyevo-step07-c215a822e1dc/` **通过**，见[机器收据](review-repairs/receipt.json)。198 个工程文件 SHA-256 与最终工作区一致；之后仅补充本次证据文档。隔离测试容器已[清理](review-repairs/database-cleanup.txt)。

| 检查 | 最终结果 |
|---|---|
| PostgreSQL/API/迁移 | [150 项通过](review-repairs/api-migrations.txt)，其中记录场景 33 项；包含新增的 7 项参数化/独立用例和原有睡眠用例的 PATCH/GET 断言 |
| 后端 | [188 项通过](review-repairs/foundation.txt)；Ruff、格式、mypy、锁文件及 schema 无漂移检查通过 |
| 前端 | [check](review-repairs/frontend-check.txt)（类型、lint、7 项 Node + 7 项 Vitest、格式）及 [build](review-repairs/frontend-build.txt) 通过 |
| 记录浏览器 | [14 条通过](review-repairs/s2-step02-browser.txt)，包含本次新增 8 条恢复/确认回归 |
| 既有浏览器 | 35 条通过：入口 10、HTTPS 1、SSE 1、[聊天 17](review-repairs/step06-browser.txt)、[历史 5](review-repairs/step07-browser.txt)、模型设置 1；本次合计 49 条 |
| 实际重启 | 六类记录/关联/收据的[行数与哈希](review-repairs/records-restart.json)在 PostgreSQL 重启前后[完全一致](review-repairs/s2-records-after-restart.txt)，既有阶段1重启检查也通过 |

中间门禁 `.artifacts/psyevo-step07-ebf40ca9298d/` 的数据库与后端测试通过，前端 lint 发现恢复 effect 的对象依赖不稳定；改为布尔依赖后重新通过上述完整门禁，未覆盖原失败记录。

验证边界：Windows 语言层网络限制不代表 WSL 内核隔离；不涉及真实模型质量、公开发布或 S2-STEP03。
