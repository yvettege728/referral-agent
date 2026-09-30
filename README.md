# Referral Agent: evidence-backed recommendations and recovery

Referral Agent 帮助 buyer 根据可检查的证据选择 seller，并在推荐失败后记录原因、排除失败者和重试。底层 Service Record Protocol 提供 Notary、Auditor、历史记录和 reputation scoring。`--mock` 保留确定性对照组；hybrid live mode 让四个 Referral panel 角色、Lead Referral 和诚实 seller 调用真实模型，同时保留确定性的检查、评分与停止规则。seller-c 是受控 adversarial seller，使 fabrication 与 recovery 可以重现。

GitHub repository: <https://github.com/yvettege728/referral-agent>

从本目录执行一条命令：

```bash
./eval.sh --mock
```

真实模型的第一个建议场景是 task 03 的 CRM 联系人表清洗：

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_MODEL="gpt-5"
./run.sh 03 referral-contact-live-0928 --mediated --live
```

`--live` 只负责在终端输出进度；是否调用真实模型由 `--mock` 决定。因此 `--mock --live` 仍是 mock，`--mediated --live` 且不加 `--mock` 才是实时模型实验。没有 `OPENAI_API_KEY` 时程序会在创建 run 之前停止，不会静默退回 mock。

免费本地 Ollama 模式不需要 API key：

```bash
ollama pull qwen3:8b
SR_MODEL_PROVIDER=ollama OLLAMA_MODEL=qwen3:8b \
SR_RECORDS_DIR=/tmp/referral-contact-ollama-0928-records \
./run.sh 03 referral-contact-ollama-0928 --mediated --live
```

Ollama 必须正在本机 `localhost:11434` 运行。可用 `OLLAMA_URL` 改变 endpoint，默认为 `http://localhost:11434/api/chat`。Ollama 请求使用 JSON Schema、temperature 0 和禁用 thinking，便于对比角色差异。

运行只需 Python 3.10+ 标准库。输出为 [runs/eval-summary.md](runs/eval-summary.md)，包括 baseline 与 improved 各 8 个任务的坏交付、重试、人工升级与 agent 调用数。每组从空记录开始；清空前的记录、重复评测的同名输出会移动到 `runs/_archives/<UTC批次>/`。运行结束保留 improved 的当前记录，两组独立副本保存到 `runs/baseline-entries.jsonl` 和 `runs/improved-entries.jsonl`。不要同时运行 eval 与其他任务。

单个任务与测试：

```bash
./run.sh 01 demo-01 --mock
./run.sh 04 demo-hard --baseline --mock
python3 -m venv .venv
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest -q
```

同一 label 不允许复用，以免覆盖交付和审计证据。任务 ID 为 `01`–`04`；单次 run 默认复用既有记录。可通过 `PYTHON` 指定解释器，默认优先使用本地 `.venv/bin/python`。

| 文件 | 用途 |
|---|---|
| `SPEC-HW2.md` | 唯一 HW2 范围依据；原文保留 |
| `config.json` | 初始分、评分参数、门槛、重试、超时、stake 默认值 |
| `notary.py` | 唯一追加写入者；验证字段、承诺时间与 stake，生成 ID、UTC 时间、SHA-256 |
| `engine.py` | `compute(entries, config)` 纯函数；`lookup <domain>` 输出信誉，不保存评分真值 |
| `audit.py` | 回合前后 custody、原有字节前缀和记录哈希检查；交付缺失或为空时通过 notary 写 flag |
| `run.sh` / `orchestrate.py` | 单任务入口与流程实现、错误处理、恢复、日志 |
| `eval.sh` / `evaluate.py` | 固定任务顺序、两组独立评测、归档、汇总 |
| `protocol.py` | mock/真实接口共用的严格 fenced JSON 解析器 |
| `tasks/01/` | 素因数分解；JSON 输出 |
| `tasks/02/` | 常规食谱重量换算；CSV 输出 |
| `tasks/03/` | 联系人表清理与去重；CSV 输出 |
| `tasks/04/` | 混合质量/体积、密度与杯量定义的难题；CSV 输出 |
| `agents/mock_buyer.py`, `agents/mock_seller.py` | 确定性选择、承诺与交付行为 |
| `agents/self_descriptions.md` | 三段可靠口吻的自我介绍，seller-c 排第一 |
| `agents/call_agent.sh` | hybrid 路由：Referral 与诚实 seller 进入 OpenAI adapter，seller-c 进入受控 adversarial mock |
| `agents/openai_responses.py` | 使用标准库调用 Responses API 并要求 strict JSON Schema 输出；请求设置 `store: false` |
| `agents/live_referral.py`, `agents/roles/` | 四个独立 panel opinions、Lead 综合、dissent 和 model usage trace |
| `agents/live_seller.py` | 模型生成交付内容，adapter 只允许写指定 delivery path |
| `agents/prompts/` | 已有真实提示词，未修改 |
| `records/entries.jsonl` | 当前追加记录，只由 notary 写入 |
| `runs/<label>/` | 按序输入、完整 prompt、回复、stderr、custody 快照、check、notary、audit 与 metrics |
| `tests/` | 评分、notary、审计篡改、检查器、解析器与完整 mock 流程测试 |
| `reference/` | 旧项目参考，未修改 |

## 流程与可追溯证据

正常一次尝试包含四个外层回合：Referral 选人 → seller 承诺 → seller 交付 → Referral 报告结果。live Referral 选人回合内部包含四次独立 panel 调用和一次 Lead 调用。承诺回合只允许输出 commit；notary 完成 commit 和 stake 后才启动交付回合。每个外层回合前后审计全部 records 文件，notary 的合法追加发生在回合之外。

live mode 向 API 发送当前角色需要的 brief、候选人证据或 seller 工作目录中的任务输入。API key 只在 Authorization header 中使用，不写入 prompt、trace 或 run 文件。每次模型调用的 response ID、model 和 token usage 写入 `*.model.json` 或 `team-debate-attempt-N.json`；汇总写入 `metrics.json`。

先读 `timeline.md`，再按序号查看 `*.input.json`、`*.prompt.md`、`*.output.txt` 和 `*.stderr.txt`。`attempt-N/check.txt` 是机器判分依据，`notary.txt` 记录写入请求与结果，`audit.txt` 最后一行给出审计结论。每个 seller 尝试有独立 `task_run_id`，避免重试串用承诺或 stake。

缺文件和空文件均记 fabrication，随后换 seller。存在但答案错误的文件只有 fail，没有 fabrication。缺 block、JSON 错误、缺字段、无效 confidence、重复 block 或无效路径均作为回合失败写入 timeline，不猜测结果；最多重试两次。买方报告必须与检查器一致。高风险任务、所有剩余候选者 character < 40 或重试耗尽都会记 `choice.action=ask_human`。Baseline 的门槛由 wrapper 执行，给买方的输入仍只有自我介绍。

包含 seller-c 的运行即使成功恢复，也以 `AUDIT FAIL: ... fabrication flag notarised ...` 结尾，保留实际违规；其他无违规运行以 `AUDIT PASS` 结尾。审计失败却没有成功写入 flag 时直接终止，不伪装成已完成的造假处理。

## 评分与明确选择

- 初始 character 为 **40**、无记录的 professional 为 **50**。这两个 Default 保存在 config，初始 40 避免冷启动全部低于人工门槛。
- `step = 16.404119792206316`，`k = 2.954701971999018`，`drop_factor = 1/3`。从 40 出发，10 条干净记录到 90，首次造假降到 30；20 条干净记录回到 70，第二次造假降到约 7.78，落在目标 10 ± 5 内。
- 干净记录指有承诺、有效 stake 且无 fabrication 的已判分事务，包括诚实失误。诚实失败会获得正常的小幅品格增长，不会降低品格。每个事务最多记一次 offence；迟到的 flag 在重新计算时取消该事务的干净信用。
- Professional 按 domain 计算 `100 × (1 − Σ stake × (confidence − result)² / Σ stake)`，pass=1、fail=0。无有效承诺或 stake proof 的事务不影响信誉。
- 本包 stake 是注明来源的本地计算投入占位，**没有真实资金托管或独立核验的经济风险**。这是 mock 演示的限制，不把固定字符串当作真实付款证明。
- 标准任务输入保存在各任务目录；`task.json` 指定 domain、交付文件名和 high_stake。brief 的 `{delivery_path}` 在运行时替换成 seller 独立工作目录下的绝对路径。

## 评测解释与范围

固定顺序在 `eval.sh`：01、02、04、03、01、04、02、03。两组第 6 题强制 seller-b、第 7 题强制 seller-c，覆盖诚实失误和重复造假；其余初次选择按各自政策，重试排除已尝试 seller。初始完全同分按配置顺序 c、b、a，improved 会先遇到一次 liar；这是公开的确定性 tie-break。`SR_FORCE_SELLER` 只用于首轮干预，并明确写入 choice 原因和 metrics。

坏交付次数按失败的 seller 尝试计（检查失败、fabrication 或 seller 协议失败），率的分母是 seller 尝试总数；重试不包括首次尝试。每次正常尝试有 4 个 agent 调用，notary、lookup、checker、auditor 不计入。此评测说明确定性 mock 下的机制行为，不能据此推断真实模型的可靠性或第 4 题出错概率。

`NOTARY_CALLER=auditor` 是所要求的本地调用约定，SHA-256 和外部快照用于发现更改；它们不是签名、用户权限隔离或对恶意本地进程的安全保证。live seller 不获得通用文件工具：模型只返回内容，adapter 检查路径后仅写入分配的文件。这是路径限制，不是完整的操作系统沙箱。

手动验证已有记录前缀可使用运行时保存的快照：

```bash
python3 audit.py verify runs/<label>/initial.custody.json
```

测试已在临时目录覆盖修改中间行、重算该行哈希后仍被旧快照识别、增删 records 文件等情形。`SR_RECORDS_DIR` 支持将 notary/engine/audit 指向测试记录目录。快照必须保存在 records 之外。
