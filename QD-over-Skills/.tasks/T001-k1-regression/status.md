# T001 状态
- 状态: IN_PROGRESS
- 最后更新: 2026-06-05  by (claude session)
- 进度:
  - ✅ 深读 `SkillOpt/` 源码 + `decisions/ADR-0001`(accept 语义 / current-best / slow-update / 受保护字段,带 file:line)。
  - ✅ 搭 `qd/` 包(workspace 根,import 已 editable 安装的 `skillopt`),TDD 实现 K=1 `U`(`qd/archive.py`):单 cell 档案 + 格内严格 `>` gate、平局拒;elite 同时扮 current/best。
  - ✅ 2 测试 GREEN(`qd/tests/test_k1_reduces_to_skillopt.py`,RED→GREEN 全程已验、零付费、毫秒级):
    ① 严格更优 → accept(对 `evaluate_gate` oracle);
    ② 5 步混合序列**逐步对齐** `evaluate_gate`(accept / worse-reject / tie-reject / new-best / tie-reject)。
- Blocker: 无(不依赖 API)。
- 下一步(给下个 session 的具体动作):
  1. 受保护 slow-update 字段 characterization 测试:复用 `skillopt.optimizer.skill.apply_patch`,造带 `<!-- SLOW_UPDATE_* -->` 的 skill + 一条 target 落在保护区的 edit,断言保护区不被覆盖(与 SkillOpt 一致)。
  2. 真实数据回归:从 `results/`(或 `SkillOpt/outputs/`)的 `history.json` 截 (selection_hard, action) 序列,replay 过 qd K=1,与 SkillOpt 记录逐步对齐。
  3. 跑通 → INDEX 标 REVIEW、写 `summary.md`、`CHANGELOG.md` 记一行。
