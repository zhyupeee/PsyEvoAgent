# 阶段1 · STEP06 学习文档：聊天、练习与偏好怎样落到页面

> 对应项目步骤：**S1-STEP06「对话、练习及偏好页面」**。本文面向第一次接触 React 页面、HTTP API、React Query 与 SSE 的读者。依据当前仓库的 STEP06 源码、[本步技术实现说明](../PsyEvoAgent项目计划/阶段1/02-技术方案与实施计划.md#s1-step06-implementation)和[验收记录](../PsyEvoAgent项目计划/阶段1/evidence/S1-STEP06/README.md)编写。文中的账号、输入和回应均为合成示例。

## 0. 先明确：这一步做成了什么

STEP05 已经实现了持久 run、独立 Worker、SSE 事件与断线续接。STEP06 把这些后端能力接到可操作的页面，并补上两个不依赖模型的入口：

1. 用户可以建立对话、发送消息、停止活动 run，并在刷新或断流后重新读取当前轮次。
2. 用户可以进入独立的文字练习；练习步骤只保存在当前页面状态里，退出或刷新后重新开始。
3. 用户可以查看支持资源的当前状态，并修改交流方式和显示偏好。
4. 后端增加当前轮次与静态资源读模型；对话、身份、来源权限和偏好接口沿用既有合同。

本步是**隔离合成页面交付**。测试使用隔离 PostgreSQL、真实 API/网关和 fake Worker。真实模型 Provider、专业内容审阅与 SMTP 仍未配置；`synthetic-attention/1` 练习明确未经专业审阅，只在隔离 `test` 环境提供步骤。历史搜索、修订、删除和反馈属于 STEP07，尚未实现。页面已实现不等于完整业务验收或已发布。

## 1. 不懂代码时，先记住这张图

把一次聊天想成“前台收下表单、后台处理、前台再核对处理结果”：

```text
浏览器 /chat
  │ 创建对话，再依次创建 run 草稿、来源 grant、启动请求
  ▼
FastAPI ───────────────► PostgreSQL：对话、run、消息、来源与事件
  │                                      │
  │ 返回已接受的 run                     │ 独立 Worker 执行 STEP05 Support
  ▼                                      ▼
浏览器订阅 SSE ◄──── 事件只通知“有变化” ──┘
  │
  └── 重新读取有权限的 current-run 快照，显示持久化结果
```

最重要的一点是：**SSE 是更新提示，current-run 快照是页面展示的权威数据。** 浏览器不会拿事件里的候选文本直接拼成回答。刷新、断线或收到事件后，页面都重新查询 API；API 会重新检查用户、会话、来源和删除状态。

练习走另一条短路径：页面读取静态步骤，在 React 局部状态里前进或跳过，不创建 run、不调用模型、不保存练习历史。

### 1.1 几个容易混淆的名字

| 名称 | 在这一步的意思 | 可以怎么理解 |
|---|---|---|
| `Conversation` / `session_id` | 一段对话的容器 | 文件夹，可包含多次 run |
| `IdentitySession` | 登录后的一次身份会话 | 证明当前浏览器是谁 |
| `current-run` | 会话最新一轮的受权快照 | 打开对话时恢复屏幕内容的查询接口 |
| React Query `Query` | 浏览器内的异步读取状态与缓存 | “正在读、读到了、读取失败” |
| SSE `RunEvent` | Worker 持久化的事件流 | 通知页面重新读取，不直接作为最终回答 |
| 练习 `step` | 当前组件里的数字状态 | 页面流程位置，不是数据库记录 |

### 1.2 本步的主要代码位置

| 文件 | 负责什么 |
|---|---|
| [frontend/src/routes/chat.tsx](../frontend/src/routes/chat.tsx) 与聊天子路由 | 壳、空白对话页和指定会话页 |
| [frontend/src/support-shell.tsx](../frontend/src/support-shell.tsx) | 登录确认、按身份隔离 Query 缓存、主导航与显示偏好 |
| [frontend/src/chat-page.tsx](../frontend/src/chat-page.tsx) | 创建会话、发送、订阅 SSE、状态恢复和取消 |
| [frontend/src/support-api.ts](../frontend/src/support-api.ts) | API 返回值的 Zod schema 与查询定义 |
| [backend/app/pages.py](../backend/app/pages.py) | 当前轮次、练习和现实支持的读取接口 |
| [frontend/src/resources-page.tsx](../frontend/src/resources-page.tsx) | 练习入口、资源空态和练习步骤 |
| [frontend/src/preferences.tsx](../frontend/src/preferences.tsx) | 交流方式与显示偏好的读取、编辑和保存 |
| [frontend/tests/support.spec.ts](../frontend/tests/support.spec.ts) | 四项 STEP06 实际页面验收 |

## 2. 完整例子：用户发送一句话后发生什么

下面用“合成演示输入，只想倾听”说明网页和 API 怎样协作。真实编号都由浏览器或服务器生成；示例编号不能复用于真实请求。

### 第一步：进入 `/chat` 并创建对话

未指定 `sessionId` 时，[ChatPage](../frontend/src/chat-page.tsx)显示开始页。用户点击“开始一次对话”后，浏览器向 `POST /api/v1/sessions` 创建 `Conversation`，成功后导航到 `/chat/{session_id}`。

按钮在身份仍未读取完成时禁用。创建失败会显示错误，不能把“点击过”当成“会话已建好”。创建请求也带幂等键；页面保存同一次尝试的键，避免网络重试意外多建会话。

### 第二步：页面读取当前轮次

会话页并行读取会话信息和 `GET /api/v1/sessions/{session_id}/current-run`。第一次进入时，接口可返回 `null`，表示还没有 run。已有 run 时，页面读取状态、输入和通过来源检查后允许展示的最终回答。

这一步刷新后仍然成立：路由中的 `session_id` 指定会话，当前轮次从服务端读取。页面不依赖浏览器 `localStorage` 重建对话正文。

### 第三步：依次创建草稿、来源 grant、启动 run

发送前，页面会 trim 输入，并检查它非空、不含 NUL、最长 4000 字符。随后按顺序提交三项操作：

| 操作 | 接口 | 用途 |
|---|---|---|
| 创建 run 草稿 | `POST /api/v1/run-drafts` | 得到稳定的 `run_id`，记录会话及其版本 |
| 绑定当前会话来源 | `POST /api/v1/context-grants` | 说明本轮允许使用哪个会话版本 |
| 启动 run | `POST /api/v1/runs/{run_id}/start` | 持久化用户输入和执行条件，进入排队状态 |

启动请求的大致内容如下：

```json
{
  "expected_version": 1,
  "expected_session_version": 1,
  "input": {"message": "合成演示输入，只想倾听"},
  "client_message_id": "同一次消息的UUID",
  "grant_ids": ["当前会话grant的UUID"]
}
```

写请求还通过同源凭据、CSRF 和 `Idempotency-Key` 受保护。`expected_version` 与 `expected_session_version` 是页面读到的版本号；服务端用它们识别过期页面状态。run 进入 `queued` 代表已排队，Worker 随后才会执行。

前端用一个消息 UUID 标识一次发送尝试，并为 `draft`、`grant`、`start` 三个子请求派生固定幂等键。同一次尝试重试时仍用原键；若 start 请求已在服务器成功、但网页没收到响应，再次提交不会新建第二条消息或第二个 run。代码用 `attempt.current` 暂存文本、消息 UUID 及已创建的 draft/grant 编号；它是当前页面的临时状态，幂等事实由服务端持久记录负责。

### 第四步：订阅事件，再读服务端快照

当 current-run 状态为 `queued` 或 `running` 时，页面建立 `EventSource`，订阅 `/api/v1/runs/{run_id}/events`。收到合法、递增的事件编号后，页面让 React Query 重新查询当前轮次。浏览器定时每 3 秒核对活动 run 的状态，作为事件之外的恢复路径。

事件流出错时，页面关闭 EventSource、提示正在核对状态，并重新查询同一个 current-run。它不会自动再发 start。原生 EventSource 不会把 HTTP `410` 细节暴露给这段页面代码，所以统一按“流断了，重新读授权快照”处理。

### 第五步：展示已持久化的回答

STEP05 Worker 在隔离测试模式下调用 fake Support，完成输出规则检查后把助手回答写入数据库，再把 run 变成终态。STEP06 页面只在 current-run 查询返回获准展示的 `output` 后显示正文。

页面状态标签包括 `尚未发送`、`已接收，等待响应`、`正在响应`、`已完成`、`已停止`、`本次响应失败`和`本次响应中断`。测试中的固定合成回应只证明工程链路，不代表真实模型或心理支持内容已经验收。

### 第六步：用户停止时，以服务端终态为准

点击“停止生成”时，浏览器先 `GET /api/v1/runs/{run_id}` 读取最新版本，再以该版本调用 `POST /api/v1/runs/{run_id}/cancel`。服务端用 STEP05 的 CAS 终态规则处理取消与完成的竞争。若 Worker 先完成，页面就显示“已完成”；若取消先成功，就显示“已停止”。网络失败或版本冲突时显示“停止未确认”，用户可以重新查询。

## 3. 核心实现：按页面到数据的顺序读

### 3.1 路由与应用外壳：页面怎样共享身份和布局

[chat 路由](../frontend/src/routes/chat.tsx)和[resources 路由](../frontend/src/routes/resources.tsx)都挂上 `SupportPage` 外壳；具体页面由子路由提供。当前路由包括：

| 路由 | 用途 |
|---|---|
| `/chat` | 创建对话的入口 |
| `/chat/$sessionId` | 查看和操作指定会话的当前轮次 |
| `/resources?tab=exercise` | 浏览练习资源 |
| `/resources?tab=support` | 浏览现实支持空态 |
| `/resources/exercises/$exerciseId` | 进行独立练习 |
| `/me` | 原账号页中的偏好、密码和退出账号 |

[SupportPage](../frontend/src/support-shell.tsx)先确认 `/auth/session` 身份；未登录会转到登录页，身份读取失败时把内容隐藏并提供重试。登录后，Query 缓存按 `user_id` 建立范围；离开这个身份范围时清除该范围缓存，降低切换账号后误显示旧数据的风险。主导航里“我的记录”显示为尚未开放，不能点击进入。

页面使用现有 TanStack Start/Router、React Query、Form、Zod 和 Tailwind。STEP06 没有另装前端依赖，也没有再建一套路由或全局 Store。

### 3.2 [support-api.ts](../frontend/src/support-api.ts)：用 Zod 描述服务端回应

`sessionSchema`、`runSchema`、`exerciseSchema`和`preferencesSchema`分别说明页面预期收到哪些字段。例如 run 状态限制为 `draft`、`queued`、`running`、`completed`、`cancelled`、`failed`、`interrupted`。接口回应先由集中 `request()` 解析为 JSON，再通过 schema 检查；字段结构不符合预期时，页面按请求失败处理。

`terminal()` 将 `completed`、`cancelled`、`failed`、`interrupted` 识别为终态。聊天页用它决定要不要继续状态轮询与 SSE 订阅。`preferencesQuery` 则把 `/me/preferences` 作为 React Query 的服务端状态读取入口。

### 3.3 [chat-page.tsx](../frontend/src/chat-page.tsx)：页面负责操作，API 负责事实

这个组件把聊天分成四类工作：

1. **建会话**：POST `/sessions` 成功后跳转到带 `sessionId` 的路由。
2. **读状态**：查询 session 与 current-run。run 仍活动时，每 3 秒再核一次终态。
3. **发消息**：校验文本，创建 draft/grant，再 start；成功后让 current-run 重新读取。
4. **接事件/停止**：SSE 事件使快照失效并重新读；取消时先取最新 run 版本。

页面输入框属于当前 React 表单状态。若发送操作没有确认，页面保留输入，并要求重试原消息或查询状态；不允许用户换成另一段文字覆盖尚未确认的尝试。读会话或当前轮次失败时，页面显示“对话暂不可用”，并隐藏消息正文。

下面是幂等尝试逻辑的缩略读法：

```ts
const pending = attempt.current ?? {
  text: parsed,
  id: crypto.randomUUID(),
}
attempt.current = pending
```

`attempt.current` 保存“正在处理的这次消息”。若页面还记着这个尝试，就复用其 ID；只有新尝试才生成新 ID。它和服务端幂等键配合，解决“服务器已经处理、浏览器没收到回执”的情况。

聊天正文不会写进 URL、浏览器持久存储或普通日志。未提交的输入只在表单内存里；刷新会丢掉尚未提交的文字。若 start 已被服务端接受，刷新可从 current-run 恢复已持久化的当前轮次。Query 缓存也只在应用内存中，并按身份范围清理。

### 3.4 [backend/app/pages.py](../backend/app/pages.py)：页面读模型在哪里补充

后端本步只增加页面需要的读取接口，没有增加表或迁移：

| 接口 | 实际行为 |
|---|---|
| `GET /api/v1/sessions/{session_id}/current-run` | 先确认会话属于当前用户且未删除；选出该会话最新 run；用 STEP05 `snapshot()` 重查来源授权，再附上未删除的用户输入。没有 run 时返回 `null`。 |
| `GET /api/v1/resources/exercises/attention` | 返回标题、版本、审阅状态和可用步骤；只有 `environment == "test"` 时返回合成步骤，其他环境标记不可用并返回空 steps。 |
| `GET /api/v1/resources/support` | 返回空 `items`、空 `checked_at` 和“暂无已核实信息”的说明。 |

`current-run` 是一个页面读模型：它把页面需要的输入、状态和允许展示的输出组合成一次读取。它只返回**当前最新一轮**，没有把接口扩展为历史消息列表、搜索或分支。会话所有者不匹配、会话删除或已授权来源失效时，服务端拒绝读取；过去有权限不会让旧快照永久可见。

### 3.5 [resources-page.tsx](../frontend/src/resources-page.tsx)：练习状态留在页面里

资源页用 URL 查询参数 `tab` 在“练习”和“现实支持”之间切换。只在打开现实支持 tab 时读取 `/resources/support`。没有核实条目时，页面明确展示空状态；它不会编造学校、电话、官方链接或核查日期，也不会自动联系他人。

练习页的 `step` 从 `-1` 开始：

```text
step = -1       说明页，还没开始
step = 0..N-1   正在显示某一步
step >= N       完成页
```

“下一步”和“跳过”都会把 step 加一；每次变化后焦点移动到新标题。退出链接卸载练习组件，刷新则重新挂载并回到说明页。练习没有计时器、动画、音频、模型调用、历史写入或完成次数统计。

路由的 `from` 参数只用于从练习返回对应会话；没有 `from` 时回资源页。它不保存练习进度，也不授权读取会话，返回会话时仍由聊天页和 API 执行身份/来源检查。

### 3.6 [preferences.tsx](../frontend/src/preferences.tsx)：偏好保存成功后才更新缓存

偏好页面沿用 STEP03 已有的 `GET/PATCH /api/v1/me/preferences` 和 `user_preferences` 数据。页面提供：

| 字段 | 选项 | 页面用途 |
|---|---|---|
| `mode` | `listen` / `explore` | 下一次发送时采用“先倾听”或“一起想办法” |
| `font_size` | `normal` / `large` | 改变页面字号 |
| `reduced_motion` | 布尔值 | 表示减少动画偏好 |
| `hide_titles` | 布尔值 | 隐藏当前对话标题的显示 |

PATCH 请求带 `expected_version`，并携带原 `age_band`。页面没有新增年龄问题或年龄确认门槛。保存成功后才 `setQueryData()` 更新缓存；失败时显示“未保存”，不会把未写入数据库的设置装作成功。需要时用户可以重新读取，解决版本冲突或网络失败。

交流方式会从下一次发送生效，run 启动时的执行偏好仍按服务端既有规则固定下来。隐藏标题只影响当前显示，不更改数据库标题或访问权限。

### 3.7 键盘、焦点和窄屏布局

[SupportPage](../frontend/src/support-shell.tsx)提供“跳到主要内容”链接；聊天状态与错误分别使用 `role="status"`、`role="alert"`。练习前进时焦点转到新步骤标题，减少键盘和读屏用户寻找位置的成本。

STEP06 的浏览器检查覆盖 390px 视口、键盘 Tab 顺序、可见焦点、大字号、标题隐藏和页面横向溢出。截图包含[聊天桌面](../PsyEvoAgent项目计划/阶段1/evidence/S1-STEP06/windows/chat-desktop.png)、[聊天手机视口](../PsyEvoAgent项目计划/阶段1/evidence/S1-STEP06/windows/chat-mobile.png)、[练习桌面](../PsyEvoAgent项目计划/阶段1/evidence/S1-STEP06/windows/exercise-desktop.png)与[资源手机视口](../PsyEvoAgent项目计划/阶段1/evidence/S1-STEP06/windows/resources-mobile.png)。视口模拟不能当作实体手机软键盘测试；本步也没有计时器或动画，所以退出后不会留下这类后台资源。

## 4. 接口与数据归属速查

| 用户动作 | 前端请求 | 数据事实归属 |
|---|---|---|
| 打开已存在会话 | GET `/sessions/{id}`、GET `/sessions/{id}/current-run` | Conversation/Run/Message 与 STEP05 授权规则 |
| 发送一条消息 | POST `/run-drafts`、POST `/context-grants`、POST `/runs/{id}/start` | Run、RunExecution、Message、幂等记录等既有数据 |
| 等待回答 | GET `/runs/{id}/events`，再 GET current-run | PostgreSQL 中的 RunEvent 与受权 snapshot |
| 停止运行 | GET `/runs/{id}`，POST `/runs/{id}/cancel` | 服务端 CAS 决定唯一终态 |
| 修改偏好 | GET/PATCH `/me/preferences` | STEP03 已有 `user_preferences` 行与版本 |
| 浏览练习/现实支持 | GET `/resources/exercises/attention`、GET `/resources/support` | STEP06 静态读模型；练习进度不入库 |

本步没有新增 schema、迁移、依赖、Agent 图或 Worker 消费者。[`main.py`](../backend/app/main.py)把 `pages.router` 与原 API、runs、SSE router 一起挂载；读取接口复用原身份依赖。页面新增不意味着多了一份业务事实来源。

## 5. 测试和验收文件在验证什么

### [frontend/tests/support.spec.ts](../frontend/tests/support.spec.ts)

四个真实页面用例分别验证：

1. 聊天真实发送、start 回执丢失后同 key 重试、刷新恢复、换账号不能读旧内容。
2. 停止与 Worker 完成竞争时，页面最终状态和 API 一致；SSE 断流后恢复且 start 只发生一次。
3. 偏好保存失败不报成功；成功后刷新保留；手机视口能用键盘发送并显示偏好。
4. Provider 不可用时练习仍独立运行；跳过、退出、刷新和完成均按预期；空资源如实显示；没有模型/run 请求或 `localStorage` 内容。

浏览器用例使用合成账号和隔离服务。它们验证网页与测试 API 的连接，不验证真实模型输出质量或已审练习内容。

### [backend/tests/test_pages.py](../backend/tests/test_pages.py)

三项 PostgreSQL 测试覆盖当前轮次读取和撤销来源后隐藏、会话删除/跨账号拒绝、模型关闭时练习仍可用且 development 不泄露未审步骤。它们也核对练习请求前后 `ModelCall` 列表没有变化。

### [scripts/check_step06.py](../scripts/check_step06.py)

这是本步隔离验收入口，复用 [`check_step03.py`](../scripts/check_step03.py) 的独立 PostgreSQL、迁移、API、fake Worker 和同源网关准备，然后先回归 STEP05，再跑 STEP06 页面用例。验收不使用开发库。

## 6. 本步证据怎样读

[STEP06 证据索引](../PsyEvoAgent项目计划/阶段1/evidence/S1-STEP06/README.md)记录最终通过状态与限制。Windows 收据显示：53 项 PostgreSQL/API/迁移测试通过（50 项前置回归、3 项本步读取接口测试），后端工程检查 65 项通过；前端 `check`、`build` 通过；STEP06 四项页面测试通过。数据库重启后还直接核对偏好持久化，以及丢回执重试只产生一条用户消息、一个 run、一次模型调用和一次主动事件。

WSL 另通过内核隔离工程检查，拒绝外连与 Windows 互操作；本步专用 PostgreSQL/API 和 STEP06 页面验收由 Windows 收据覆盖。证据区保留失败轮次和修复记录，最终状态以 `windows/receipt.json` 及索引中的最终记录为准。

这些数字是本步**工程执行证据**。153 项业务验收仍是计划，四项页面用例不等于整个阶段业务验收通过；真实 Provider、专业内容审阅、SMTP 和发布也没有被这一步验证。

## 7. 用几个失败场景检查自己是否理解

### 场景 A：服务器已经启动 run，网页却报发送未确认

服务器可能已经提交了消息，但响应在网络中丢失。页面保留 `attempt.current`，用同一个消息 UUID 派生的 start 幂等键重试。数据库确认相同用户、相同键、相同请求后返回原资源，不重复创建 run。刷新后则查询 current-run 恢复已经持久化的当前轮次。

### 场景 B：SSE 连接断开

页面关闭该 EventSource 并重新读取同一个 current-run。断线只表示浏览器暂时收不到事件，不会自动再次发送消息。活动 run 的三秒轮询也会继续核对服务端状态。

### 场景 C：取消和 Worker 完成几乎同时发生

前端先取最新 run 版本，API 再按 STEP05 的 CAS 规则竞争终态。以数据库最终状态为准，页面不能仅凭按钮点击就写“已停止”。

### 场景 D：换账号后打开旧会话 URL

前端登录身份与 Query 缓存按 owner 隔离；后端的 `owned()` / `snapshot()` 仍会再次检查所有权、删除与来源。无权读取时页面隐藏正文并显示不可用状态。

### 场景 E：偏好保存返回 503 或版本冲突

mutation 进入错误状态，页面显示未保存，不更新成功缓存版本。用户重新读取服务端值后再编辑和提交。

### 场景 F：普通开发环境打开未经审阅的练习

资源接口返回 `available: false` 与空 `steps`，页面显示待审阅。`test` 环境里的合成步骤不能被当成正常开发或真实用户内容。

## 8. 建议的学习顺序与自测

建议按数据流读源码：

1. 先看 [路由目录](../frontend/src/routes/chat.tsx) 与 [support-shell.tsx](../frontend/src/support-shell.tsx)，找页面是怎样确认身份和共享导航的。
2. 看 [chat-page.tsx](../frontend/src/chat-page.tsx)，依次找创建会话、当前轮次查询、start 请求、SSE 监听和 cancel 请求。
3. 看 [support-api.ts](../frontend/src/support-api.ts)，把页面所依赖的 run 状态字段和终态找出来。
4. 看 [backend/app/pages.py](../backend/app/pages.py)，确认 current-run 如何选最新 run、怎样复用 `snapshot()` 核权。
5. 看 [resources-page.tsx](../frontend/src/resources-page.tsx) 和 [preferences.tsx](../frontend/src/preferences.tsx)，比较页面局部状态与服务端持久状态。
6. 最后看 [support.spec.ts](../frontend/tests/support.spec.ts) 和[本步验收记录](../PsyEvoAgent项目计划/阶段1/evidence/S1-STEP06/README.md)，用实际用例核对理解。

可以用下面的问题自测：

1. 为什么 SSE 收到 `message.delta` 后仍要重新读取 current-run？
2. 一个消息 UUID 怎样帮助 draft、grant、start 三个请求安全重试？刷新后恢复又依赖什么？
3. 为什么 cancel 请求前先读取最新 run 版本？取消按钮成功点击能否单独证明 run 已取消？
4. `current-run` 为什么不等同历史列表？撤销 grant 后为什么之前的回答可能不再显示？
5. 练习的 `step` 和交流偏好的 `mode` 分别存在哪里？刷新后表现为何不同？
6. 为什么 `environment == "test"` 返回练习步骤，不代表内容已审或可以用于真实用户？
7. 偏好 PATCH 失败时，页面如何避免显示未保存的值已经写入？

如果能用“**页面发起幂等操作 → PostgreSQL/Worker 保存真实运行事实 → SSE 提醒重新读取授权快照；练习只用局部状态；偏好通过版本化 API 保存**”概括 STEP06，就抓住了本步的主干。
