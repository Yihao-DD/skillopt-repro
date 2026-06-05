# T001 — K=1 回归测试 Summary

- 状态：**REVIEW**（待复核转 DONE）
- 完成日期：2026-06-06
- 关联：SPEC 命题 3.6；成功判据 **C0**；BRIEF §4 红线第 2 条；ADR-0001。

## 结论
QD 的 **K=1 档案 `U`**（`qd/archive.py`：单 cell + 格内严格 `>` gate + 平局拒；elite 同扮 current/best）在 **per-step 选择逻辑**上与 SkillOpt **逐决策等价**，且 step edit 不覆盖受保护 slow-update 区。**C0 成立**（QD 是 SkillOpt 的 K=1 特例）。

## 交付
- `qd/archive.py` — K=1 MAP-Elites 档案 + `U.update`（accept/reject）。
- `qd/tests/test_k1_reduces_to_skillopt.py` — 2 测试，对 `evaluate_gate` oracle 逐步等价。
- `qd/tests/test_k1_characterization.py` — 3 测试：slow-update 保护×2 + 真实 ssb history replay×1。
- `decisions/ADR-0001` — accept 语义 / current==best 不变量 / 受保护字段（带 file:line）。

## 验证
AutoDL Python 3.12.3：`pytest qd/tests/` → **5 passed in 0.34s**，零付费、毫秒级。
真实 replay 锚定 `results/ssb_dpsk_run1`（SpreadsheetBench vanilla，8 步，含 step2 平局 reject），`action/current/best/best_step` 全对齐。

## 语义边界（ADR-0001）
- T001 范围 = per-step 选择逻辑（`current==best` 不变量下，gate 只走 `accept_new_best`/`reject`）。
- epoch 级 slow-update 的 current/best 分叉、gated 模式 → 不在 T001，留 **T005**（K>1）再议。

## 下一步
**T002**（descriptor v0：轨迹 τ → φ → Tier-A `g` → cell，**不碰文字、不依赖 API**）。
