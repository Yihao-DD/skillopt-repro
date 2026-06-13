# DeepSeek 三分割 × 3-seed 结果 — dpsk-3way-s{1,2,3}（2026-06-13）

> deepseek-chat ｜ **三分割协议**：gate 在 val（40 题）打分、终评在 **test 留出全集（280 题）** ｜ 等预算 24 evals/臂 ｜ frozen target temp=0 seed=42 / optimizer temp=0.8 ｜ 3 个独立 optimizer seed ｜ 串行 ~5h ｜ 自费 ~¥60
>
> **为什么换三分割**：此前所有跑 gate==报告集 → best 含 3.5-5.5pts「选择税」（劈半重放 `tools/analyze_selection_generalization.py` 实测）。三分割在 gate 没见过的 test 集上验收，消除该偏置；顺带 gate 评估 280→40 题，便宜 7×，使 3-seed 比单次旧全量还便宜。

## TEST 留出口径（真口径，论文用）

| test 留出分 | s1 | s2 | s3 | **均值** |
|---|---|---|---|---|
| baseline (INITIAL) | 0.4536 | 0.4643 | 0.4393 | **0.452** |
| K=1 贪心 | 0.4107 | 0.4536 | 0.3536 | **0.406** |
| **K=4 QD** | 0.5250 | 0.5714 | 0.4964 | **0.531** |
| K=4+RCV | 0.4357 | 0.3929 | 0.4107 | **0.413** |

## 三个结论 — 每个 3/3 seed 单独成立（非平均）

| 对比 | s1 | s2 | s3 | 均值 | pooled McNemar（840 配对） |
|---|---|---|---|---|---|
| **QD − 贪心** | +11.4 | +11.8 | +14.3 | **+12.5** | b=68 c=173 net=+105 **p=9.9e-12** |
| QD − baseline | +7.1 | +10.7 | +5.7 | **+7.9** | — |
| **贪心 − baseline** | −4.3 | −1.1 | −8.6 | **−4.6** | 3/3 负（负迁移） |
| **RCV − QD** | −8.9 | −17.9 | −8.6 | **−11.8** | b=166 c=67 net=−99 **p=7.1e-11** |

per-seed McNemar：QD>贪心 p=0.0003/0.0004/0.0000；RCV<QD p=0.0031/0.0000/0.0071 — 三 seed 各自显著。

## 解读

1. **核心一击（diversity as regularization）**：便宜 40 题 gate 上优化、到 280 题留出验收——**贪心三次全部优化到比「什么都不做」还差**（均值 −4.6pts，灾难性过拟合：把小 gate 噪声当规律拟合）。**QD 三次全部稳定跑赢贪心 +12.5pts（pooled p≈1e-11）、跑赢基线 +7.9pts**。QD 的 archive 强制行为多样性 = 隐式正则化，免疫过拟合。这是比「QD 逃出局部最优」更硬的机制故事，且首次明确。
2. **真实优势 > 重放预测**：劈半重放（只模拟「最后挑选」一步）预测 QD−贪心 +3.45pts；真三分割暴露出 +12.5pts。差距来自重放无法模拟贪心在搜索**全程**对噪声 gate 的累积过拟合。
3. **RCV 干净盖棺**：五种设定（N=20 / N=280 / 重放 / 三分割×3seed）全负，三 seed test 全部低于基线，pooled p≈1e-11 反向显著。archive 已吃尽多样性红利，拒绝账本是重复供给 → 降级为论文消融一节 + future work（AVOID-only / 退火 / 大预算变体未测）。

## 诚实边界

- 单 benchmark（SpreadsheetBench）+ 单模型（deepseek-chat）。SearchQA 公司侧测出平局（高基线、行为维度薄、headroom 小）→ 边界条件叙事：**探索是增益的必要非充分条件**，非「处处赢」。
- target ±2~3pts 复跑噪声（今日 baseline 0.439-0.464 vs 昨晚 0.479，同 temp=0）；+12.5pts margin 远超噪声带。
- optimizer seed 经 3 次独立随机实现（`OPTIMIZER_SEED` 已记录；fork 侧 enforcement 待第 4 个 fork commit，当前不可逐位复现，统计上等效）。
- n=3 seeds：sign 级 3/3 + pooled per-item McNemar 双重支撑；更多 seed 可收窄区间但方向已定。

## 复现

`python scripts/run_experiment.py --full --rcv --gate-split val --seed {1,2,3} --tag dpsk-3way-s{1,2,3}`
产物 `runs/full-dpsk-3way-s*/summary.json`（+ 各臂 `best_skill.md`/`elite_cell*.md` 落盘，供 M2 档案蒸馏）。
统计 `tools/analyze_returned_stats.py`（pooled_mcnemar）+ `tools/analyze_selection_generalization.py`（劈半重放/选择税）。
