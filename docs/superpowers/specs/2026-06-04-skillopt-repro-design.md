# SkillOpt 忠实复刻 — Phase 1 设计 (Spec)

- **日期**：2026-06-04
- **状态**：待用户评审
- **作者**：协作产出（user + Claude）
- **范围**：仅 Phase 1 —— 忠实复刻 vanilla SkillOpt，benchmark = SearchQA，后端模型 = GPT-5.5（optimizer = target）

---

## 0. 背景与定位

整体是一个研究计划：基于微软 [microsoft/SkillOpt](https://github.com/microsoft/SkillOpt)（MIT，2026-05 开源）做扩展，给它贪心的"文本空间优化"加上 **exploration**（后续 Phase 计划引入 PBT / Novelty Search / Entropy Bonus / RND），目标是刷 benchmark。

**本 spec 只覆盖第一步：忠实复刻原项目，得到一个可信、可复现的 vanilla 基线。** 后续阶段（接缝重构、QD 主干、消融、规模化）各自再走独立的 spec → plan → 实现循环，**本阶段一律不涉及**。

SkillOpt 一句话原理：把一份自然语言"技能文档"当作可训练参数，对冻结的 LLM agent 反复做 `rollout → reflect（生成 add/delete/replace 编辑）→ aggregate → select（验证门）→ update（文本学习率预算）→ evaluate`，产出可部署、零额外推理开销的 `best_skill.md`。

---

## 1. 目标 & 非目标

### 目标
1. Fork 官方 `microsoft/SkillOpt` 并在本地可运行。
2. 完成 SearchQA 的**数据物化**（官方只发布 ID 清单，需从 HuggingFace 还原全字段）。
3. 用 **GPT-5.5**（optimizer=target）在 SearchQA 上跑通完整训练循环。
4. 验证结果与官方 `ckpt` / 论文 SearchQA 数字一致 → 锁定 vanilla 基线。
5. 产出可复现的运行脚手架 + 验收报告模板。

### 非目标（明确排除）
- 任何 exploration 扩展（entropy / PBT / novelty / RND）。
- 任何"接缝"重构 / 架构泛化。
- SearchQA 以外的 benchmark。
- 由本工具直接执行付费训练（见 §2 假设②）。

> **纪律：Phase 1 不写一行优化/扩展代码。** 只为"把原项目跑对、跑通、可复现"服务。允许写的非原仓库代码仅限：数据物化脚本、运行/验收的薄封装脚本、报告模板。

---

## 2. 关键约束与假设

| 编号 | 假设 | 说明 |
|---|---|---|
| ① | **后端先不定 → 参数化、不写死** | 同时备好 OpenAI 直连与 Azure OpenAI 两条路；`.env` 模板 key 留空；运行命令通过 `--optimizer_model/--target_model` 与环境变量切换。 |
| ② | **执行归属：Claude 只搭建，用户自跑** | 一次完整 SearchQA 训练是付费、约几十分钟级的跑批（~10⁴ 量级 GPT-5.5 调用）。Claude 交付可运行的脚手架 + 脚本 + 报告模板；**实际训练由用户用自己的 key 执行**。`baseline_report.md` 为待填模板。 |
| ③ | **算力实验室级** | 预算充足；但 Phase 1 仍先以**单 seed 打通**为目标，多 seed 仅在结论需要时补。 |
| ④ | **忠实优先** | 超参、配置、随机种子一律沿用官方默认（`configs/searchqa/default.yaml`），不调参。 |
| ⑤ | **GPT-5.5 可用** | 用户具备 gpt-5.5 访问权限（Azure 部署或 OpenAI），由用户在执行时提供。 |
| ⑥ | **写权限已解决** | `E:\skillopt` 原 ACL 仅给 Users 只读；已通过管理员 `icacls` 授予当前账户 Modify。 |

---

## 3. 验收标准（可测量）

记 **A\*** = 官方 `ckpt/searchqa/gpt5.5_skill.md` 在 SearchQA test(1400) 上 `eval_only` 的稳定参考分。

1. **Sanity 通过**：能跑出 A\*，且与论文报告的 SearchQA 数字相符（差距 < ε）。这一步同时验证"后端 + 数据物化 + 评测链路"全部正确。
2. **训练复现**：从 `initial.md` 完整训练得到的 `best_skill.md`，test 分数满足
   - `score(best_skill) ≥ A* − ε`，且
   - `score(best_skill) ≥ 论文报告 SearchQA 数字 − ε`。
3. **正向提升**：`score(best_skill) > score(initial.md)`（`initial.md` = 环境种子技能 `skillopt/envs/searchqa/skills/initial.md`，代表初始/弱技能基线），方向与论文一致。
4. **可复现**：固定 `seed=42`；保存配置快照、`history.json`、commit hash、后端与模型名；同配置重跑波动落在 ε 内。

- **ε 取值**：建议 **2–3 个百分点**（覆盖 LLM 解码随机性与评测噪声），最终值在执行前据 sanity 波动确定。
- **论文 SearchQA 数字**：执行验收时从论文 PDF（arXiv 2605.23904）结果表提取并记入报告（本地已存 PDF 副本，见 §13）。

---

## 4. 仓库与目录布局

工作根目录：`E:\skillopt`。

```
E:\skillopt\
├── SkillOpt\                      # 官方仓库 fork（克隆于此，保留 upstream 远程）
│   ├── skillopt\ scripts\ configs\ data\ ckpt\ ...   # 原仓库内容
│   └── data\searchqa_split\       # ← 物化产物写入这里（config 期望路径）
├── tools\
│   └── materialize_searchqa.py    # 我们写的数据物化脚本
├── docs\superpowers\specs\
│   └── 2026-06-04-skillopt-repro-design.md   # 本 spec
├── baseline_report.md             # 验收报告（模板，用户跑完后填）
└── .env.example / .env            # 后端凭据模板（key 留空）
```

**决策**：把官方仓库克隆到子目录 `E:\skillopt\SkillOpt\`，我们自己的脚手架（spec/tools/report）放在工作根。理由：后续 Phase 要在 fork 内改代码，子目录隔离让"我们的工作区文件"与"上游代码"边界清晰，也避免与官方已有 `docs/` 冲突。
（实现时若已有根目录文件导致 `git clone` 报"目录非空"，按 plan 用临时目录克隆后归位即可。）

---

## 5. 环境与安装

- Python ≥ 3.10（官方 `pyproject.toml` 要求）。建议独立虚拟环境（venv/conda）。
- 核心安装：`cd SkillOpt && pip install -e .`（依赖：openai / pyyaml / numpy / openpyxl / azure-identity / azure-core / httpx）。
- **无需 torch / GPU**：SearchQA + GPT-5.5 为纯 API 路径。
- 物化额外依赖：`pip install datasets huggingface_hub`（不在官方依赖内）。
- 校验：`python -c "import skillopt; print('SkillOpt ready!')"`。

---

## 6. 后端配置（参数化，不写死）

默认 `backend=azure_openai`、`optimizer_backend=target_backend=openai_chat`、`optimizer=target=gpt-5.5`、`reasoning_effort=medium`（来自官方 base config）。两条路，`.env.example` 同时给出、key 留空：

- **OpenAI 直连**
  ```ini
  AZURE_OPENAI_AUTH_MODE=openai_compatible
  AZURE_OPENAI_ENDPOINT=https://api.openai.com/v1
  AZURE_OPENAI_API_KEY=          # 用户填
  ```
- **Azure OpenAI**
  ```ini
  AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
  AZURE_OPENAI_API_VERSION=2024-12-01-preview
  AZURE_OPENAI_API_KEY=          # 用户填；或用 AZURE_OPENAI_AUTH_MODE=azure_cli
  ```

模型名通过 `--optimizer_model gpt-5.5 --target_model gpt-5.5` 或环境变量 `OPTIMIZER_MODEL/TARGET_MODEL` 传入（`run_searchqa.sh` 已支持）。**spec 不固定某一条路**；用户执行前二选一即可。

---

## 7. 数据物化（关键步骤）

### 背景
`SkillOpt/data/searchqa_id_split/{train,val,test}/items.json` **只含 ID**（如 `{"id": "221c83e6..."}`）。`data/README.md` 明确这些是 manifest、非完整 payload。SearchQA 的 `dataloader.py` 仅从本地读 JSON 数组、不会自动拉取。而 `configs/searchqa/default.yaml` 期望 `split_dir: data/searchqa_split`（注意：**不是** `searchqa_id_split`）。因此必须物化。

### 脚本契约：`tools/materialize_searchqa.py`
- **输入**：
  - ID 清单：`SkillOpt/data/searchqa_id_split/{train,val,test}/items.json`
  - 源数据集：HuggingFace `lucadiliello/searchqa`（关联键 `key`）
- **关联**：`items.json[].id == dataset.key`
- **输出**：`SkillOpt/data/searchqa_split/{train,val,test}/`，每个 split 一个 JSON 数组文件，每条含至少：
  ```json
  { "id": "...", "question": "...", "context": "...", "answers": ["..."] }
  ```
  （字段名以 `skillopt/envs/searchqa/{rollout,evaluator}.py` 实际消费为准，实现时核对。）
- **校验**：
  - 各 split 命中数 == manifest counts：**train=400 / val=200 / test=1400**；
  - 无缺失/重复 ID；缺失则报错并列出，不静默丢弃。
- **幂等**：可重复运行；已存在则覆盖或跳过（带 `--force`）。

---

## 8. 复刻运行协议

> 命令以 `E:\skillopt\SkillOpt\` 为工作目录。Windows 下 `run_searchqa.sh` 需 Git Bash/WSL；或直接用 PowerShell 调 `python scripts/train.py`。

**Step 0 — 物化数据**
```bash
python ../tools/materialize_searchqa.py    # 生成 data/searchqa_split/
```

**Step 1 — Sanity（先打通后端+数据+评测）**
```bash
python scripts/eval_only.py \
  --config configs/searchqa/default.yaml \
  --skill ckpt/searchqa/gpt5.5_skill.md
# 记录 test 分 = A*
```

**Step 2 — 训练（官方默认超参，不调参）**
```bash
bash scripts/run_searchqa.sh
# 等价于：
# python scripts/train.py --config configs/searchqa/default.yaml \
#   --optimizer_model gpt-5.5 --target_model gpt-5.5 --out_root outputs/<run>
```
官方默认超参（来自 config，**忠实沿用**）：
`num_epochs=4, train_size=400, batch_size=40, seed=42`；
`gradient.minibatch_size=8, merge_batch_size=8, analyst_workers=16, max_analyst_rounds=3`；
`optimizer.learning_rate(edit_budget)=4, min_lr=2, lr_scheduler=cosine, skill_update_mode=patch, use_slow_update=true (samples=20), use_meta_skill=true`；
`evaluation.use_gate=true`；`env: max_turns=1, max_completion_tokens=16384, workers=24`。

**Step 3 — 评估训练产物**
```bash
python scripts/eval_only.py \
  --config configs/searchqa/default.yaml \
  --skill outputs/<run>/best_skill.md
```

**Step 4 — 对比与记录**：train 产物分 vs A\* vs 论文数字，写入 `baseline_report.md`。

---

## 9. 基线产物与报告模板

保留完整 `outputs/<run>/`（`steps/`、`best_skill.md`、`history.json`、`config.yaml`）。

`baseline_report.md` 字段（模板，用户跑完填写）：
- 环境：Python 版本、commit hash（fork + upstream）、后端（OpenAI/Azure）、模型名、日期。
- 指标：A\*（ckpt 复评分）、`score(initial.md)`、`score(best_skill.md)`、论文报告 SearchQA 数字、ε。
- 过程：每步/每 epoch 的 val gate 接受情况摘要（取自 `history.json`）、技能文档 token 数变化。
- 成本：总模型调用数、token 用量、墙钟时间、估算费用。
- 结论：是否满足 §3 验收标准（逐条勾选）。

---

## 10. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| **LLM 非确定性** | 分数波动 | 固定 `seed=42`；验收用容差 ε；关键结论补 1–2 seed |
| **gpt-5.5 访问/配额** | 跑不动 | 先用 `eval_only` 小验证打通后端，再开训练 |
| **成本** | 预算/时间 | 单次训练 ~10⁴ 量级调用，主要被每步 val(200) gating 吃掉；**确切量需读 `engine/trainer.py` 确认 gate 频率/规模**；先单 seed |
| **HF 数据可用性** | 物化失败 | 脚本做缺失校验并报明细；必要时换镜像/缓存 |
| **字段不匹配** | rollout/eval 出错 | 物化前核对 `envs/searchqa/{rollout,evaluator}.py` 实际消费字段 |
| **Windows / bash 脚本** | 脚本跑不了 | 用 Git Bash/WSL，或直接 PowerShell 调 `python scripts/train.py ...` |
| **clone 进非空目录** | git 报错 | 子目录克隆（§4）；或临时目录克隆后归位 |

---

## 11. 明确排除项（Out of Scope）

- entropy bonus / PBT / novelty search / RND 等任何扩展与其设计。
- trainer/scoring/selection 的接缝化或种群化重构。
- DocVQA / OfficeQA / LiveMath / SpreadsheetBench / ALFWorld。
- 由 Claude 直接执行付费训练。
- 多模型 × 多 benchmark 的规模化刷表。

---

## 12. 交付物清单（Phase 1 完成时）

1. `E:\skillopt\SkillOpt\`：可运行的官方 fork（保留 upstream 远程）。
2. `tools/materialize_searchqa.py`：数据物化脚本（含校验）。
3. `data/searchqa_split/`：物化后的 SearchQA 全字段数据（或脚本可一键生成）。
4. `.env.example`（两后端，key 留空）+ 安装/运行说明。
5. `baseline_report.md`：验收报告模板。
6. 本 spec（评审通过版）。

> 注：3–6 中"训练实跑结果"由用户执行后回填；Claude 交付到"一键可跑 + 模板齐备"。

---

## 13. 开放问题 / 执行时确认

- 论文 SearchQA 精确数字：执行验收时从 arXiv 2605.23904 结果表提取（本地 PDF 副本已存于会话 tool-results 目录）。
- gate 评测的频率与规模（每步是否全量 val=200、`sel_env_num=0` 的确切语义）：实现/执行前读 `skillopt/engine/trainer.py` + `skillopt/evaluation/gate.py` 确认，用于精确成本估算。
- `data/searchqa_split` 各 split 的文件命名（单文件 `items.json` vs 其他）：以 `skillopt/datasets/base.py::SplitDataLoader` 实际 glob 规则为准。
- 后端最终二选一（OpenAI 直连 / Azure）：用户执行前确定。
