# 第一阶段完成质量审查修复

日期：2026-09-29。修复基线为`6b8c48e`；不改写STEP08及此前增量的历史收据，不实施阶段2。本次不调用真实Provider、不发送SMTP、不操作开发库或公开发布。

后续三条输出规则审查意见已修复，当前增量验证见[审查跟进记录](review-followup.md)。下列完整门禁及`verification/`收据保留原执行时点，不代表跟进修改后重新执行了全部门禁。

## 修复内容

- 输出规则升级为`behavior-rules/2`：补直接诊断、全角/不可见分隔字符反例；条件讨论、归属明确的转述及正常日期/数量有正例。未核实联系方式按号码形态及联系语境拦截，不再禁止所有三位数字。有限规则仍不等于开放域语义安全或专业评价通过。
- 模型配置测试新增`k011_provider_tests`迁移及持久回执：同owner单并发、10秒启动间隔、Idempotency-Key重放、原deadline、删除个人配置/退出身份取消、超时或进程中断不自动重发。只保存无正文调用元数据，不保存测试凭据；复用现有Provider和唯一Support图，没有第二个Agent Runtime或常驻消费者。
- 活动run及已保存消息优先于较新空草稿返回；已有queued/running时拒绝新空草稿。前端仅在明确的run_active冲突后刷新当前状态，保留原消息并恢复停止入口；网络回执丢失仍保留原有人工核对流程。
- `RunReads`在同一事务内分批读取执行、消息、来源、grant及公共结果元数据；每次Worker核权重新读取，事务外不缓存权限。时间线和前文选择保持原分页、分支、来源版本和删除语义。
- CSS明确LF检出，消除Windows干净工作树的Prettier失败。
- STEP06门禁纳入7项聊天/反馈专项（含新增的竞争标签页停止回归），STEP07门禁串行加入模型设置页面；超时也保存子进程输出和失败状态。模型设置检查使用新随机产物目录且拒绝占用端口，不覆盖历史材料。
- 页面用例先等待首次身份加载完成，再测量导航坐标；自动标题与手动改名竞态必须验证409提示、草稿保留及用户再次保存，服务端CAS未放宽。

## 验证记录

首轮定向104项规则/Provider/配置检查通过；新增6项隔离数据库回归通过，覆盖并发测试、幂等重放、删除/注销取消、持久回执、过期不重发、空草稿冲突以及批量查询后的撤销核权。25轮前文的读取和复核各最多5条查询，20条时间线含身份检查最多15条查询，由实际SQL事件计数断言。

**最终Windows隔离合成门禁通过。** 命令为`backend/.venv/Scripts/python.exe -X utf8 scripts/check_step03.py --step07 --web-port 3197 --api-port 8197 --tls-port 3497`，退出0；[机器收据](verification/receipt.json)为`passed=true`，33个检查命令完成。原始目录为`.artifacts/psyevo-step07-ab697d43aeb7/`。交付时逐项复核收据中的代码SHA-256，均与当前源码一致；测试容器已清理，未修改开发数据。

| 检查 | 最终结果 |
|---|---|
| PostgreSQL/API/迁移 | [114项通过](verification/api-migrations.txt)，含追加迁移、漂移和有损降级拒绝 |
| 后端常规 | [160项通过](verification/foundation.txt)；Ruff lint/format、mypy、锁检查通过 |
| 前端 | [check通过](verification/frontend-check.txt)：类型、Lint、7项启动入口和7项前端单测、格式；[build通过](verification/frontend-build.txt) |
| 浏览器基础与身份 | [10项通过](verification/browser.txt)，[HTTPS 1项](verification/https-browser.txt)、[SSE网关1项](verification/step05-gateway.txt)通过 |
| 聊天、资源、专项 | [17项通过](verification/step06-browser.txt)，含21轮连续聊天、首次加载、回执丢失、停止、删除阻断和反馈 |
| 历史与跨标签页 | [5项通过](verification/step07-browser.txt)，含归档、修订、重生成、无关草稿保留与删除回执 |
| 模型设置 | [1项页面旅程通过](verification/model-settings/browser.txt)，密钥不回显、保存/切换/删除及移动端检查通过；[API/Worker受监督退出通过](verification/model-settings-browser.txt) |
| 数据库重启 | [run与唯一调用](verification/step05-restart-facts.txt)、[消息/偏好/标题](verification/step06-restart-facts.txt)、[反馈/修订/删除](verification/step07-restart-facts.txt)直查通过 |
| 文档 | [32份阶段文档检查通过](verification/documents.txt)，原153项验收定义保持不变；不是153项业务验收全部执行 |

浏览器共35项通过，各组均无重试。当前[桌面多轮](verification/multiturn-desktop.png)、[手机多轮](verification/multiturn-mobile.png)、[模型设置手机页](verification/model-settings/model-settings-mobile.png)为本次产物。此前多轮运行中断及跨标签页超时已在当前整轮复验通过；未提高普通run期限、没有删掉相关断言。

中间失败保留在新的`.artifacts/psyevo-step07-*`目录：迁移断言的旧表/head、过宽的发送失败刷新、自动标题CAS竞态、初次身份加载前的空坐标采样及混合行尾均已处理。CAS仍拒绝冲突，页面用例显式核验草稿保留后再次保存；不将这些早期失败收据标为通过。

## 保留边界

真实供应商多轮效果、专业支持质量、临床有效性与公共安全分块未在本次重新验证。WSL内核隔离和真实SMTP未重跑，不借用历史收据宣称本次也已执行。未审练习仍test-only，现实支持列表仍诚实标记未知。本次没有增加业务deadline或放宽安全/权限断言。
