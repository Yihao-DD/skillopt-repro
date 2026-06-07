# INDEX — 任务看板（SSOT）

> 任务状态的唯一权威来源。状态变更**先改这里，再改对应 `status.md`**。
> 状态：`TODO | IN_PROGRESS | BLOCKED | REVIEW | DONE | DROPPED`

## 🚩 阻塞项
- **BLOCKER-1（API / 模型访问）** — 见 `OPEN_DECISIONS.md`，**待公司**。阻塞一切昂贵付费实验（T008、T011…）；不阻塞本地工作。

## 📌 决策记录
- **主战场 benchmark = SpreadsheetBench**（高余量 +38.9、多策略空间；用于楔子 T003 与主结果）。第二 benchmark：OfficeQA（通用性）。**不**用 SearchQA（饱和）/ DocVQA（多模态）/ LiveMath（策略空间窄）作主战场。
- **SearchQA 复现的平台期观察仅供参考**：SearchQA 近天花板，平台期分不清「局部最优 vs 天花板」，故 GATE-0 的 payoff 须在 SpreadsheetBench 上重测。

## Phase 0 — 验证 payoff 与可行性

| ID | 任务 | 状态 | 依赖 | 验收要点 / 备注 |
|----|------|------|------|----------------|
| T000 | 复现 SkillOpt | **DONE** | — | ✅ DeepSeek：SearchQA EM 0.747→0.804（4 accept 后 36 连拒，已推 GitHub）；**+ 主战场 SpreadsheetBench EM 0.457→0.529（+7.1），平台期再现（8 步 2 收 6 拒）** → `ssb_baseline_report.md`/`results/ssb_dpsk_run1` |
| T001 | $K=1$ 回归测试（档案单格 == SkillOpt） | **DONE** (06-07 smoke) | T000 | ✅ 5 测试 GREEN：gate-oracle 等价×2 + slow-update 保护×2 + 真实 ssb history replay×1。语义 → `decisions/ADR-0001` |
| T002 | descriptor v0（τ→φ→Tier-A g→cell，**不碰文字**） | **DONE** (06-07 smoke) | T000 | ✅ 代码级 φ；8 测试 GREEN（φ有界 / 稳定 std<0.08 / best≠initial 可分）。轴选 → `ADR-0002` |
| T003 | 楔子 + 逃逸依赖测（**在 SpreadsheetBench 上**） | BLOCKED (06-07) | T001,T002,BLOCKER-1 | 需付费/API 决策；当前仅有单题 SpreadsheetBench smoke，未做楔子实验 |
| **GATE-0** | payoff 在不在（SpreadsheetBench）？变异源够不够？→ 写 ADR | TODO | T003 | 否则转向 / 止损 |

## Phase 1 — 低风险结果

| ID | 任务 | 状态 | 依赖 | 验收要点 |
|----|------|------|------|----------|
| T004 | 瞄准着采变异 `V` | **REVIEW** (06-07 smoke) | T002 | ✅ `qd/variation.py`：archive prompt + novelty quota candidate selection；smoke GREEN |
| T005 | 档案 + 格内 gate `U` | **REVIEW** (06-07 smoke) | T001,T002 | ✅ `qd/archive.py` K>1：空格收、格内严格 `>`、全局最优单调；smoke GREEN |
| T006 | 去重 + 缓存 + 成本计数 `Π`(一) | **REVIEW** (06-07 smoke) | T002,T005 | ✅ `qd/budget.py`：行为去重、cache、cheap/expensive 计数；smoke GREEN |
| T007 | 自适应 k 调度 `Π`(二) | **REVIEW** (06-07 smoke) | T005,T006 | ✅ `qd/scheduler.py`：plateau 检测、候选数/novelty/gamma 调度、UCB cell 选择；smoke GREEN |
| T008 | Phase-1 集成实验（SpreadsheetBench，**同预算**逃逸） | TODO | T004–T007,BLOCKER-1 | 续爬 vs SkillOpt plateau |
| **GATE-1** | 同预算逃逸复现了吗？→ 写 ADR | TODO | T008 | |

## Phase 2 — 冲刺

| ID | 任务 | 状态 | 依赖 | 验收要点 |
|----|------|------|------|----------|
| T009 | descriptor 验证实验（文字 vs 行为） | TODO | T002 | 判别性（SPEC §3.1 C） |
| T010 | Tier-B 学出 descriptor | TODO | T002,T009 | |
| T011 | 全面对比（SpreadsheetBench + OfficeQA，**同预算**打 SkillOpt + EvoSkill） | TODO | T008,T010,BLOCKER-1 | 成功判据 C2 |
| T012 | 迁移实验（跨模型 / 跨 harness） | TODO | T011 | 成功判据 C3 |
| T013 | (理论，导师向，可选) 调度 `Π` 的 regret 推导 | TODO | T007 | SPEC §9 |

---
_当前活跃任务_：**T004–T007 → REVIEW**（本地 QD 组件 smoke GREEN，AutoDL py3.12）。**T003 BLOCKED**：楔子/逃逸依赖测需要公司 API/预算决策；在此之前可继续做低成本集成 harness / loop smoke。
