# S1-STEP04 单Support、Provider与预算

日期：2026-09-24；基线`30b332f`；开始时工作区干净。仅推进STEP04及必要前置修复，无STEP05/06接口或页面、无数据库业务迁移、无Worker消费者、无远程发布、无真实模型/邮件调用。

## 前置核对

STEP03的邮箱身份、默认配置、来源核权、迁移、前端路由及测试确已落地。旧STEP03.5独立收据和2026-09-24开发记录证明曾执行18项数据库、20项工程、9项浏览器及1项HTTPS检查，但当时总门禁因两张旧隐私页面截图缺失失败。步骤页还留有“邮箱未实现”的过期文字和未勾项。

本次将旧截图引用改为明确的缺失说明，未恢复或伪造历史图片，旧收据不改写。同步STEP03当前身份口径；本轮`prerequisite/receipt.json`独立复验完整门禁通过：18项真实PostgreSQL测试、20项工程测试、前端check/build、9项浏览器及1项HTTPS、数据库重启事实核对、文档与diff检查通过。收据中的source hash是结束时工作树，期间已开始编写尚未被此前命令加载的STEP04模块；不声称这是不可变STEP03快照或STEP04测试。

两次前置失败独立保留：`prerequisite-format-failure/`的Prettier检查发现manifest/CSS本地行尾格式不一致；仅对这两文件执行已有Prettier，语义未变。`prerequisite-db-start-failure/`发现PostgreSQL初始化临时socket误报ready，检查器改为TCP探测后通过。只清理门禁自身创建的随机合成容器，不访问开发库。

## 当前实现

`backend/app/support.py`提供唯一`START → meta → support → output_policy → END`图。Meta固定规则决定支持方式、拒绝优先和空工具集合。版本绑定、预算、模型能力与可信输入用Pydantic校验；外部调用前/重试前/输出前复核来源。当前来源快照由内部可信调用方注入，HTTP身份到持久run原子绑定属于STEP05，未声称已经接通。

LangGraph 1.2.12、langchain-core 1.6.4精确锁定。langsmith 0.14.0作为SDK传递依赖同时显式声明，以调用其关闭追踪的API；不启动观测服务。新增锁约束使websockets 17.1降为16.1.1，其余原直接业务依赖保持。没有安装真实供应商SDK。

统一边界执行每次调用预占、2次调用上限、token/费用上限与原deadline；瞬态错误有限重试，schema修复配额0；429不越deadline，半截输出不重试。usage未知保留预占，actual为null。metadata-only账本不留正文和异常原文，模型不热换。fake价格/币种单独标注，不是假称真实供应商成本。

所有候选整稿缓冲，模型外schema验证、固定行为规则及来源复核均通过才返回。13条既有场景正反例覆盖拒绝/结束/欺凌/未知资源及后半段排他、义务、诊断、危险内容。有限规则不能证明任意中文语义安全；semantic_score始终null；无已审回退时明确Controlled Stop，不假称已理解或已保存。

## 验收与故障修复

协议和验收映射以[03局部协议](../../03-测试与验收标准.md#s1-step04-validation)为准，执行入口见[DEVELOPMENT](../../../../DEVELOPMENT.md)。最终[Windows门禁](windows/receipt.json)与[WSL内核隔离门禁](wsl/receipt.json)全部通过。各目录包含engineering.json、完整日志、tests.xml、runtime.json及源码hash。

| 检查 | 最终实测 |
|---|---|
| uv锁、Ruff lint/format、mypy | Windows/WSL通过 |
| 后端工程与本步运行回归 | 两环境各61项通过（含本步41项），18项数据库另由前置独立门禁验证 |
| STEP04专门JUnit | 两环境各41项通过；覆盖正常/失败/预算/取消/来源/追踪 |
| 实际graph场景与fake账本导出 | 各29条结果：13场景×正反例＋3条故障账本，全部符合预期 |
| 前端类型/lint/unit/build/工程浏览器 | 两环境通过；unit 2项，浏览器5项；Windows前置另含pnpm check/Prettier |
| WSL内核出口隔离 | IPv4/IPv6 TCP/UDP、curl、Windows互操作拒绝；工程及本步测试均在隔离内 |
| 非隔离负例 | [收据](wsl-negative/receipt.json)预期失败，接口不只lo时前置探针拒绝，未执行后续测试 |
| 文档/fixture/补丁 | 门禁通过；收尾后再次执行文档和diff检查 |

版本为Python 3.12.13、Node 22.19.0、pnpm 10.28.0，库版本以runtime.json和uv.lock为准。最终源码hash已与两个收据核对：WSL执行副本仅隔离shell脚本CRLF转LF，其余STEP04清单逐字节相同；脚本按LF规范化后相同。源码在最终门禁后未修改，后续仅证据和文档收尾。Windows语言保护不冒充内核隔离，WSL不包含PostgreSQL业务验收。

初始测试夹具中`AIMessage | Exception`的Pydantic联合校验在异常对象上触发LangChain校验器错误；将异常类型优先校验后复验通过，未放宽产品断言。Windows第一次完整工程门禁发现旧reload监督器在stdin关闭时无法正常退出，失败保留于`windows-reload-failure/`。最初async sleep轮询虽通过进程测试但被Ruff ASYNC110拒绝，Windows/WSL失败保留于`windows-poll-lint-failure/`、`wsl-poll-lint-failure/`。最终使用事件循环定时器检查multiprocessing.Event，退出时取消定时器，去掉阻塞executor等待；进程回归4项及最终完整门禁通过。未改停止超时、失败状态或退出断言。

## 外部阻塞与交接边界

| 项目 | 状态 | 影响 |
|---|---|---|
| 真实Provider/model、价格、地区/保留条件、usage/取消能力 | BLOCKED / unknown | 无真实调用；fake能力不能填入live矩阵 |
| 支持文案专业审阅、独立人工rubric | BLOCKED / pending verification | 合成规则测试不是心理质量/真实安全验收，不开放真实支持产品 |
| 真实SMTP | BLOCKED，沿STEP03保留 | 已有邮箱密码登录可用，真实注册/找回邮件外发未验证；不阻塞本步fake图 |
| 两张历史隐私页截图 | 缺失、不可核验 | 当前链接检查已修正表述；旧历史图证不能宣称补齐 |
| 持久run/start/SSE/CAS、完整聊天UI | planned，STEP05/06 | 本轮不实施，不把函数取消当作业务run取消 |

本步数据库无schema变更；fake账本作为验收产物归档，不创建第二份业务事实库。153项业务整项不因局部工程通过而全部完成。

最终状态：**COMPLETED（仅S1-STEP04四项fake域工程交付）**。真实域按上表BLOCKED，不标tested/pass；当前最早尚未实施的步骤为S1-STEP05，本轮停止于STEP04。
