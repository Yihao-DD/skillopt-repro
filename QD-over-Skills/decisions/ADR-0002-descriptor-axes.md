# ADR-0002 — descriptor v0 轴选(代码级行为 φ)

- 状态: **Superseded by ADR-0006**（2026-06-08：axis1 = 1−uses_pandas 在真实数据饱和 → 档案塌缩 P1；改 graded op_density）
- 日期: 2026-06-06
- 关联: T002；SPEC §3.1 / 命题 3.2 / 3.8(ii)；BRIEF §4 红线(descriptor 只从 τ、不碰文字)。

## 背景
descriptor `b` 决定 QD 怎么把 skill 分格(SPEC §8「生死手」)。必须从轨迹 τ（非 skill 文字）抽，且能区分不同 skill 的「打法」。需定 φ(τ) 的轴。

## 证据(SpreadsheetBench，best vs initial 各 279 任务，取自 `results/ssb_dpsk_run1`)
- **result 级字段饱和**：归一 `n_turns` 0.219=0.219、`exec_ok` 0.986=0.986 在 best/initial 上**完全相同**；唯一差是 `solved`(0.529 vs 0.457)。→ result 级只反映性能 f，不反映打法；直接用会让 descriptor 退化成 fitness。
- **代码级字段区分打法**（从 `predictions/<id>/code.py` 抽）：`uses_pandas` best 0.02 vs initial 0.16、`lines` 70.7 vs 60.9、`n_ctrl` 14.1 vs 11.8、`n_ops` 8.3 vs 6.0。best 偏「长 openpyxl + 多控制流」，initial 偏 pandas。**这是真正的策略差**。

## 决定
descriptor v0 用**代码级 φ(τ)∈[0,1]^5**：`code_len / uses_pandas / ctrl_density / op_density / iter_depth`。Tier-A 手设 g → 2 可解释轴：
- **axis0 = 解题复杂度** = (code_len + ctrl + ops)/3
- **axis1 = 库策略** = 1 − uses_pandas（0=pandas 重 … 1=openpyxl/手写重）

网格 `nbins=4` → 16 格。

## 理由
- 满足红线（只从 τ、不碰文字）。
- 代码级捕捉 result 级看不到的打法差（上证）；稳定性达标（probe 重采 b 各轴 std<0.08，命题 3.2，测试验证）。
- 可解释、零 API、确定性 → 适合 v0 与回归测试。

## 影响 / 待验证(C)
- v0 仅在 2 个 skill 上验证区分性；**多 skill/候选的分格质量、楔子逃逸（命题 3.8 i/ii）留 T003**。
- 迭代深度轴信号弱（n_turns 多为 1）；Tier-B(T010) 可在 φ 上学嵌入替代手设 g。
- 轴是否够「双 Lipschitz / 抗 template collapse」→ T009 descriptor 验证实验。
