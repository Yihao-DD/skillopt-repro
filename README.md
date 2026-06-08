# skillopt-repro — QD-over-Skills

> **任何 agent 第一眼读这里。** 本仓库在 `microsoft/SkillOpt` 之上做 **Quality-Diversity（MAP-Elites）搜索**（"QD-over-Skills"）：用「按行为分格的档案 + 格内严格 `>` gate」替代 SkillOpt 单点贪心 gate，逃出局部最优、又不破坏其稳定性（**K=1 = SkillOpt 特例**）。研究内容/红线见 `QD-over-Skills/`；协作/交付流程见 `PROCESS.md`。
> 本 README 自带**完整代码地图（每个 .py 干什么）** + **smoke test 复现步骤**，供两边跑对齐。

## ⛓️ 硬约定（最先判断）
prompt **每句**以 `在公司，` 开头 ⇒ **公司模式（runs-only）**：只跑 `run_experiment.py` + 填 `FEEDBACK.md`，**绝不改码 / commit / push**。无前缀 ⇒ 我方全权限。详见 `PROCESS.md §9` / `QD-over-Skills/AGENTS.md`。

## 读序（开工前按顺序读）
1. `QD-over-Skills/AGENTS.md` — agent 入口（红线 + 读序）。
2. `PROCESS.md` — 协作 SSOT：双单向通道、运行生命周期、预检门、结构 vs 约定诚实分级。
3. `QD-over-Skills/BRIEF.md` + `方案与数学推导.md`（SPEC）。
4. `QD-over-Skills/.tasks/INDEX.md` — 研究任务看板（SSOT）。
5. **`REORG_PLAN.md` — ⚠️ 当前活的执行清单（先看其 `RESUME HERE`）。**
6. **`LOCAL_ONLY.md` — 公司侧怎么从零跑起来（GitHub 缺件 + air-gap zip + 换 API=改 `.env` + 一键全量）。**

## 当前状态（2026-06-08，分支 `reorg/2026-06-08` == `master`）
封存+重组（审计 14 类失败模式后的响应 = 5 ADR + `PROCESS.md`；审计结论并入 `ADR-0003`，原始审计/记录已删除、可从 `archive/pre-reorg-2026-06-08` tag 取回）。
- **已完成 S0–S12 + 描述子真实数据标定 + S15 真实 adapter**：loop 全建（K=1==SkillOpt / K>1 descriptor 分格 / dedup / UCB 父格 / 等预算 stall-tolerant）；descriptor 标定到真实 558 条占 **16/16 格**（ADR-0006）；`qd/adapter_skillopt.py` 把 loop 接到真 SkillOpt+DeepSeek。**`qd/tests` = 39 passed（零 API）。**
- **🎯 真实验证已跑（DeepSeek，~$0.7，`tools/run_qd_validation.py`）—— 诚实负结果**：N=20、等预算 `eval_budget=12`，**贪心 K=1 best=0.65 赢 QD K=4 best=0.50**（K=4 探索 n_occupied=2 但薄、且多花 budget）。**[Q1] QD 探索 ✅；[Q2] QD payoff ❌**。详见下「🎯 验证结果」。
- **收口**：QD payoff 未获验证（小样本反对）。**定论需全量测试**（更大 N + 更长 budget + 接「瞄准着采」厚探索 —— 当前 `adapter.propose` 只是单纯 reflect，QD 未在最强形态下测过）。`scripts/run_experiment.py`（一键全量：`--full`/`--preflight`/`--dry-run`）+ `scripts/make_bundle.py`（air-gap 发包）+ `LOCAL_ONLY.md` **已补齐**（换 API=改 `.env`、全量=一条命令）；S16 更重校验（verify_checkout/run_provenance）+ vendor/benchmark 打包（S13/S14）仍待做。
- 旧无 provenance 产物（`docs/superpowers/`、`results/`、旧 baseline 报告、审计/工作记录）**已删除**，可从 `archive/pre-reorg-2026-06-08` tag 取回。

---

## 📂 代码地图：每个 .py 干什么

### `qd/` — QD-over-Skills 核心实现（我方）
| 文件 | 干什么 | 关键符号 | 状态 |
|---|---|---|---|
| `qd/__init__.py` | 包说明 + 红线声明（纯 API/无 GPU；K=1=SkillOpt；格内严格 `>`；descriptor 只从轨迹 τ）。无代码导出。 | — | 完整 |
| `qd/descriptor.py` | 行为描述子 b（Tier-A）：从轨迹的**生成代码**抽 φ∈[0,1]⁵ → μ → 手设投影 g → 2 轴（axis0=复杂度 `code_len+ctrl`、axis1=`op_density`（p95 归一）`n_ops/lines`）→ 网格 cell。**只从代码、不从 skill 文字**。 | `code_features` `phi` `mu` `project` `cell_of` `descriptor` | 完整（S2/S3 + 真实数据标定：558 条占满 16/16 格，ADR-0006） |
| `qd/archive.py` | MAP-Elites 档案 + 选择算子 U：每格严格 `>` gate（平局拒）；K=1 归一到单格（逐步 == SkillOpt）；K>1 每格一个 elite、空格直收；全局最优单调。None-sentinel（空档案真空）+ 可种**任意 cell**。 | `Elite` `UpdateResult` `Archive`(`update`/`elite`/`occupied_cells`/`global_best`/`current_*`/`best_*`) | 完整（S1 修过） |
| `qd/budget.py` | 昂贵评估的**去重 + 计数**：行为去重（按 cell+半径留最优 probe）；`EvalCounter`（cheap/expensive/cache-hit；hash 缓存，只在 miss 计昂贵）。 | `BehaviorCandidate` `behavior_distance` `deduplicate_by_behavior` `EvalCounter` | 完整（loop 用作共享 `EvalCounter` + `deduplicate_by_behavior` 行为去重） |
| `qd/variation.py` | 瞄准着采的本地契约（T004 桩）：archive 条件化 prompt + 按 novelty 配额选候选（**identity 去重** + `strict_novelty` 标志）。**还没接 LLM/optimizer**。 | `VariationRequest` `CandidateEdit` `build_variation_prompt` `select_candidate_edits` | 桩（loop 经注入 `CandidateProducer`；真生成器 S7+ 接） |
| `qd/scheduler.py` | 自适应调度（T007 桩）：`is_plateau` 检测（输入=best-so-far 单调序列）；plateau 触发增候选/novelty；UCB 选父格。 | `is_plateau` `PlateauScheduler` `ucb_cell_score` `choose_parent_cell` | loop 用 SkillOpt cosine + `choose_parent_cell`(UCB) 选父格；`is_plateau` 调度待接 |
| `qd/loop.py` | 集成循环：`produce_and_score_candidate`（注入 `CandidateProducer` → 零 API 可测）+ `run_search`（`eval_budget` 驱动两臂，stall-tolerant 花满等预算）；共享 baseline + 一个 `EvalCounter` + cosine；K=1==SkillOpt、K>1 按 descriptor 分格（grid=16）。 | `CandidateProducer` `produce_and_score_candidate` `run_search` `SearchResult` `ProposedCandidate` | 完整（S4–S9；真跑验证过） |
| `qd/adapter_skillopt.py` | **真实 model adapter（S15）**：把 `CandidateProducer` 接到真 SkillOpt SpreadsheetBench rollout / `compute_score` / `reflect` / `apply_patch` + DeepSeek；一个 skill 缓存一次 rollout 喂 score/probe/propose；`configure_deepseek()` 从 `.env` 配 openai-compat。**昂贵路径,仅 run/preflight 用,不进单测。** | `configure_deepseek` `SkillOptProducer` `make_producer` | 完整 + DeepSeek 真跑验证过 |

### `qd/tests/` — 39 个测试（逐项见下方复现节）
| 文件 | 测什么 | 数 |
|---|---|---|
| `test_k1_reduces_to_skillopt.py` | **K=1 == SkillOpt**：同 `(skill,score)` 序列喂 `skillopt.evaluation.gate.evaluate_gate`(oracle) 与 `Archive(k=1)`，断言 action+状态逐步一致。 | 2 |
| `test_k1_characterization.py` | slow-update 保护区 step-edit 跳过；真实 SpreadsheetBench history 8 步 replay。 | 3 |
| `test_descriptor_v0.py` | φ 有界/确定、`code_features` 解析、probe 重采稳定(sd<0.08)、cell 确定、两轴 graded、**真实 558 条占 ≥12/16 格非退化**（S2/S3 + 标定）。 | 9 |
| `test_descriptor_validation.py` | 红线：忽略 skill 文字（同轨迹→同 b）、按行为分（pandas vs openpyxl→不同 b）。 | 2 |
| `test_archive_multicell.py` | K>1：空格收、平局拒、格内独立、全局最优单调、**空档案真空、种任意 cell**（后 2 个 S1 新增）。 | 5 |
| `test_budget_smoke.py` | 行为去重 + `EvalCounter` cheap/expensive/cache-hit 计数。 | 2 |
| `test_variation_smoke.py` | prompt 契约；选择（novelty 配额、**identity 去重、strict raise**，后 2 个 S1 新增）。 | 4 |
| `test_scheduler_smoke.py` | plateau 检测需满窗、plateau 调度、UCB 选父格。 | 3 |
| `test_loop_generation_path.py` | K=1 决策逐步 == `evaluate_gate`（F3）；cosine 程序化；真 `rank_and_select` no-op；等预算两臂相等；K>1 路由 `n_occupied≥2`；**dedup 省评估 / cross-cell pickup / UCB 父格 / shared-baseline**（S7/S9）。 | 9 |

### `tools/` — 数据物化 + 验证（我方跑，公司不跑）
| 文件 | 干什么 |
|---|---|
| `tools/materialize_spreadsheetbench.py` | 从 HF `KAKA22/SpreadsheetBench` 物化 → `SkillOpt/data/spreadsheetbench_{split,verified_400}`（train=80/val=40/test=280）。 |
| `tools/spike_deepseek_feasibility.py` | DeepSeek 可行性 spike（temp=0，~5 调用）：连通性 + 真实代码的描述子分格。读 `.env`。 |
| `tools/analyze_descriptor_calibration.py` | 用 558 条真实 fixtures 标定描述子归一参数（零 API）→ ADR-0006 标定附录。 |
| `tools/preflight_deepseek_smoke.py` | S15 端到端 smoke（2 题真 DeepSeek，~$0.02）：验 adapter rollout/grade/reflect/gate 通。读 `.env`、写 `runs/`。 |
| `tools/run_qd_validation.py` | **真实 K=1 vs K>1 验证**（SpreadsheetBench+DeepSeek，frozen target temp=0 / optimizer temp=0.8，等预算）：打印 n_occupied / best / verdict + token。env 调 `N_SELECT/EVAL_BUDGET/K_BIG`。读 `.env`、写 `runs/`。 |
| `tools/materialize_searchqa.py` | 从 HF 物化 SearchQA split（Phase-1 遗留）。 |
| `tools/test_materialize_searchqa.py` | `materialize_searchqa` 的单测。 |

### `scripts/` — 公司一键全量入口（本次补齐启动面 S16）
| 文件 | 干什么 |
|---|---|
| `scripts/run_experiment.py` | **一键启动**：`--full`（test 全集 N=280，K=1 贪心 vs K=4 QD，等预算 12/臂）/ `--preflight`（2 题冒烟）/ `--dry-run`（零费用自检 fork+数据+key）。读 `.env` 换 API、设冻结 target（temp=0/seed=42）、写 `runs/<mode>/summary.json`（含 verdict、不含 key）。跑的是 `run_qd_validation` 同款核心，参数化成 CLI。 |
| `scripts/make_bundle.py` | **我方发包**：把仓库 + gitignored 的 `SkillOpt/` fork + SpreadsheetBench 数据 + `.env.example` 打成自包含 air-gap zip（排除 `.env`/`.git`/`outputs`/非 SSB 数据）+ sha256。`--dry-run` 看清单体积。 |
| `scripts/__init__.py` | 让 `scripts` 可被零 API 测试 import（`resolve_plan`/`_included`，见 `qd/tests/test_company_launch.py`）。 |

### 根目录
| 文件 | 干什么 |
|---|---|
| `conftest.py` | 让 `import skillopt` / `import qd` 在**干净 clone** 上可解析：prepend `vendor/SkillOpt`（或 `SkillOpt`）+ repo root 到 `sys.path`；**不依赖本机 editable `.pth`**。 |
| `pyproject.toml` | `qd` workspace：pytest `testpaths` + dev deps（openai/pytest/datasets）；fork 经 `-e ./SkillOpt` 单独装。 |
| `configs/frozen/deepseek-chat@2026-06-08.yaml` | 冻结目标 provenance（红线 P2）：target temp=0+seed、optimizer temp=0.8。 |
| `handoff/RELEASES.md` | vendored fork 的 release 记录：fork SHA `0948d2d` = upstream `ee9931e` + 2 个 adapter commit（openai-compat + 角色温度）。 |
| `.env.example` / `.env` | 后端凭据（`.env` gitignored，**绝不提交**；DeepSeek openai-compat：`AZURE_OPENAI_ENDPOINT/_API_KEY`）。 |

### 复用的关键 SkillOpt 模块（上游 fork `ee9931e`，QD loop 复用、不重写）
| 模块 | 角色 |
|---|---|
| `skillopt/evaluation/gate.py` | 严格 `>` gate（`evaluate_gate`，`cand_score > current_score`@123）。 |
| `skillopt/optimizer/scheduler.py` | cosine `edit_budget` 调度（`build_scheduler`/`CosineScheduler`，4→2）。 |
| `skillopt/optimizer/clip.py` | `rank_and_select`（按 edit_budget 截断 edits）。 |
| `skillopt/engine/trainer.py` | 原始训练环（rollout→reflect→aggregate→budget→clip→gate；baseline-once @900-918）。 |
| `skillopt/model/azure_openai.py` | 后端（含 openai-compat 适配：`_is_openai_compat_client` → `max_tokens`、去 `reasoning_effort`）。 |

---

## 🔁 复现 smoke test（确认你拿到和我一致的结果）

```bash
# 1) 环境（Python 3.10+；我方实测 3.13.6 通过）
python -m venv .venv
.venv\Scripts\python.exe -m pip install -U pip
.venv\Scripts\python.exe -m pip install -e ./SkillOpt -r requirements-extra.txt

# 2) 跑（conftest.py 自动解析 import，无需手动设 PYTHONPATH / 无需 API / 零费用）
.venv\Scripts\python.exe -m pytest qd/tests -v
```

**预期：`39 passed`，下列 39 项逐一 `PASSED`**（我方 2026-06-08 实测 `39 passed`）：
```
test_archive_multicell.py:  test_multicell_accepts_empty_cell_and_rejects_ties
                            test_multicell_per_cell_gate_and_global_best_are_monotone
                            test_k1_still_normalizes_all_updates_to_cell_zero
                            test_unparameterized_archive_is_truly_empty
                            test_baseline_can_seed_an_arbitrary_cell
test_budget_smoke.py:       test_deduplicate_by_behavior_keeps_best_probe_per_cell_radius
                            test_eval_counter_tracks_cheap_expensive_and_cache_hits
test_descriptor_v0.py:      test_phi_bounded_and_sized / test_phi_deterministic
                            test_code_features_parsing / test_phi_accepts_raw_code
                            test_descriptor_stable_under_probe_resampling
                            test_cell_deterministic_and_in_range
                            test_descriptor_axes_are_graded_not_degenerate
                            test_strategy_axis_tracks_op_density
                            test_descriptor_spreads_real_fixtures_across_grid
test_descriptor_validation.py: test_descriptor_ignores_skill_text_when_trajectory_behavior_matches
                            test_descriptor_separates_same_prompt_with_different_behavior
test_k1_characterization.py: test_step_edit_into_protected_region_is_skipped
                            test_normal_append_lands_before_protected_region
                            test_k1_replays_real_spreadsheetbench_history
test_k1_reduces_to_skillopt.py: test_k1_accepts_strictly_better_candidate_like_skillopt
                            test_k1_matches_skillopt_step_by_step_on_mixed_sequence
test_scheduler_smoke.py:    test_plateau_detection_requires_full_window
                            test_scheduler_increases_candidates_and_novelty_on_plateau
                            test_choose_parent_cell_uses_gain_uncertainty_and_novelty
test_variation_smoke.py:    test_variation_prompt_includes_archive_and_novelty_contract
                            test_select_candidate_edits_honors_novelty_quota_when_available
                            test_select_keeps_distinct_value_equal_candidates
                            test_strict_novelty_raises_when_quota_unmet
test_loop_generation_path.py: test_edit_budget_follows_cosine_schedule_programmatically
                            test_k1_decision_matches_evaluate_gate
                            test_real_rank_and_select_unchanged_when_pool_within_budget
                            test_equal_expensive_eval_budget_across_arms
                            test_k_gt_1_routes_distinct_behaviors_to_distinct_cells
                            test_dedup_collapses_same_behavior_candidates
                            test_cross_cell_pickup_is_recorded
                            test_parent_cell_selection_prefers_higher_gain_cell
                            test_both_arms_share_the_same_frozen_baseline
```

> `test_k1_*`（C0 红线）+ `test_loop_generation_path.py` 的 K=1 决策路径始终 == `evaluate_gate`。
> 这些是**零 API 的单元/集成 smoke**（公司复现到这一步即可）。**真实 DeepSeek 端到端验证**（付费）= `tools/run_qd_validation.py`（先 `.env` 配 key）→ 结果见下「🎯 验证结果」。

## 🎯 验证结果（真实 DeepSeek，2026-06-08，诚实记录）
`tools/run_qd_validation.py` · SpreadsheetBench `verified_400` · N=20 · 等预算 `eval_budget=12` · frozen target temp=0+seed / optimizer temp=0.8 · ~$0.7：

| | baseline | K=1（贪心/SkillOpt） | K=4（QD） |
|---|---|---|---|
| best hard | 0.45 | **0.65**（9 evals） | 0.50（12 evals，n_occupied=2，cross_cell=2） |

- **[Q1] QD 探索 = ✅**（K>1 铺到 2 格）。**[Q2] QD payoff = ❌** —— 贪心 K=1 赢、且更省（9 vs 12 evals）。
- **诚实结论**：当前规模/benchmark/模型下 **QD 不 work,贪心赢**。原因:探索薄（仅 2 格）、贪心没被困在局部最优、budget 短。**核心赌注（QD>贪心）未验证,小样本反对**（对照公司当初那个无效的 +7.1）。
- **定论需全量测试**：更大 N + 更长 budget + 把「瞄准着采」（target-cell-conditioned variation，`qd/variation.py`）接进 `adapter.propose` 加厚探索 —— 当前 propose 只是单纯 reflect，QD **未在最强形态下测过**。

## 布局（目录级）
```
skillopt-repro/
├── README.md / PROCESS.md / REORG_PLAN.md / pyproject.toml / conftest.py   # 入口 / 流程 / 清单 / 包 / import
├── qd/                  # QD 核心实现 + adapter_skillopt + tests（见上「代码地图」）
├── QD-over-Skills/      # SPEC + 文件系统 PM（.tasks SSOT / decisions ADR-0001..0006 / BRIEF / OPEN_DECISIONS）
├── handoff/            # 出站交付（RUNBOOK / RUN_REQUEST / FEEDBACK / RELEASES）
├── tools/              # 数据物化 + 可行性/标定/验证脚本
├── configs/frozen/     # 冻结目标 provenance（temp/seed，红线 P2）
├── scripts/            # 公司一键全量入口 run_experiment + 发包 make_bundle（本次补齐）
├── LOCAL_ONLY.md       # GitHub 缺件 + air-gap 交付 + 换API/全量步骤（公司冷启动读这个）
├── runs/               # rollout 产物（gitignored）
└── SkillOpt/           # 上游 fork（ee9931e + adapter commits；待 vendor 进 vendor/SkillOpt/，ADR-0004）
```
> 旧错误/无 provenance 文档（Phase-1 报告、`docs/superpowers/`、`results/`、审计、工作记录、冗余 patch）已删除，全部可从 `archive/pre-reorg-2026-06-08` tag 恢复。
