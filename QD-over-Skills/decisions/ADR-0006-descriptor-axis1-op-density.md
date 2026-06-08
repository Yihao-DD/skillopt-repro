# ADR-0006 — descriptor axis1 重建（op_density 取代 1−uses_pandas）

- 状态: Accepted
- 日期: 2026-06-08
- 关联: **supersedes ADR-0002**；REORG_PLAN S2/S3；审计 P1（descriptor 塌缩 = 红线）；`qd/descriptor.py`、`qd/tests/test_descriptor_v0.py`。

## 背景
ADR-0002 定 axis1 = 1−uses_pandas（库策略）。审计发现：公司用「文档长度」轴（红线违规）固然最糟，但即便用 ADR-0002 的 pandas 轴，在真实 SpreadsheetBench 数据上该轴也**饱和** → best/initial 落同一格 → 档案塌成 1 格 →「全量 QD」退化成 vanilla-vs-vanilla（P1 根因）。

## 证据（descriptor spike，真实 fixtures `ssb_{best,initial}_feat.jsonl` 各 279 任务）
- axis1 = 1−uses_pandas 在 best/initial 上 **0.9785 / 0.8423，同落 bin 3**（nbins=4）→ 网格不可分；ADR-0002 的「分离」测试只因断言原始浮点 `b[1]`（非 `.cell`）才过。
- gate 提示的 `iter_depth` **无效**：mu[4]=iter_depth 在两 fixture 上 **均 0.2194**（饱和，且被 `project` 丢弃）。
- **op_density（每行 spreadsheet-op 调用数）是唯一弱可分的特征** → 选它做 axis1。
- 结论：在这个 benchmark+模型上数据**行为同质**，2-fixture 上 best≠initial 的格分离**不可达**；强行断言 = 过拟合。

## 决定
1. **axis1 = op_density**：φ[3] 由 `n_ops/16`（计数归一）改为真·密度 `n_ops/lines`；`project` axis1 = mu[3]。
2. **axis0 = 复杂度 = (code_len + ctrl)/2**（去掉 ops，避免两轴重叠）。
3. `uses_pandas` 保留在 φ（诊断）但 `project` 不再使用。
4. **真正的非退化判据移到 runtime**：`n_occupied>1`（100 题搜索 / 预检门 S16），**不在** 2-fixture 单测里断言 best≠init cell。
5. 本地单测改判：`test_descriptor_axes_are_graded_not_degenerate`（多样合成集上两轴 graded + 跨 ≥3 格）+ `test_strategy_axis_tracks_op_density`；保留 text-invariance（`test_descriptor_validation`）。`qd/tests` 29 passed。

## 理由
- 仍满足红线（只从 τ、不碰 skill 文字）；稳定性达标（probe 重采两轴 std<0.08，命题 3.2，测试验证）。
- 把「能不能产生行为多样性」这个真问题交给**会花钱的 runtime** 诚实回答，而不是用 2 个同质 fixture 假装在单测里解决。

## 影响 / 待验证（C）
- **战略风险（已知且记录）**：数据同质 → 即便 axis 修对，runtime 仍可能 `n_occupied=1`。那是**真发现**（需更强 optimizer / 换 benchmark / Tier-B 学习式 descriptor），预检门会**诚实暴露**、不糊弄。
- op_density 单轴信息量有限；Tier-B（T010）可在 φ 上学嵌入替代手设 g。
- 多 skill 的分格质量与抗 template-collapse 仍待 T003/T009 验证。
