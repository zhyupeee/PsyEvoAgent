# 阶段1工程验收矩阵（STEP08.2）

协议：s1-engineering-acceptance/2026-09-28，依据[当前验收标准](../../03-测试与验收标准.md#step08-engineering-scope)。**21项所列工程期望全部通过，矩阵已冻结。** 本页不是新业务合同，不新增编号；不能推导心理支持质量、专业内容获准或153项跨阶段业务全通过。最终运行、环境/版本/hash、时间及失败记录统一关联[收尾记录](engineering-closeout.md)，机器可读结果见[CaseResult](closeout/case-results.json)。

证据域：`test_support.py`是真实单LangGraph+LangChain fake候选；`test_provider.py`是真实SDK+受控传输；`test_live_runs.py`是真实PostgreSQL+受控SDK；其余API/迁移使用真实隔离库。浏览器身份/资源/历史测试使用fake模型或邮件替身；`live.spec.ts`单独调用真实Provider。测试均位于实际backend/tests、frontend/tests，无虚构测试入口。

| 既有用例 | 工程预期 | 实测观察与定位 | 不包含/限制 |
|---|---|---|---|
| S1-A01 | 固定冷启动/倾听/澄清/分析/拒绝/欺凌场景满足已定义路由、schema和规则 | test_support的13场景正反例；live.spec真实只倾听旅程 | 人工支持质量评分未执行，有限规则不证明开放域语义正确 |
| S1-A02 | 偏好持久化、失败不假保存、手机键盘与账号隔离 | test_pages、support.spec、privacy.spec及工程页面检查 | 视口测试不替代实体手机软键盘 |
| S1-A03 | 无模型独立练习、跳过/退出、版本真实 | test_pages模型关闭仍可练习且无调用；support.spec练习进出 | unreviewed保留；development仍不可用，无专业认可 |
| S1-A04 | 本人历史搜索归档、不可变修订与新旧分支隔离 | test_history及history.spec搜索/归档/修订/重生成与跨标签保留 | 无后续记忆或记录能力 |
| S1-A05 | 幂等start、断流恢复、CAS唯一终态 | test_runs并发/重放/取消，runs.spec网关，live.spec刷新一次调用 | 远端计费/取消unknown |
| S1-A06 | 先持久删除屏障，失败可重试，无正文复活 | test_history故障清理与重连；live删除/重启直查；test_live_runs外部状态持久 | checkpointer/备份未配置为N/A；外部Provider删除unknown |
| S1-A07 | 固定高风险/未知资源场景不编联系方式、不公开违规候选 | test_support的support_unknown/support_expired与负例；资源API返回真实unknown | 专业危机干预流程效果和真实机构服务未验证 |
| S1-A08 | 自愿反馈、空理由、真实ID及唯一幂等 | test_history及history.spec丢回执/失败重试 | 无反馈不推导负面评价 |
| S1-A09 | 有界预算/超时/schema/tool停止，不泄漏密钥与原始错误 | test_support、test_provider及test_live_runs配置漂移/故障 | 真实价格与精确tokenizer未知，实际usage超界判失败 |
| S1-A10 | 真实页面→API→库→Worker→Provider→检查→公共SSE | live.spec核对SSE=快照=DOM；step08_receipt重启直查唯一调用 | 整稿路径，非公共安全分块 |
| S1-A11 | 授权事件、游标窗口与快照、取消/完成一致 | test_runs/test_run_stream与runs.spec；过期410、错owner/删源拒绝、实际SSE | 不把LangGraph内部事件当公共事件 |
| S1-A12 | 429/超时/断流/缺usage/tool拒绝，有界重试与账本unknown | test_provider 22项协议/错误/取消检查，终局用量去重且冲突拒绝；test_support预算；live反例与真实观察分列 | 未人为制造真实限流，受控错误不是Provider实测能力 |
| S1-A13 | 锁、lint/types、前后端、真实库、隔离出口、无业务数据污染 | 完整Windows gate和WSL内核gate；探针缺配置拒绝；临时容器清理 | WSL工程域与Windows真实库/live域分列 |
| RSI-S1-A01 | 冷启动、拒绝、欺凌、结束固定正反例不过边界 | test_support场景选择与内容规则；trace禁止外发 | 独立人工rubric未执行，不冒充专业评价 |
| RSI-S1-A02 | 邮箱验证建号、登录直接进入、unknown年龄、无伪造consent | email_identity/registration/experiment_config及身份页面 | 真实SMTP运输另验；业务全链邮件仍用替身 |
| RSI-S1-A03 | 来源owner/version/run/删除核权，历史consent不阻塞 | test_registration/test_experiment_config/test_history来源失效回归 | 无后续记忆授权实现 |
| RSI-S1-A04 | 主动事件幂等、区间并集、闲置排除、未知时长null | test_runs互动去重/漂移与数据库重启唯一计数 | 不把停留时长解释为临床指标 |
| RSI-S1-A05 | 后半段危险/排他/诊断候选不先公开 | test_support负例、test_live_runs私有流暂停时零delta、tool/refusal异常拒绝 | 有限规则不等于任意中文语义安全 |
| RSI-S1-A06 | 评估异常/schema/预算不假pass，输出为空且stop_reason真实 | test_support评估超时/错误、test_provider失败及账本unknown | 无专业获准回退；受控停止为当前工程行为 |
| RSI-S1-A07 | 并发终态唯一、删后不可读、故障不重复副作用 | test_runs竞态、test_history、test_live_runs写失败/commit丢回执及live取消删除 | 真实Worker进程kill未新增专项；原deadline恢复在真实库测试 |
| RSI-S1-A08 | 键盘/移动/减少动画、可跳过反馈可退出，无角色菜单 | support.spec/history.spec与账号退出/返回检查 | 不含后续阶段入口 |

受控候选正反例必须同时通过对应断言；不能只统计成功回答。状态与分母以JUnit和命令收据为准。SMTP服务器接受+收件确认单独收据支持身份运输可用性，不额外增加业务编号。
