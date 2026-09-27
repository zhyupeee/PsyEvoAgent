# STEP07 评审修复（2026-09-27）

本次在已有暂存的STEP07实现上修复三项P2；未改写原交付收据、未提交Git、未触及开发库或真实Provider。

- 草稿读取：尚无RunExecution时，查询该run的继承grant，复用owner/run/purpose、撤销/删除和来源版本检查。current-run/snapshot拒绝失效草稿，history不返回其正文。
- 修订恢复：文本先经Zod规范化并检查空白、长度及NUL，再保存待重试的幂等尝试；保留实际请求未确认时的原key重试约束。
- 跨标签页：通知携带类型及会话ID；普通变化定向刷新会话列表和相关会话查询，不重载无关页面。删除/退出及BFCache恢复继续重新核权。

新增三种PostgreSQL授权失效回归；真实页面覆盖空白修订后更正、空修订后重新生成，以及改名/归档/恢复/重新生成/修订时跨标签页未提交composer、revision、feedback的保留。

首轮本地收据：`.artifacts/psyevo-step07-a3c5dd804b01/receipt.json`。68项PostgreSQL/API/迁移、66项后端回归、前端check/build及前置页面通过；新增页面用例等待到旧分支终态后过早操作折叠表单，3项STEP07页面通过、1项超时。测试已改为明确等待新分支input_version=2且completed的current-run响应。

最终完整门禁通过：`backend/.venv/Scripts/python.exe -X utf8 scripts/check_step07.py --web-port 3107 --api-port 8107 --tls-port 3447`，本地目录`.artifacts/psyevo-step07-7389fafce26b/`。68项PostgreSQL/API/迁移、66项后端回归、前端check/build、9项身份页面、1项HTTPS、1项SSE、5项STEP06及4项STEP07页面全部通过；数据库重启直查、文档检查和diff检查通过，测试容器已清理。

保留[完整收据](review-fixes/receipt.json)、[PostgreSQL用例报告](review-fixes/postgres-tests.xml)、[STEP07页面日志](review-fixes/step07-browser.txt)及[重启核对日志](review-fixes/step07-restart-facts.txt)。收据中的其他日志位于上述本地目录，不将未复制的日志标为已归档。所有执行仅使用随机独立PostgreSQL、合成账号及fake Worker；不代表STEP08、真实SMTP/Provider、内容专业审阅或整阶段业务验收完成。
