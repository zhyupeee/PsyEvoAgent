# 阶段1→阶段2工程合同交接（STEP08.3/.4）

**已冻结：s1-handoff/2026-09-28。** 最终门禁、逐例矩阵及来源复核已完成，冻结文件/hash见[交接清单](closeout/handoff-manifest.json)。权威字段继续维护于[阶段1技术合同](../../02-技术方案与实施计划.md#shared-contracts)，本文件是实际实现入口和已验证边界索引，不建立另一套API/schema。

## 消费边界

| 合同 | 阶段1真实实现及阶段2约束 |
|---|---|
| 身份/owner | FastAPI安全Cookie/Origin/CSRF为唯一业务身份；owner服务端注入，复合外键保留。不可新增第二套身份或把客户端owner当权威 |
| 来源ID/版本 | Conversation.id/version、Message.id/version、Run.session_id/session_version/source_message_version；ContextGrant绑定owner/source_id/source_version/run_id/current_run、撤销及删除。新增资料应按阶段2合同扩展来源，不能把当前只支持conversation的grant当任意来源已实现 |
| 默认配置/历史 | experiment-defaults/1与旧consent分离；历史declined/revoked不封禁基本能力，不伪造用户granted。业务无固定TTL，认证/验证码/deadline独立 |
| run事实/幂等 | PostgreSQL runs+run_executions唯一事实；draft→queued→running→completed/failed/cancelled/interrupted；同owner键和client_message_id唯一。版本/输入fingerprint冲突拒绝；修订分支不修改旧输入 |
| 版本冻结 | support-policy/1、behavior-rules/1、support-graph/1、support-runtime/1、experiment-defaults/1；model_ref与provider_ref随start冻结，进程配置漂移零调用。未声明原生structured schema已验证 |
| 预算 | live一次调用、最多8192账本token信封、每次输出最多1024、默认60秒且上限120秒；原deadline不续期，Worker使用冻结输出上限；SDK重试0。价格/currency未知、max_cost/reserved_cost/actual_cost=null；unknown usage保留预占，不能当零或套fake价格 |
| 整稿出口 | 原始流私有，完整schema/tool/refusal/finish/usage/规则通过后，同事务写assistant、单条message.delta和completed。公开public-run-events/1；128事件窗口，过期410读授权快照；当前只有completed快照output，无部分正文 |
| 取消/恢复 | owner锁+版本CAS+generation阻止迟到写；取消关闭本地流，未知远端用量保留。running任务不重跑，按原deadline interrupted；写失败回滚，commit丢回执读取终态，不再发Provider |
| 删除 | 先持久屏障/取消，再串行清理在线消息/事件/反馈/来源；失败可重试。无正文墓碑、幂等摘要和用量保留。external_provider_status从持久ModelCall判断，unknown不能被当前disabled配置抹成N/A |
| 后续记忆 | 本阶段没有LangMem提取、Memory/job/checkpointer/向量存储；阶段2必须另验自动提取、来源校验、删源传播、推断标签和抑制标记。只有已授权、未删除的输出可供后续消费者使用 |

实际代码入口：backend/app的config、api、runs、run_worker、run_stream、support、provider、history、deletion、models；前端复用TanStack Start/Router/Query/Form/Zod。最高迁移h007_history_feedback；本步无新迁移。锁定依赖以backend/uv.lock及frontend/pnpm-lock.yaml为准，不从文档版本猜测环境。

## 来源和真实依赖复核

- S01/S02为架构设计输入，不是本仓库运行证据；原版R03练习交互只作适配参考，本项目独立实现合成文字，未导入原媒体或私人资料。精确版本/许可继续引用[唯一来源索引](../../02-技术方案与实施计划.md#source-index)，历史未核项不补造commit或许可。
- 当前实际消费的LangChain Core/OpenAI、LangGraph、OpenAI SDK/HTTPX2、FastAPI/SQLAlchemy/PostgreSQL版本与hash随最终收据和锁文件冻结。LangSmith追踪显式关闭，未启用OTel/Langfuse、Kafka、对象存储或pgvector；不因阶段2准备预装。
- 实验输入为仓库fixtures/S1-STEP01/scenarios.json及页面测试合成文字；证据区分fake、受控SDK、真实Provider、真实SMTP。无真实私人对话用于验收。
- 用户配置Provider为ai.hybgzs.com兼容接口、grok-4.7；地区/保留/费用/远端取消删除未知。应用不对这些未知条件作供应商保证。SMTP密码和Provider key仅本地忽略文件显式注入，不属于交接包。

## 运维、回归与剩余能力

启动/配置读取方/隔离验收命令见[DEVELOPMENT](../../../../DEVELOPMENT.md)。API导入/reload不启Worker；新阶段继续独立进程，默认Compose只起PostgreSQL，测试仅随机合成库。任何后续修改均须回归owner、来源版本、start幂等、取消、删除、账本与public SSE，不把本次收据当永久通过。

保留限制：专业审阅/人工心理支持质量/临床有效性未验证；安全公共分块未实现，采用合同允许的整稿路径；未审练习仍test-only；live运行仍限隔离合成test库。持久checkpointer/应用备份未配置，相关清理N/A；部署/真实业务连续运行未验收。本次没有实际远程发布或后续阶段功能。

当前交接可承接的下一步是S2-STEP01来源与用途合同；其余阶段2步骤保持原计划，本轮不执行。
