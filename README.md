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

## 当前状态（2026-06-08，分支 `reorg/2026-06-08`）
封存+重组中（审计 `审计报告-公司工作记录.md` 14 类失败模式后的响应 = 5 ADR + `PROCESS.md`）。
- **已完成**：S0（分支+F1）、F0（conftest + plan）、**S1（6 bug 修复，`qd/tests` 29 passed）**。
- **未完成（诚实）**：`qd/loop.py` **还没建**（S4）→ **现在还不能真正跑一次 QD 搜索**；descriptor axis1 待重建（S2，当前会塌成 1 格）；`scripts/`/预检门/数据自带（S14-16）未做。
- **下一步 = S2**（重建 descriptor，见 `REORG_PLAN.md`）。旧 Phase-1（SearchQA+GPT-5.5）脚手架已被取代，将封进 `_sealed_2026-06-08/`。

---

## 📂 代码地图：每个 .py 干什么

### `qd/` — QD-over-Skills 核心实现（我方）
| 文件 | 干什么 | 关键符号 | 状态 |
|---|---|---|---|
| `qd/__init__.py` | 包说明 + 红线声明（纯 API/无 GPU；K=1=SkillOpt；格内严格 `>`；descriptor 只从轨迹 τ）。无代码导出。 | — | 完整 |
| `qd/descriptor.py` | 行为描述子 b（Tier-A v0）：从轨迹的**生成代码**抽 φ∈[0,1]⁵（`code_len/uses_pandas/ctrl/op/iter`）→ probe 均值 μ → 手设投影 g → 2 轴 → 网格 cell。**只从代码、不从 skill 文字**。 | `code_features` `phi` `mu` `project` `cell_of` `descriptor` | ⚠️ axis1 饱和，S2 重建为 `op_density` |
| `qd/archive.py` | MAP-Elites 档案 + 选择算子 U：每格严格 `>` gate（平局拒）；K=1 归一到单格（逐步 == SkillOpt）；K>1 每格一个 elite、空格直收；全局最优单调。None-sentinel（空档案真空）+ 可种**任意 cell**。 | `Elite` `UpdateResult` `Archive`(`update`/`elite`/`occupied_cells`/`global_best`/`current_*`/`best_*`) | 完整（S1 修过） |
| `qd/budget.py` | 昂贵评估的**去重 + 计数**：行为去重（按 cell+半径留最优 probe）；`EvalCounter`（cheap/expensive/cache-hit；hash 缓存，只在 miss 计昂贵）。 | `BehaviorCandidate` `behavior_distance` `deduplicate_by_behavior` `EvalCounter` | 完整（未被 loop 实例化，S6 接） |
| `qd/variation.py` | 瞄准着采的本地契约（T004 桩）：archive 条件化 prompt + 按 novelty 配额选候选（**identity 去重** + `strict_novelty` 标志）。**还没接 LLM/optimizer**。 | `VariationRequest` `CandidateEdit` `build_variation_prompt` `select_candidate_edits` | 桩（S4 接真生成） |
| `qd/scheduler.py` | 自适应调度（T007 桩）：`is_plateau` 检测（输入=best-so-far 单调序列）；plateau 触发增候选/novelty；UCB 选父格。 | `is_plateau` `PlateauScheduler` `ucb_cell_score` `choose_parent_cell` | 桩（未被 loop 调用，S6/S7 接） |
| `qd/loop.py` | **（待建 S4–S7）** 集成循环：两臂（K=1 vanilla + K>1 QD）共享 baseline + **一个** EvalCounter + **一个** cosine 调度；复用 SkillOpt 的 rollout→reflect→`rank_and_select`→gate。 | — | **不存在** |

### `qd/tests/` — 29 个测试（逐项见下方复现节）
| 文件 | 测什么 | 数 |
|---|---|---|
| `test_k1_reduces_to_skillopt.py` | **K=1 == SkillOpt**：同 `(skill,score)` 序列喂 `skillopt.evaluation.gate.evaluate_gate`(oracle) 与 `Archive(k=1)`，断言 action+状态逐步一致。 | 2 |
| `test_k1_characterization.py` | slow-update 保护区 step-edit 跳过；真实 SpreadsheetBench history 8 步 replay。 | 3 |
| `test_descriptor_v0.py` | φ 有界/确定、`code_features` 解析、probe 重采稳定(sd<0.08)、cell 确定、best/init 分离。**⚠️ 含 S2 要改的 axis1 断言。** | 8 |
| `test_descriptor_validation.py` | 红线：忽略 skill 文字（同轨迹→同 b）、按行为分（pandas vs openpyxl→不同 b）。 | 2 |
| `test_archive_multicell.py` | K>1：空格收、平局拒、格内独立、全局最优单调、**空档案真空、种任意 cell**（后 2 个 S1 新增）。 | 5 |
| `test_budget_smoke.py` | 行为去重 + `EvalCounter` cheap/expensive/cache-hit 计数。 | 2 |
| `test_variation_smoke.py` | prompt 契约；选择（novelty 配额、**identity 去重、strict raise**，后 2 个 S1 新增）。 | 4 |
| `test_scheduler_smoke.py` | plateau 检测需满窗、plateau 调度、UCB 选父格。 | 3 |

### `tools/` — 数据物化（我方一次性 build，公司不跑）
| 文件 | 干什么 |
|---|---|
| `tools/materialize_spreadsheetbench.py` | 从 HF `KAKA22/SpreadsheetBench` 物化 → `SkillOpt/data/spreadsheetbench_{split,verified_400}`（train=80/val=40/test=280）。 |
| `tools/materialize_searchqa.py` | 从 HF 物化 SearchQA split（Phase-1 遗留）。 |
| `tools/test_materialize_searchqa.py` | `materialize_searchqa` 的单测。 |

### 根目录
| 文件 | 干什么 |
|---|---|
| `conftest.py` | 让 `import skillopt` / `import qd` 在**干净 clone** 上可解析：prepend `vendor/SkillOpt`（或 `SkillOpt`）+ repo root 到 `sys.path`；**不依赖本机 editable `.pth`**。 |

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

**预期：`29 passed`，下列 29 项逐一 `PASSED`**（我方 2026-06-08 实测 `29 passed in 1.13s`）：
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
                            test_descriptor_separates_best_from_initial
                            test_strategy_axis_tracks_pandas_usage
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
```

> ⚠️ 这 **29 项是 S2 之前的基线**。S2 重建 descriptor 后，`test_descriptor_v0.py` 里 `test_descriptor_separates_best_from_initial` / `test_strategy_axis_tracks_pandas_usage` 会被换成「graded 非退化」断言（届时数会变）。`test_k1_*`（C0 红线）始终保持绿。
> 这些是**零 API 的单元/集成 smoke**，**不是**端到端 QD 实验（那要等 `qd/loop.py`，S4）。

## 布局（目录级）
```
skillopt-repro/
├── README.md / PROCESS.md / REORG_PLAN.md / conftest.py   # 入口 / 流程 / 执行清单 / import 解析
├── qd/                  # QD 核心实现 + tests（见上「代码地图」）
├── QD-over-Skills/      # SPEC + 文件系统 PM（.tasks SSOT / decisions ADR-0001..0005 / BRIEF / OPEN_DECISIONS）
├── handoff/            # 出站交付（RUNBOOK + RUN_REQUEST/FEEDBACK 模板）
├── tools/              # 数据物化脚本
├── SkillOpt/           # 上游 fork（ee9931e；待 vendor 进 vendor/SkillOpt/，ADR-0004）
├── patches/            # deepseek-backend-adapter.patch（已并入 fork 工作树，S11 删）
└── 审计报告-公司工作记录.md / 工作记录-完整版.md           # 审计 + 公司记录（将封进 _sealed_）
```
