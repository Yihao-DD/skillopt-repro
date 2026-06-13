# 完全忠于原文复现 + QD 注入 — review、可信度、预测、重构计划（2026-06-13）

## 0. 为什么要这次重构

用户要求「完全忠于原文 SkillOpt」再比较 greedy vs QD。审查发现：**fork 的 `engine/trainer.py` 就是原文完整实现**（三集分离 + slow/meta + epoch + rejected buffer + gate），而我们的 `qd/loop.py` 是绕过它的简化层。要忠于原文，应直接用 trainer，把 QD 作为 archive 维度注入。

## 1. 原文协议核对（基于 fulltext + trainer 代码）

| 机制 | 原文出处 | trainer 实现 |
|---|---|---|
| 三集 D_tr/D_sel/D_test | Eq 2/3, §3.1 | rollout `split=train`；gate `split="valid_seen"`(selection, trainer:1324)；report 在 test |
| forward (生成) | §3.2 | D_tr batch 40 rollout → reflect |
| backward (反思) | §3.3 | `run_minibatch_reflect`（失败/成功分组 minibatch） |
| 学习率 (edit budget) | §3.4 | `rank_and_select` clip 到 L_t，cosine 4→2 (trainer:1176) |
| 验证门 | §3.5 | `evaluate_gate` strict>，ties reject (trainer:1337) |
| rejected buffer | §3.5 | epoch 内负反馈 → `step_buffer_context` |
| slow update | §3.6 | `run_slow_update` 每 epoch 末；默认 **force-accept**（无条件注入 current+best，trainer:1755）|
| meta skill | §3.6 | optimizer 端，`format_meta_skill_context` 注入 reflect prompt |
| 默认超参 | line 560-567 | 4 epoch, rollout batch 40, minibatch 8, lr 4 cosine floor 2, slow 20 samples |

## 2. 上次结果（gate=40/80/120）可信度——分层判决

我们之前的跑用 `qd/loop.py`（简化层），相对原文有三层偏差：

| 偏差 | 影响 | 方向 |
|---|---|---|
| **合并集**（gate==生成集，原文 train 生成/val gate 分离） | 放大选择税，QD 抗选择税 → 利好 QD | 高估 QD |
| **无 slow/meta**（我们没实现，原文默认开） | greedy 阉割（原文 Table3: SSB 去掉 slow/meta 77.5→55.0，−22.5pts）→ 我们 greedy 远弱于原文完整版 | 低估 greedy |
| 迭代结构（eval_budget 计数 vs epoch×step×batch） | 简化，对照内部一致但非逐字 | 中性 |

**判决**：
- ✅ 可信 — 「QD archive 机制 > 单点贪心机制」（同简化 harness 公平消融，pooled McNemar 显著）；gate-size 趋势（优势随 gate 增大衰减）。
- ❌ 不可信 — 「对原文 SkillOpt 提升 X pts」：greedy 阉割了 slow/meta（原文 SSB 强表现关键，+22.5pts）+ 合并集放大 QD 优势 + 无一跑是原文逐字协议。
- ⚠️ 尖锐事实：原文 slow/meta 在 SSB 的贡献（+22.5）**远大于**我们测的 QD 优势（+4.8~12.5）。我们的 QD 是在关掉原文最强组件的阉割基线上展示优势的。

## 3. 预登记预测（跑前锁定，不许事后挪门柱）

完全忠于原文（trainer + slow/meta，greedy vs QD+archive）：

| 情形 | 预测 | 概率 |
|---|---|---|
| 中心 | greedy 大幅变强（deepseek 上 ~0.55-0.65，含 slow/meta）；QD−greedy +0~+3pts，很可能**不显著** | ~50% |
| 悲观 | QD ≈ 持平/不显著 — 之前优势几乎全是 artifact（合并集 + 阉割基线） | ~30% |
| 乐观 | QD 稳定 +2~4pts 显著 — SSB 真有 off-baseline 更优行为区（gate=80 时 QD best 稳定落 cell 9 暗示存在），archive 在原文之上仍有增量 | ~20% |

核心逻辑：越忠于原文 → greedy 越强、过拟合越轻 → QD 正则化红利越小。无论结果，诚实测量都有产出（QD 真有增量 = 硬结果；无增量 = 「评估协议 artifact 高估 skill 优化方法」的方法论警示）。

## 4. 重构计划（A 方案：trainer + archive 注入）

**核心设计**：trainer 加可选参数 `archive: Archive | None`。
- `archive=None` → **原文逐字**（greedy 臂；现有路径一字不改，git diff 验证 None 路径行为不变）。
- `archive=Archive(k=16)` → **QD**：
  - **parent**（step 开始的 current_skill）= `archive.elite(choose_parent_cell(...)).skill`（UCB 选格）；
  - **descriptor**：candidate 的 selection rollout 轨迹（`sel_eval_dir/predictions/*/code.py`）→ `qd.descriptor` → cell（零额外 rollout，复用 gate 的 sel rollout）；
  - **step gate**（trainer:1337-1366）：`archive.update(candidate, cand_score, cell)` 替代单点 `evaluate_gate`；
  - **best 报告** = `archive.best_skill`；
  - **slow update**（force-accept, trainer:1755）：注入到 archive 的 best elite + 当前 parent elite。

**K=1 红线**：greedy = `archive=None`（原文逐字）。`archive=Archive(k=1)` 冗余但应 == 原文（ADR-0001：archive k=1 == evaluate_gate）——作为回归测试断言。

**等预算**：两臂都跑原文 num_epochs×steps_per_epoch，**每 step 1 候选**（archive 不增候选数，parent 来自档案不增 rollout）→ 自动等预算（rollout 数相同）。这是比旧「K 候选/step」更干净的设计。

## 5. 测试策略
- archive 注入逻辑单测（zero-API）：parent=UCB elite、candidate 落格、格内 gate、best=archive.best。
- **archive=None 回归**：注入代码路径在 None 时与原文逐字等价（结构断言 + 关键路径不变）。
- 真跑验证：greedy(archive=None) 产出 == 原文 trainer；QD(k=16) n_occupied>1。

## 6. 风险（诚实标注）
- 改 fork 2000 行核心循环 → archive=None 路径必须逐字不变（最高优先级保护）。
- slow update × archive 交互（slow 注入哪些 elite）是最不确定的注入点，需小心。
- trainer 用 config 驱动 + 自己的 rollout 结构，QD descriptor 要对接 trainer 的 sel rollout 产物路径。
- 这是第 4 个 fork commit，记入 `handoff/RELEASES.md`。

## 7. 执行顺序
1. 理解 trainer 的运行入口 / config（怎么单跑一次）。
2. TDD：archive 注入（parent → gate → best → slow），每步保 archive=None 逐字。
3. 本机 zero-API 验证 + 一次真跑 smoke（小 config）。
4. AutoDL 上跑 greedy(None) vs QD(k=16)，3 seed，原文 4 epoch + slow/meta。
