# SkillOpt SpreadsheetBench 复刻基线报告 (Phase-1 扩展)

> 指标 hard = Exact Match（cell-value，忠实官方 SpreadsheetBench `evaluation.py` 语义：数值 `round(.,2)`、datetime→Excel serial 等）；本 env 每 task 单 test-case，故 **soft = hard**。
> **本次用 DeepSeek 替代论文的 GPT-5.5（无 GPT-5.5 访问）**，所以这是「DeepSeek vanilla 基线」，**不与论文数字 / 官方 gpt5.5 ckpt 直接可比**。
> 目的：在**第二个 benchmark（SpreadsheetBench）**上端到端复现 vanilla SkillOpt，并作为 Phase-2 QD-over-Skills 的 **K=1 / vanilla 参照基线**。配套见 `baseline_report.md`（SearchQA）。

## 环境
- 日期：2026-06-06
- 远程：AutoDL（`connect.westb.seetacloud.com`），Python **3.12.3**（miniconda base，独立 venv）；**纯 API、无 GPU**
- fork commit（upstream `microsoft/SkillOpt`）：`ee9931e`
- 后端：**DeepSeek**（`https://api.deepseek.com`，`openai_compatible`；需打 `patches/deepseek-backend-adapter.patch`）。实测模型路由 `deepseek-v4-flash`。
- optimizer / target：`deepseek-chat` / `deepseek-chat`（`reasoning_effort` 关闭）
- 执行环境：LLM 生成 Python → `subprocess`（venv python）改 xlsx → `openpyxl` 评分；远程补装 `pandas 3.0.3`（生成代码常用）
- 数据：**SpreadsheetBench Verified 400**（本地物化 HF `KAKA22/SpreadsheetBench` → `train=80 / val=40 / test=280`；远程 HF 不通，故本地物化再传）
- seed：42 ｜ 超参：**官方默认**（`epochs=4, train=80, batch=40, edit_budget=4 cosine, min_edit=2, minibatch=8, slow_update(samples=20)+meta_skill 开, gate=hard, mode=multi, max_turns=30, exec_timeout=600, workers=24`）

## 指标（test = 280）
| 项 | overall hard | cell-level (n=193) | sheet-level (n=87) |
|---|---:|---:|---:|
| `initial.md`（S0，弱基线） | 0.4571 | 0.4041 | 0.5747 |
| **`best_skill.md`（训练产物）** | **0.5286** | **0.5026** | **0.5862** |
| 提升 Δ | **+0.0714** | +0.0985 | +0.0115 |

（selection/val=40：`baseline 0.400 → best 0.625`）

提升几乎全部来自 **cell-level（+9.9pts）**；sheet-level 基本持平（+1.2pts）。

## 过程
- `steps=8，accept=2 / reject=6 / skip=0`；best 在 **step 6（epoch 3）** 达 val=0.625 后进入平台期。
  - epoch1: 1a/1r best=0.600 ｜ epoch2: 0a/2r best=0.600 ｜ epoch3: 1a/1r best=**0.625** ｜ epoch4: 0a/2r best=0.625
- skill 文档体量：**1,594 → 19,373 字节**（initial→best），与 SearchQA 一样显著膨胀。
- 墙钟：**7,029s（≈117 min）** train ｜ 调用：**4,005** ｜ tokens：**110,734,896**（prompt 106,193,620 / completion 4,541,276）
  - 分解：rollout **3,926 calls / 109.1M**（主要开销）、analyst 46/1.28M、merge 20/0.18M、slow_update 3/0.073M、meta_skill 3/0.068M、ranking 7/0.033M
- 估算费用（deepseek-chat，$0.14/M in、$0.28/M out，未计缓存折扣）：
  - **train ≈ $16.14**（输入 106.19M×$0.14=$14.87 + 输出 4.54M×$0.28=$1.27）
  - STEP1 `eval initial`（test 280，独立 eval_only 进程，token 未计入 train 统计）：**估 ~$2–3**
  - **合计 ≈ $18–19（≈¥130–140）**

## 验收（对照 BRIEF win conditions / SearchQA 基线流程）
- [x] **端到端跑通**：codegen → subprocess 执行改 xlsx → openpyxl 官方语义评分，全链路无集成错误。
- [x] **正向提升**：best > initial（test 0.5286 > 0.4571，+7.1pts；val 0.625 > 0.400）。趋势与论文/SearchQA 一致。
- [x] **可复现**：seed=42；`config.json` / `history.json` / `summary.json` / `best_skill.md` 已存档（`results/ssb_dpsk_run1/`），fork commit 已记。
- [x] **平台期观察**：epoch 2/4 全 reject、best 卡 0.625——贪心局部最优，**正是 Phase-2 QD 要打破的现象**。
- [n/a] **对齐论文 / 官方 ckpt**：DeepSeek 口径不适用。

## 结论
vanilla SkillOpt 在 SpreadsheetBench（DeepSeek）上**端到端跑通**，并复现核心效果：把 1.6KB 种子技能优化成 19KB 文档，使 test EM 从 **0.4571 → 0.5286（+7.1pts）**，增益主要落在 cell-level。方向与 SearchQA（+5.6pts）一致。8 步中 6 步 reject、best 在第 6 步即定的**平台期**再次显现，为 Phase-2（QD / MAP-Elites）提供了干净的 **K=1 vanilla 参照基线**。
单轮成本：~110M tokens / ~$16 / ~117min（multi-turn + 代码执行，比 SearchQA 贵约一个量级）。

## 复现命令（DeepSeek）
```bash
# 1) 本地物化（在 HF 可达处；远程 AutoDL 的 HF 不通）
python tools/materialize_spreadsheetbench.py        # → SkillOpt/data/spreadsheetbench_{split,verified_400}
# 2) 远程 .env: AZURE_OPENAI_AUTH_MODE=openai_compatible / ENDPOINT=https://api.deepseek.com / API_KEY=...
git apply patches/deepseek-backend-adapter.patch    # 在 SkillOpt/ 内
cd SkillOpt && python scripts/train.py --config configs/spreadsheetbench/default.yaml \
  --optimizer_model deepseek-chat --target_model deepseek-chat --reasoning_effort "" --mode multi \
  --out_root outputs/ssb_dpsk_run1
```

## 存档产物（`results/ssb_dpsk_run1/`）
`best_skill.md`（19KB）、`history.json`、`summary.json`、`config.json`、`runtime_state.json`、`test_eval/summary.json`（best on test280）、`test_eval_baseline/summary.json`（initial on test280）；S0 另存 `results/ssb_eval_initial/eval_summary.json`。
