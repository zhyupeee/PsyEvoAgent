# STEP08续作：真实模型与整稿网页联调

2026-09-28已按用户确认的工程范围完成STEP08，见[最终收尾](engineering-closeout.md)。下文为2026-09-27时点记录，原未满足项和收据保持历史事实。

日期2026-09-27。基线仍为`f783572`加上一轮STEP08未提交改动；用户明确本机已填写API key并要求继续STEP08。本轮保留已有改动和历史收据，未读取/打印密钥正文，没有进入阶段2。

## 顺序与当前边界

按STEP08.1先执行真实内部流PoC，再接原API/独立Worker/单LangGraph/事务事件链。首个真实PoC流已返回，但输出usage超过1024上限，判失败；兼容请求补充`max_tokens`后第二个PoC通过。保留两次独立收据，预算校验未删除，未知费用未记零。

接入范围限定隔离合成数据库：live开关显式、凭据仅注入API/Worker，前端不持有密钥；start冻结模型/base URL、输出上限、deadline与一次调用预算。实际字节/token统计不可冒充真实tokenizer。原图meta→support→output_policy保持不变，内部流经整稿检查后才写入原message、delta和completed事务。取消、失去来源权限和删除仍走原generation/CAS锁。

外部删除状态通过持久调用账本判定；即使API重启为disabled，也不会将历史live清理改称不适用。在线清理与供应商保留/删除分别展示，后者unknown。本轮无新数据库schema、Agent循环或Worker。

## 未满足项

| 项目 | 当前结论 |
|---|---|
| 密钥与真实模型连通 | 已解除原密钥阻塞；内部流PoC通过，不等于全部能力通过 |
| 网页整稿真实旅程 | 已实现并通过实际页面、SSE/快照/DOM、取消/删除及数据库重启验收 |
| 安全分块 | BLOCKED：没有经验证的分块准入/上下文策略，按02/03保留Full Buffer Review；不把有限关键词判定当放行证据 |
| 供应商地区/保留/价格及远端取消/删除 | unknown；仅合成资料调用，未知费用null；本地关闭流不冒充远端停止计费 |
| 专业支持/练习/高风险内容审阅 | BLOCKED：没有独立审阅材料，不能伪造S1-A01/A03/A07及RSI语义验收通过 |
| 真实SMTP | BLOCKED：邮箱身份回归继续使用隔离邮件替身 |
| STEP08.2～.4及阶段2交接冻结 | 尚未完成；.1未关闭前不勾选或冻结，当前只整理证据与未满足项，不跳步 |

## 验证记录

真实结果、受控故障、fake回归分列。最终命令为显式加载本机配置后执行`backend/.venv/Scripts/python.exe -X utf8 scripts/check_step08.py --live --web-port 3108 --api-port 8108 --tls-port 3448`。本地目录`.artifacts/psyevo-step07-bc69289a9d2b/`沿用旧目录前缀，机器收据step_id为S1-STEP08；35个命令全部退出0，随机合成容器最终清理成功。Python3.12.13、Node22.19.0、pnpm10.28.0及既有固定PostgreSQL16.13镜像。未访问开发库，未发布远程服务。

| 最终验收 | 实际结果 |
|---|---|
| 完整入口 | [最终收据](continuation/windows/receipt.json)passed；这是整稿live工程域通过，不是整个STEP08关闭 |
| DB/API/迁移 | [70项通过](continuation/windows/postgres-tests.xml)，含新增2项真实库+受控SDK流的完成/取消/删除回执持久化 |
| 后端与前端 | [83项后端](continuation/windows/foundation.txt)、Ruff/格式/mypy/锁、[前端check](continuation/windows/frontend-check.txt)与[build](continuation/windows/frontend-build.txt)通过 |
| 前置真实页面 | 9项身份/工程、1项HTTPS、1项SSE网关、5项STEP06及4项STEP07通过 |
| 真实模型页面 | [1项完整旅程通过](continuation/windows/step08-live-browser.txt)：发送、真实SSE、刷新、跨owner拒绝、取消、确认删除；[页面元数据](continuation/windows/live-browser.json)记录一条整稿delta、SSE=快照=DOM、刷新后调用数仍1 |
| 重启事实 | [直查日志](continuation/windows/step08-restart-facts.txt)、[持久账本与删除回执](continuation/windows/live-facts.json)：成功轮settled/3378总token，取消轮cancelled/actual=null，各只有一次调用；正文清空、公共事件删除，外部Provider状态unknown持久保留 |
| 源码 | [144个工程文件](continuation/windows/source-verification.json)与最终收据逐项hash一致；之后仅文档/证据归档 |

实际查看[真实合成回答页面](continuation/windows/live-chat.png)和[删除回执页面](continuation/windows/live-deletion.png)，布局与新增外部状态说明可读。截图只有合成输入/账号，不冒充专业内容审阅或实体手机验证。前置资源练习仍是test-only合成域。

| 证据域 | 观察与证据 |
|---|---|
| 真实PoC首轮 | [失败收据](continuation/poc-output-limit-failure/receipt.json)：88块，首块4297ms，调用10766ms；usage_over_reservation，未返回正文，实际总token3846，费用unknown；不能记成功 |
| 真实PoC兼容修复后 | [通过收据](continuation/poc-passed/receipt.json)：90块，首块2171ms，调用6500ms；真实JSON text/schema、终局usage及整稿规则通过，总token3492；一次调用、无SDK重试，费用null |
| 网页首轮 | [失败收据](continuation/browser-cookie-failure/receipt.json)及[日志](continuation/browser-cookie-failure/step08-live-browser.txt)：真实发送和SSE/页面一致性通过，后续Node APIRequest不携带Secure Cookie导致快照断言失败；改用页面同源fetch，不跳过快照断言 |
| WSL内核隔离 | [封装收据](continuation/wsl/receipt.json)、[工程收据](continuation/wsl/engineering.json)：83项后端、5项工程页面通过；额外[41项Support](continuation/wsl/runtime-tests.txt)通过，IPv4/IPv6 TCP/UDP、原生curl及WSL互操作出口受阻。保留原STEP04/02收据ID，不冒充live运行在禁外连域 |
| 源码核对 | [WSL业务源码对照](continuation/wsl/source-verification.json)：配置、适配、图、API、Worker、删除及回执页面与Windows一致，忽略行尾；后续仅调整live验收脚本/文档 |

其他失败：首两次完整门禁因新测试输出文字超长触发Ruff失败，随后缩短文字；Worker旧生命周期测试的替身未接收新增settings参数，更新替身签名后原关闭顺序断言通过。首次完整回归期间新增持久化用例，最终另轮完整执行，不把早期源码hash当最终验证。所有失败均在`.artifacts/psyevo-step07-*`各自目录保留，不改写历史成功收据。

## 能力矩阵边界

| 能力 | 真实观察 | 受控验证/未满足 |
|---|---|---|
| text/内部stream/JSON text schema | 实测通过 | 不等于Provider原生JSON schema约束支持 |
| usage与token限制 | 第二轮usage通过；首轮输出超限失败 | 只记实测样本，不保证供应商始终服从；max_tokens与max_completion_tokens共同发送，服务端继续复核 |
| 取消 | 实际网页停止→持久cancelled→重启账本cancelled/unknown用量，零回答 | 本地流关闭另有受控SDK/DB验证；远端停止/计费unknown |
| 401/429/500/超时/截断/断流/缺usage/schema错误 | 不故意制造真实限流 | 17项实际SDK传输替身按独立测试验证，不能记真实Provider tested |
| tool、refusal、structured+tool组合 | 真实能力unknown | tool禁止执行；受控流拒绝tool/refusal且不公开，未开放工具来测试 |
| 语义安全/高风险/独立内容审阅 | unknown/BLOCKED | 仅有限固定规则，不替代专业人工rubric |
| 安全公共分块 | 未开放/BLOCKED | 整稿通过后单条delta；不把Provider内部多块或前端动画记公共安全流 |

本轮模型调用仅固定合成输入；截图只保留合成测试页面。普通日志及账本不记录提示词/回答正文或密钥，不归档本地环境文件、SMTP邮件目录或TLS私钥。实际调用可能计费，金额未知，没有虚构零费用。
