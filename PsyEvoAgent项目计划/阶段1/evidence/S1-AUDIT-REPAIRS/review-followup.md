# 输出规则审查跟进

日期：2026-09-29。范围为三条P2审查意见；保留原暂存修改和历史门禁收据。

- 短号码：识别“拨999999”“打999”等普通拨号指令，覆盖冒号、空白归一化、全角数字与不可见分隔符；普通年份、日期、金额和“打300字”仍允许。
- 诊断限定语：检查匹配内部的“是否／是不是／有没有／会不会”及紧随诊断的疑问语气；另一个分句中的疑问不能豁免确定诊断。
- 冻结版本：Support按运行绑定的`evaluator_version`分派。v1保留原规则和空白归一化，v2采用当前规则；不重写`RunExecution.versions`及调用回执。相同年份文本在v1被拦截、v2通过。

新增回归先在修复前复现15项失败，再验证修复。数据库用例从API创建排队run，经Worker和Support执行，断言终态、SSE、助手消息及持久版本回执；v1拦截时没有公开正文。

| 检查 | 本次结果 |
|---|---|
| 后端常规 | [188项通过](review-followup/backend-tests.txt)，数据库用例按默认标记排除 |
| 隔离PostgreSQL/API | [55项通过](review-followup/postgres-tests.txt)：`test_runs.py`、`test_multiturn.py`、`test_stage1_repairs.py`、`test_model_settings_api.py`；3项非数据库用例排除 |
| 静态检查 | [Ruff](review-followup/lint.txt)、[格式](review-followup/format.txt)、[mypy](review-followup/types.txt)通过 |
| 数据库清理 | [临时容器已移除](review-followup/database-cleanup.txt)；未访问开发库 |

[机器收据](review-followup/receipt.json)记录命令、退出码和三个修改代码文件的SHA-256。原始产物目录为`.artifacts/psyevo-support-review-02facf0085f6/`，独立合成库应用现有迁移至head。测试模型为本地fake或受控传输替身。

本次未修改前端，未重跑浏览器、完整Windows/WSL门禁、真实Provider或SMTP。有限输出规则不等于专业语义安全或临床有效性验证。
