# REORG_PLAN — 执行清单（一把推前的全部本地工作）

> 分支: `reorg/2026-06-08`（off master，PROCESS Flow A）。目标: 修审计发现的 6 个 qd/ bug + 重建 descriptor + 建 `qd/loop.py` + reorg(收编 fork / 封存 / 带 benchmark) + **最后**建 fail-closed 预检门 → **一把推 master**。
> 计划来源: 2 轮 grounding+critique workflow（逐条核对源码）。本文件是跨 session 的恢复锚点。

## 🔖 RESUME HERE（当前状态，2026-06-08）
- 分支: `reorg/2026-06-08`。检查点已 commit: `conftest.py` + S1 修复 + 本 plan + 新根 `README.md`。
- 已完成: **S0 / F0 / S1**（`qd/tests` = **29 passed**）。
- **下一步 = S2**: 读 `qd/tests/test_descriptor_v0.py` + `test_descriptor_validation.py` → 重建 `qd/descriptor.py` axis1 = graded `op_density`（`phi[3]`→ops/line；`project` axis0=size+control、axis1=op_density；`uses_pandas` 留 φ 不用）→ 写 `ADR-0006` supersede `ADR-0002` → 更新 axis1 相关断言(含 `test_strategy_axis_tracks_pandas_usage`) + 加 graded-非退化测试 → `pytest` 绿。之后 **S4** 建 `qd/loop.py`。
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
- [ ] **S2** descriptor axis1=`op_density`（graded）；处理被弃的第 5 特征；→ ADR-0006 supersede ADR-0002。
- [ ] **S3** descriptor 测试: 非退化(两轴 graded/有方差) + 保 text-invariance；枚举更新所有 axis1 相关断言(含 `test_strategy_axis_tracks_pandas_usage`)。
- [ ] **S4** `qd/loop.py`: 抽 `produce_and_score_candidate`（rollout→reflect→merge→`scheduler.step()`→`rank_and_select`(from `skillopt.optimizer.clip`)→apply_patch→hash）。
- [ ] **S5** baseline 一次冻结 + 注入两臂（K=1 单格 elite；K>1 种 baseline 的 descriptor cell）。
- [ ] **S6** 一个共享 `EvalCounter` + 一个共享 cosine scheduler；`EvalCounter._cache`=sel_cache；暴露 per-arm expensive_evals / per-step edit_budget / n_occupied / cross-cell。
- [ ] **S7** K>1 路: probe traj→`descriptor.cell`→behavior dedup→`Archive.update`；记 n_occupied + cross-cell pickup。
- [ ] **S8** `test_k1_generation_path.py`（cosine 序列**程序化**导出 + `rank_and_select` 截断 + 决策等价 `evaluate_gate`）→ 闭 F3。
- [ ] **S9** loop 集成测试: n_occupied / shared-budget(同一对象) / shared-baseline。
- [ ] **S10** root `pyproject.toml`（path dep `vendor/SkillOpt`）。conftest 已先行。
- [ ] **S11** 提交 fork openai-compat 修复为 fork commit + **删 patch** + 加 `origin=Yihao-DD/SkillOpt` + 记 SHA。
- [ ] **S13** un-gitignore + 搬 `SkillOpt/`→`vendor/SkillOpt/`（plain，先记 fork SHA 再处理 `.git`）；reinstall editable；`handoff/RELEASES.md`。
- [ ] **S14** materialize 一次 + 提交 15MB tarball + items.json + `SOURCE.md`（sha256）到 `data/benchmarks/`；gitignore 解压目录。
- [ ] **S12** 封存 legacy → `_sealed_2026-06-08/` + tag `archive/pre-reorg-2026-06-08`；旧 headline 标 ARCHIVED（**在 S13 之后**）。
- [ ] **S15** 铺 `configs/frozen/<model>@<date>.yaml`(temp=0+seed-to-model) / `runs/index.csv` / `scripts/`(stamp/run/ingest/make_handoff/redline_lint，真实可测)。
- [ ] **S16** **最后** `scripts/preflight_gate.py`（fail-closed，binds 真符号；缺符号=FAIL）。
- [ ] **S17** 门自测 `scripts/tests/test_preflight_gate.py`（坏 fixture 必拒）+ redline_lint 自测。
- [ ] **S18** 全绿 + 门 PASS + 双树干净 + ADR 落 + MEMORY/INDEX/CHANGELOG → **merge master + 一把推 + tag**。

## one-push readiness（全为真才推）
pytest(qd+scripts/tests) 从干净 clone 全绿 · 3 个 K=1 测试绿(含生成路径) · descriptor 两轴 graded + text-invariance · loop 小 replay 上 `n_occupied>1` & cross-cell≥1（K=1 单格）· 两臂同一 `EvalCounter` + 等预算 + 同 baseline · 6 bug 都有回归测试 · 门 PASS 且对删符号 fail-closed + 门自测拒坏 fixture · fork vendored + 一份 openai-compat 修复 + SHA 记录 · 15MB tarball+items+SOURCE 提交、解压目录 gitignore · 双树 `git status` 干净 · `configs/frozen` 存在 · ADR-0003/4/5 在树、ADR-0006 落、legacy 封存+archive tag · MEMORY/INDEX/CHANGELOG 更新。
