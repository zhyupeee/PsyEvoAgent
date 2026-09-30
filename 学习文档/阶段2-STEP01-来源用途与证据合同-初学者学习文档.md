# 阶段2 · STEP01 学习文档：来源、用途与证据合同怎样立起来

> 对应项目步骤：**S2-STEP01「来源与用途合同」**。本文面向第一次接触来源授权、版本引用和证据标注的读者，依据[阶段2技术合同](../PsyEvoAgent项目计划/阶段2/02-技术方案与实施计划.md#s2-step01-contract)、[本步验收切片](../PsyEvoAgent项目计划/阶段2/03-测试与验收标准.md#s2-step01-checks)、[执行记录](../PsyEvoAgent项目计划/阶段2/evidence/S2-STEP01/README.md)和实际检查器编写。文中的人物、记录与引用均为合成例子。合同定稿于 2026-09-29；STEP02 已于次日实现其中的记录部分，读到旧矩阵里的“未实现”时请以[STEP02 当前实现合同](../PsyEvoAgent项目计划/阶段2/02-技术方案与实施计划.md#s2-step02-implementation)为准。

## 0. 先明确：这一步做成了什么

阶段1已有账号、会话、消息、`Run`、`ContextGrant`、来源检查和删除流程。阶段2计划再处理笔记、睡眠记录、支持备忘卡，以及后续的记忆与画像。如果只给每条材料写一个 ID，系统仍无法判断“谁的、哪一版、准许用于哪件事、现在是否还有效”。STEP01 先把这些问题写成可核对的合同。

本步交付四件事：**所有权与来源版本矩阵、配置与用途映射、11 维证据标注规范、字段和来源的可追溯映射**。另有合成材料和离线检查器验证合同是否自洽。2026-09-29 的本步完成状态只表示**合同与合成材料范围完成**；当时没有新增记录表、页面、长期记忆、画像服务或模型 Assessor。STEP02 后来实现了三类记录及 `current_run` 带入，但 STEP01 的检查结果本身仍不是这些运行能力的证据。

## 1. 不懂代码时，先看一条来源怎样被判断

```text
一条合成消息：owner-a / message / source-a / version 1
  ↓
一个用途限定的引用：owner-a / source-a / version 1 / current_run
  ↓
消费方提出请求：谁在读？哪个 run？为哪种用途？配置是哪一版？
  ↓
逐项核对 owner、type、ID、版本、grant、用途、状态和范围
  ├─ 全部匹配 → 这一用途、这一范围内才可读取
  └─ 任一项失效 → 拒绝；相似文字和旧检查结果都不能补授权
```

这里的“来源”是能追到原始对象的**结构化引用**，例如消息 ID 和版本；“用途”是这次消费被允许做什么。两者都要在真正读取时重新核对。不能从“我现在可以把消息带进一次对话”推断出“后台也可以把它保存为长期记忆”。

### 1.1 六个容易混淆的名字

| 名称 | 含义 | 容易误解的地方 |
|---|---|---|
| `owner_id` | 来源、grant 和消费者共同核对的账号归属 | 请求自填 owner 不会取得别人的资料 |
| `source_type/id/version` | 对象种类、具体 ID 和当前版本 | 同 ID 不同种类、同 ID 旧版本都不能互换 |
| `ContextGrant` | 把来源绑定到特定 run 和 `purpose` 的授权记录 | 一条 grant 不是所有用途的通行证 |
| `experiment-defaults/1` | 实验配置的默认策略版本 | 默认开关为 true 不等于相应功能已落地 |
| `DependencyEvidence` | 带来源的单条支持、反证或含糊材料 | 不是诊断，也不是某一维的最终分数 |
| `DependencyProfile` | 计划中的 11 维、观察窗口和证据充分性结构 | 冷启动或缺资料时必须保留 unknown |

阶段1的 `ContextGrant` 在 STEP01 时只支持真实会话来源和 `current_run`；STEP01 的合成材料可以写计划中的其他 source/purpose，但那不会让线上 API 自动接受它。STEP02 后的实际扩展仍只开放 `current_run`，长期记忆和画像用途留给各自步骤。

### 1.2 本步主要文件

| 文件 | 读它的目的 |
|---|---|
| [阶段2技术合同](../PsyEvoAgent项目计划/阶段2/02-技术方案与实施计划.md#s2-step01-contract) | 看四份产出的权威定义、状态边界与后续责任 |
| [scenarios.json](../PsyEvoAgent项目计划/阶段2/fixtures/S2-STEP01/scenarios.json) | 看独立的合成来源、用途判断和 11 维预期材料 |
| [_check_s2_step01.py](../_check_s2_step01.py) | 看材料结构、引用关系和损坏反例怎样检查 |
| [backend/app/models.py](../backend/app/models.py) 与 [api.py](../backend/app/api.py) | 对照本步写合同时已经存在的 owner、版本和 grant |
| [阶段2验收切片](../PsyEvoAgent项目计划/阶段2/03-测试与验收标准.md#s2-step01-checks) | 分清本步局部通过与后续真实消费者的验收 |

## 2. 完整例子：同一条消息怎样用于不同目的

假设合成用户甲留下消息“最近总在睡前打开对话”。材料写明它属于 `owner-a`，类型 `message`，ID 为 `source-a`，版本为 1，尚未删除。这是**来源事实**；至于它表明什么，仍需要其他证据和解释。

### 第一步：绑定真正的来源

一条引用不能只写“那句关于睡前的消息”。它至少要准确指向 `source_type=message`、`source_id=source-a`、`source_version=1`，并与 owner 对齐。若用户后来修订消息，旧版引用不能偷偷转向新版；若来源被删除，也不能凭摘抄的文字继续使用。消息的角色也重要：助手说出的句子不能冒充用户自述或已确认偏好。

### 第二步：确定这次消费的用途

STEP01 把用途分开登记：

| `purpose` | 计划中的消费者 | 本步完成时的实际状态 |
|---|---|---|
| `current_run` | 本次支持对话选定的来源 | 阶段1已有会话来源；记录来源在 STEP02 扩展 |
| `candidate_extraction` | 从合格来源提出记忆候选 | 留待 STEP04；不能继承对话 grant |
| `personalization` | 读取正式记忆辅助某次对话 | 留待 STEP05；提取权限不等于检索权限 |
| `dependency_assessment` | 生成带证据的可选画像 | 留待 STEP06；不能借用记忆权限 |
| `evaluation` | 隔离的内部评测快照 | 留待后续评测阶段；不是私人正文外发许可 |

配置默认开启只是策略输入，还要有**实际消费者、合格来源、精确用途、有效 grant 和当前版本**。历史决定保留原值；不能为了让新实验跑通而把旧 `declined` 或 `revoked` 改成 `granted`。关掉画像用途不自动关掉记忆或支持对话；反过来也一样。

### 第三步：按顺序作一次判断

合同规定先看账号及对象可见性，再看来源当前状态/版本，再看 grant 的 purpose 和版本，然后看对应配置及消费者范围，最后才读取或提交。合成材料中的 `memory-is-not-profile`、`old-source-version`、`deleted-source`、`revoked-grant` 等反例就是为了发现“跳过了其中一步”的错误。

例如甲可以在某个 run 中使用自己的消息，并不代表乙的相似消息也可读；同一条甲的消息也不能拿 `current_run` grant 去执行 `dependency_assessment`。这些例子检查的是合同判断，不是数据库中实际产生过这些 grant。

## 3. 11 维标注：从原话到证据，不跳成结论

STEP01 定义 `s2-annotation/1`，给未来的 Assessor 和画像存储提供字段与预期样例。11 个维度 ID 是 `language_expectation`、`frequency_change`、`duration_schedule`、`regulation_concentration`、`reassurance_loop`、`unavailability_response`、`decision_autonomy`、`use_control`、`exclusivity_replacement`、`functional_impact`、`protective_factors`。它们分别关注期待、频率、时长安排、调节与专注、反复求保证、不可用反应、自主决定、使用控制、排他替代、实际功能影响和保护因素；**没有第 12 维或总分**。

读一条材料时，先分清说话人、发生时间和引用范围，再标它支持什么、反驳什么，或仍然含糊。`DependencyEvidence` 需要 `stance`、`evidence_kind`、非空 `source_refs` 和 `alternative_explanations`；不清楚发生时间时保留 `null` 与原因。不能用记录创建时间冒充经历发生时间，也不能因“夜间使用”或“次数很多”单独判为需要行动。

未来的 `DependencyProfile` 要为全部 11 维写状态。刚开始没资料时填 `unknown`，不能填 0 或“低风险”；正反证冲突时保留两边来源、标明 `conflicting`，不能求平均。长期高频但没有实际影响，与当前明确的严重影响，也不能套用同一条简化规则。改善或解除需要新证据或自愿报告；没有再来使用产品不等于改善。

同样，计划中的记忆 `claim_type` 要区分 `user_statement`、`user_feeling`、`system_inference` 和 `confirmed_preference`。自动保存推断之后它仍是推断；“已确认偏好”必须有实际用户确认或更正事件及版本。这里冻结的是字段语义，**没有运行记忆提取、保存或画像分类**。

## 4. 合成材料和检查器究竟验证了什么

[scenarios.json](../PsyEvoAgent项目计划/阶段2/fixtures/S2-STEP01/scenarios.json)明确标记为 synthetic，包含来源、grant、用途关联、各维支持/反证/未知例子，以及冷启动、缺失、冲突、高频无影响和长期严重影响五类预期场景。不同样例中的复用 ID 是教学用引用封套，不构成一个真实人的连续时间线。

[_check_s2_step01.py](../_check_s2_step01.py)读取指定 JSON 和合同材料，在内存中比较结构与预期，并故意构造损坏样例，确认检查器会拒绝缺字段、错版本或假通过标签。它只用 Python 标准库，不连接数据库、不调用模型，也不读取真实私人记录。可以在仓库根目录运行：

```powershell
backend/.venv/Scripts/python.exe -X utf8 _check_s2_step01.py
```

`--receipt` 会在本步证据目录新增带时间戳的收据；日常学习只需不带该参数检查，避免把一次新运行混入历史交付证据。[本步执行记录](../PsyEvoAgent项目计划/阶段2/evidence/S2-STEP01/README.md)记载了当时 **28 条来源/用途关联、11 维 33 条例子、5 组场景、15 个损坏反例**；另有 **53 项隔离 PostgreSQL 阶段1前置复验**。前者不是线上授权或 Assessor，后者验证的是继承来的阶段1路径。没有因此证明长期记忆、画像、中文阈值或专业标注一致性。

## 5. 为什么还要做字段与来源映射

合同既要指出“已有代码在哪里”，也要指出“计划字段由哪一步负责”。[矩阵](../PsyEvoAgent项目计划/阶段2/02-技术方案与实施计划.md#s2-step01-contract)把 `Message`、`Run`、`ContextGrant` 等既有实体与尚未落地的笔记、记忆、画像并排写清，避免把计划里的字段误认成已运行 API。

它还把记录字段、记忆候选和 11 维标注的参考来源分开登记：有的只是历史静态材料或研究概念边界，并不代表本步导入了外部代码、量表题项或私人数据。`expires_at` 是保留的历史字段，可为空，不是新设的业务自动删除期限；技术 deadline、租约和资料保留也不是一回事。

尤其要记住 STEP01 给 STEP02 留下的迁移要求：扩展原有 `context_grants`，继续约束账号和实际目标，不要把外键拿掉后只剩一个任意 `source_id`。后来 STEP02 的 [l012_records 迁移](../backend/migrations/versions/l012_records.py)才把这条要求落到数据库。

## 6. 用几个失败场景检查自己是否理解

### 场景 A：同一句话出现在两个账号里

文字一样也不能互借。先看认证 owner 与来源 owner、grant owner、消费方 owner 是否一致；任何一个不一致都拒绝。

### 场景 B：消息改成第 2 版，引用还指向第 1 版

要按版本重新核对。旧 grant 或摘记不能无声转向新版，更不能让模型根据相似文本自行认定它们等价。

### 场景 C：`memory=true`，但没有提取消费者

默认配置不能凭空建立运行能力。STEP01 的合成判断可以描述它的准入规则，真实提取仍须等 STEP04 的存储、校验和执行路径。

### 场景 D：材料里只有助手说“你依赖我”

这不是用户自述，也不是确认偏好。最多按来源角色作为上下文，不能直接升级为用户事实或画像结论。

### 场景 E：五天没有打开产品

缺少观察资料应保留 unknown；不能自动推断“依赖已解除”。若正反证并存，应记录冲突和替代解释。

## 7. 建议的学习顺序与自测

1. 从[所有权与用途矩阵](../PsyEvoAgent项目计划/阶段2/02-技术方案与实施计划.md#s2-step01-contract)找出 `owner`、版本、grant、purpose 各由谁核。
2. 打开[合成材料](../PsyEvoAgent项目计划/阶段2/fixtures/S2-STEP01/scenarios.json)，分别找一条允许关联、一条错版本反例和一条反证标注。
3. 读[检查器](../_check_s2_step01.py)的 `binding_result()` 与 `validate()`，确认它是在比较合成材料，不是在调用服务端。
4. 用[验收切片](../PsyEvoAgent项目计划/阶段2/03-测试与验收标准.md#s2-step01-checks)和[执行记录](../PsyEvoAgent项目计划/阶段2/evidence/S2-STEP01/README.md)核对“本步通过”的确切范围。
5. 再读[STEP02 学习文档](阶段2-STEP02-笔记睡眠与备忘卡-初学者学习文档.md)，看记录来源如何真正进入数据库和一次对话。

自测时试着回答：为什么 `current_run` grant 不能做记忆提取？为什么 `unknown` 不能用零代替？为什么记录版本和 grant 版本都要检查？为什么合成材料的预期标签不等于模型观察结果？能用“**准确来源 → 独立用途 → 当前核验 → 有证据才作有限解释**”讲清这些问题，就掌握了 STEP01 的主干。
