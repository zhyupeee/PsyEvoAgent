# S1-STEP08 全阶段联调及交接：进入检查

2026-09-28最新状态：**内部实验工程验收完成**，当前依据、矩阵及交接见[最终收尾](engineering-closeout.md)。本文及continuation保留之前BLOCKED时点，不改写历史收据。

用户补齐本机密钥后的最新状态见[STEP08续作记录](continuation.md)；本文保留首次内部流PoC代码切片时点。

日期：2026-09-27。执行者：本轮 Codex。基线：`f783572`；开始时 Git 工作区干净。当前最早未完成步骤为 **S1-STEP08**。**STEP08.1 内部流PoC代码部分实现；真实验收BLOCKED**，未完成本步，不进入阶段2。

## 前置事实

- STEP07历史交付与评审修复均已合入。最新历史证据见[评审修复记录](../S1-STEP07/review-fixes.md)：68项PostgreSQL/API/迁移、66项后端回归、4项STEP07页面及前置页面通过。历史证据不冒充本轮执行。
- 实际代码存在：`backend/app/history.py`、`deletion.py`、`frontend/src/history-page.tsx`及`backend/migrations/versions/h007_history_feedback.py`；对应API/页面/迁移测试及`scripts/check_step07.py`均存在。
- 开始检查时`app.config.Settings.support_mode`仅允许disabled/fake，`SupportRuntime`拒绝非本地fake适配器，独立Worker只装配fake，无真实适配依赖或PoC。原完整候选通过检查后才由Worker同一事务发布正文、事件及终态。本轮只扩展图内PoC，产品API/Worker开关仍未开放live。
- 本轮只检查相关进程环境变量名称，未发现Provider/模型/SMTP配置；未读取或打印凭据值。API按合同只读进程环境、不自动加载.env，不能由此推断机器其他位置没有凭据。

## 当前步骤与阻塞

依据[执行顺序](../../04-分步实施与检查清单.md#s1-step08)、[真实接入技术合同](../../02-技术方案与实施计划.md#live-model-integration)和[验收补充](../../03-测试与验收标准.md#live-model-acceptance)，先登记实际Provider并验证内部流，再接整稿网页旅程，之后评估安全分块；.1完成后执行.2～.4。

| 项目 | 状态 | 原因与解除条件 |
|---|---|---|
| STEP08.1实际配置 | 部分已登记；密钥BLOCKED | 用户本轮指定`https://ai.hybgzs.com/v1`、`grok-4.7`并要求密钥留空自行填写。凭据引用`PSYEVO_PROVIDER_API_KEY`；兼容协议待实测，价格、地区、保留条件unknown；费用不作为排期阻塞项 |
| STEP08.1适配与内部流PoC | 代码已实现；live未执行 | `app.provider`、`app.provider_probe`复用唯一Support图。实际SDK受控传输覆盖正常流、取消、超时、断流、拒答、tool、schema、usage与错误；无真实凭据不能记Provider tested |
| STEP08.1真实整稿网页旅程 | 未实现、未执行 | 依赖上述PoC；fake网页验收不能替代live |
| STEP08.1安全分块 | 未实现、未验证 | 尚无可靠准入/分块策略与真实适配证据，保持现有整稿路径；未命中关键词不作为放行依据 |
| STEP08.2～.4 | 未执行 | 按顺序等待.1完成；未冻结阶段2交接包 |
| 专业支持/练习内容、SMTP | BLOCKED（既有外部条件） | 审阅与真实SMTP配置尚未提供，分别承接；合成练习及邮件替身不证明真实条件已满足 |

## 本轮实现

新增显式配置读取、LangChain兼容协议内部流适配与固定合成输入PoC命令，配置和启动见[DEVELOPMENT](../../../../DEVELOPMENT.md)。密钥留在忽略的`.env.step08.ps1`空槽中，应用不自动读取该文件。仅PoC接受live适配，网页与Worker仍保持原装配，遵守先真实PoC、后网页旅程的顺序。

唯一图仍为meta→support→output_policy；live只预占一次8192 token信封、默认1024输出token/60秒，无重试。原始流在私有Buffer内，上限32768字节/4096块；停止不flush，不输出内部JSON、工具或未检查正文。费用unknown/null，不套用fake价格；没有已验证真实tokenizer或金额上限。本地取消只证明本地流关闭，远端行为unknown。

锁定LangChain OpenAI 1.6.6、OpenAI SDK 3.19.2及其显式HTTPX2 2.13.1客户端；没有升级既有Core/Graph或卸载业务依赖。实际SDK转换存在两处边界：会丢弃流式refusal、把缺失usage计数补零；适配器在转换边界保留拒答标记并拒绝缺失计数，新增反例验证。缺密钥入口留BLOCKED元数据收据，不泄漏原始异常。

没有新增前端产品行为、数据库迁移、Agent循环、Worker或公共流协议。前置style.css仅规范行尾/格式，使Prettier通过；语义diff为空。未发送真实模型请求/邮件、未发布服务、未操作开发数据库。

## 本轮验证

首轮前置复验在68项PostgreSQL/API/迁移及66项后端通过后，因style.css格式失败，浏览器尚未执行。收据单独保留，不覆盖失败。格式修复后完整门禁通过；随后补齐usage反例，最终代码再完整复验。STEP08真实内部流、网页、安全分块及整阶段验收均未执行，不宣称通过。

根目录实际执行`backend/.venv/Scripts/python.exe -X utf8 scripts/check_step07.py --web-port 3107 --api-port 8107 --tls-port 3447`，最终本地目录`.artifacts/psyevo-step07-85f43d3fb056/`。随机独立合成PostgreSQL容器最终清理成功；未访问开发库。Python3.12.13、Node22.19.0、pnpm10.28.0，数据库镜像沿既有固定digest。

| 最终Windows检查 | 实测与证据 |
|---|---|
| 完整门禁 | [收据](windows/receipt.json)32个命令全部退出0；step_id保留STEP07，明确为前置回归 |
| 数据库/API/迁移 | [68项通过](windows/postgres-tests.xml)，含owner/删除/修订/反馈及迁移保留 |
| 后端 | [83项通过](windows/foundation.txt)，其中17项受控SDK测试；[Ruff](windows/lint.txt)、[格式](windows/format.txt)、[mypy](windows/types.txt)和锁检查通过 |
| 前端 | [check](windows/frontend-check.txt)、[build](windows/frontend-build.txt)通过 |
| 实际页面 | [9项身份/工程](windows/browser.txt)、[1项HTTPS](windows/https-browser.txt)、[1项SSE网关](windows/step05-gateway.txt)、[5项STEP06](windows/step06-browser.txt)、[4项STEP07](windows/step07-browser.txt)通过 |
| 数据库重启 | [STEP07直查](windows/step07-restart-facts.txt)及前置STEP05/06事实核对通过，非仅HTTP200 |
| 源码 | [139个工程文件hash](source-verification.json)与最终收据一致；之后只归档证据和更新说明 |

页面日志对应实际Playwright运行；本轮前端仅格式修复，未新增页面设计，不新增截图验收声明。文档检查仍为32份/153项定义，不代表153项业务用例通过。

- [首次格式失败](preflight-format/receipt.json)：当时未新增适配代码，失败点为Prettier；[日志](preflight-format/frontend-check.txt)。
- [缺凭据负例](missing-credentials/receipt.json)：子进程清除PSYEVO配置后执行`python -m app.provider_probe --live`，实际退出2、reason=provider_not_configured，未发请求。不是live通过收据。
- [WSL封装收据](wsl/receipt.json)、[内核隔离工程收据](wsl/engineering.json)：83项后端（含17项新适配测试）、5项工程页面，以及额外[41项原Support回归](wsl/runtime-tests.txt)通过；IPv4/IPv6 TCP/UDP、原生curl及WSL互操作外连拒绝。仍沿用STEP04/STEP02收据ID，不能改名当作STEP08 live或数据库页面全链隔离。关键后端源码[逐文件核对](wsl/source-verification.json)与宿主一致，仅忽略CRLF/LF。
- WSL准备中先后出现PowerShell传参/CRLF、复制中文路径编码和验证副本缺Git元数据问题；只修正独立副本的复制/入口与`git init`，未放宽测试、未改宿主业务数据。[缺Git元数据的失败收据](wsl-preparation-failure/receipt.json)保留；最终复验通过。
- 首轮新适配测试暴露refusal字段丢失，另有超长自动pytest用例ID触发Windows路径限制；修正适配字段保留并使用短用例ID，不删除断言。后续补齐缺usage计数反例，最终17项通过。

当前解除阻塞动作：用户本机填写`.env.step08.ps1`密钥，执行显式PoC并保留结果；之后补齐真实内部流能力矩阵，再按顺序实现整稿网页旅程。不能仅凭本次PoC代码/SDK替身或后续一次HTTP200标本STEP完成。专业内容审阅、SMTP仍单列未满足。
