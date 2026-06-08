# REORG_PLAN — 执行清单（一把推前的全部本地工作）

> 分支: `reorg/2026-06-08`（off master，PROCESS Flow A）。目标: 修审计发现的 6 个 qd/ bug + 重建 descriptor + 建 `qd/loop.py` + reorg(收编 fork / 封存 / 带 benchmark) + **最后**建 fail-closed 预检门 → **一把推 master**。
> 计划来源: 2 轮 grounding+critique workflow（逐条核对源码）。本文件是跨 session 的恢复锚点。

## 🔖 RESUME HERE（当前状态，2026-06-08）
- 分支: `reorg/2026-06-08`（== `master`）。**已 merge master + 推 origin（`82077db`，纯净）**；`archive/pre-reorg-2026-06-08` tag 已推（删掉的 audit/工作记录/旧产物可 `git checkout <tag> -- <file>` 恢复）。
- 已完成: **S0–S12 + 描述子真实数据标定 + S15 真实 adapter + 真实 DeepSeek 验证**（`qd/tests` = **39 passed**；master `c259b8f`+）。`qd/adapter_skillopt.py` 接真 SkillOpt+DeepSeek；`tools/run_qd_validation.py` 跑了公平 K=1-vs-K=4（N=20、等预算 12、frozen target temp=0 / optimizer temp=0.8、~$0.7）。
- **🎯 验证 verdict（诚实负结果，已收口）**: 贪心 **K=1(0.65) 赢 QD K=4(0.50)**；[Q1] QD 探索 ✅ / [Q2] payoff ❌ → **QD 当前不 work**（探索薄 2 格、贪心没被困在局部最优、budget 短）。**真正定论 = 全量测试**（更大 N + 更长 budget + 把「瞄准着采」`qd/variation.py` 接进 `adapter.propose`，让 QD 在最强形态下测）。
- **剩余待做（非阻塞）**: S13/S14（un-gitignore + vendor `SkillOpt/`→`vendor/SkillOpt/` + benchmark tarball，交付公司前）、S16 `scripts/preflight_gate.py`（预检门）。
- 研究任务看板（T0XX）见 `QD-over-Skills/.tasks/INDEX.md`，reorg 完成后恢复。决策/硬伤已锁定，见下两节。

## 已锁定的决策（"按你建议来"）
- **descriptor**: axis1 = `op_density`(graded，唯一能分开的)；本地测试改判「两轴 graded/非常数」；**真正非退化判据 = runtime `n_occupied>1`**（100 题搜索）。spike 证明 2-fixture 同质、测不出 best≠init cell。
- ADR-0002 用 **ADR-0006 supersede**（干净 provenance）。
- 15MB benchmark tarball **plain commit**（无 lfs）。
- 受控对比: `slow_update/meta=OFF`、`update_mode=patch`、cosine LR；两臂共享一个 scheduler。
- 战略风险（已知）: 数据同质 → 即便修对，runtime 可能 `n_occupied=1`；那是真发现（需更强 optimizer / 换 bench / Tier-B），门**诚实暴露**，不糊弄。

## Critique 硬伤（已折进步骤）
- **F1**: patch 已「未提交即已应用」（×3，apply 失败）→ 提交 in-tree 改动 + **删 patch**，绝不重 apply。✅已确认(S0)
- `build_scheduler` 真实路径 = `skillopt.optimizer.scheduler`（非 `skillopt.scheduler`）。
- `Archive` 只能种 cell 0 + cell-range 守卫 `0<=cell<k` 会崩（descriptor cell∈[0,nbins²)）→ 改构造器支持种**任意 cell** + `k>=nbins²`（或稀疏键）。
- cosine 序列**程序化导出**（别硬编码 `[4,4,3,3,3,2,2,2]`，banker's rounding 脆）。
- 搬 vendor 破 `.pth`（conftest 已兜底）+ fork 是嵌套独立 `.git`（搬前先记 fork SHA）；lfs/plain 在提交前定（=plain）。
- 测试回归: axis1 改后 `test_strategy_axis_tracks_pandas_usage` 等会红 → S3 枚举更新所有 axis1 相关断言。
- 依赖边修正: S10 acceptance 依赖 post-S13；S16 加 depends S3；S12 封存挪到 S13 之后。

## 步骤（√=done）
- [x] **S0** 建分支 + 捕获 fork 脏态 + 确认 F1。
- [x] **F0** root `conftest.py`（解耦 import）+ 本 plan + pytest 基线绿。
- [x] **S1** 修 MED/LOW bug: variation 按值去重(identity)、novelty 欠填(strict 标志)、archive None sentinel + 种任意 cell。+4 回归测试。（is_plateau 逻辑本就对，仅文档；29 passed）
- [x] **S2** descriptor axis1=`op_density`（graded，`n_ops/lines`）；axis0=`(code_len+ctrl)/2`；`uses_pandas` 留 φ 不用；ADR-0006 supersede ADR-0002。
- [x] **S3** descriptor 测试: `_axes_are_graded_not_degenerate`（两轴 graded + 跨≥3格）+ `_tracks_op_density` 换掉 pandas 轴断言；保 text-invariance；RED→GREEN 验证，29 passed。
- [x] **S4** `qd/loop.py`: `produce_and_score_candidate`(propose→`rank_and_select`(lazy clip)→apply→descriptor cell→`EvalCounter` 计数) + `run_search`(eval_budget 驱动)。model 用 `CandidateProducer` 注入 → 零 API 可测。
- [x] **S5** baseline 一次注入两臂（`Archive(baseline_skill/score/cell)`；K=1 归一单格、K>1 种 baseline_cell）。
- [x] **S6** 一个共享 `EvalCounter`（cache by skill-hash = 去重）+ cosine；`SearchResult` 暴露 `expensive_evals/n_occupied/edit_budgets`；等预算由 eval_budget 强制（测试验证两臂相等）。
- [x] **S7** K>1 路: probe→`descriptor.cell`→`Archive.update`；接 `deduplicate_by_behavior`（行为去重省昂贵预算）+ UCB `choose_parent_cell`（父格按 elite-gain + 探索选，`_select_parent_cell`）；记 cross-cell pickup。
- [x] **S8** `test_loop_generation_path.py`：K=1 决策**逐步等价 `evaluate_gate`** + cosine 程序化导出 + 真 `rank_and_select` no-op 分支 → **闭 F3**。
- [x] **S9** loop 集成测试: 等预算两臂相等 + K>1 路由 + **dedup 省评估** + **cross-cell pickup** + **shared-baseline 两臂一致**（共 9 个 loop 测试）。
- [x] **S10** root `pyproject.toml`（qd 包 + pytest `testpaths` + dev deps；fork 仍经 `-e ./SkillOpt` 装，conftest 解析 import）。bare `pytest` → 39 passed。
- [x] **S11** fork openai-compat 修复已提交为 fork commit **`05a023c`**（base upstream `ee9931e`）+ 加 origin remote（未推）+ patch 早已删。SHA 记于 `handoff/RELEASES.md`。
- [ ] **S13** un-gitignore + 搬 `SkillOpt/`→`vendor/SkillOpt/`（plain，先记 fork SHA 再处理 `.git`）；reinstall editable；`handoff/RELEASES.md`。
- [ ] **S14** materialize 一次 + 提交 15MB tarball + items.json + `SOURCE.md`（sha256）到 `data/benchmarks/`；gitignore 解压目录。
- [x] **S12**（改为**删除**，user 2026-06-08，非 `_sealed_`）：删 audit/工作记录/旧 baseline/`docs`/`results`/`patches` + tag `archive/pre-reorg-2026-06-08`（已推 origin，可恢复）。**已 merge master + 推**（`82077db`）。注：master 现为「重组进行中」诚实态，S18 仍是完成里程碑。
- [ ] **S15** 铺 `configs/frozen/<model>@<date>.yaml`(temp=0+seed-to-model) / `runs/index.csv` / `scripts/`(stamp/run/ingest/make_handoff/redline_lint，真实可测)。
- [ ] **S16** **最后** `scripts/preflight_gate.py`（fail-closed，binds 真符号；缺符号=FAIL）。
- [ ] **S17** 门自测 `scripts/tests/test_preflight_gate.py`（坏 fixture 必拒）+ redline_lint 自测。
- [ ] **S18** 全绿 + 门 PASS + 双树干净 + ADR 落 + MEMORY/INDEX/CHANGELOG → **merge master + 一把推 + tag**。

## one-push readiness（全为真才推）
pytest(qd+scripts/tests) 从干净 clone 全绿 · 3 个 K=1 测试绿(含生成路径) · descriptor 两轴 graded + text-invariance · loop 小 replay 上 `n_occupied>1` & cross-cell≥1（K=1 单格）· 两臂同一 `EvalCounter` + 等预算 + 同 baseline · 6 bug 都有回归测试 · 门 PASS 且对删符号 fail-closed + 门自测拒坏 fixture · fork vendored + 一份 openai-compat 修复 + SHA 记录 · 15MB tarball+items+SOURCE 提交、解压目录 gitignore · 双树 `git status` 干净 · `configs/frozen` 存在 · ADR-0003/4/5 在树、ADR-0006 落、legacy 封存+archive tag · MEMORY/INDEX/CHANGELOG 更新。
