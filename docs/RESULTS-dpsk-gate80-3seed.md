# DeepSeek gate=80（SkillOpt 原文协议）× 3-seed 结果 — dpsk-train-s{1,2,3}（2026-06-13）

> deepseek-chat ｜ **gate=train(80)** = SkillOpt 原文的选择集（K=1 臂 == 原文 SkillOpt 协议）｜ 终评在 **test 留出(280)** ｜ 等预算 24 evals/臂 ｜ 3 独立 optimizer seed ｜ 在 AutoDL 48核机上 3 条并行（workers 12）｜ 自费
>
> **为什么这一档是"法庭"**：回答"对原文 SkillOpt 有实打实提升、而非另起炉灶"。此前 gate=40(val) 的 +12.5pts/p=1e-11 是在**比原文更小**的 gate 上得到的（更易让贪心过拟合 → 放大 QD 优势），不是对原文的数字。gate=80 才是原文协议下的可比结论。

## TEST 留出口径（真口径）

| test 留出分 | s1 | s2 | s3 | 均值 |
|---|---|---|---|---|
| baseline | 0.4714 | 0.4357 | 0.4536 | 0.454 |
| K1 贪心 | 0.4643 | 0.4464 | 0.4607 | 0.457 |
| **K4 QD** | 0.5214 | 0.4357 | 0.5571 | **0.505** |
| K4+RCV | 0.5286 | 0.4679 | 0.4964 | 0.498 |

## pooled McNemar（3 seed × 280 = 840 配对，逐题配对）

| 对比 | net | pooled p | s1 | s2 | s3 |
|---|---|---|---|---|---|
| **QD − 贪心** | +40 | **9.6e-3（显著）** | +16 (p=.068) | −3 (p=.82) | +27 (p=.005) |
| RCV − QD | −6 | 0.73（持平） | +2 | +9 | −17 |

## 结论（诚实定位）

1. **对原文有提升，统计显著但中等、seed 间不稳**：QD 均值 +4.8pts、pooled p=9.6e-3（<0.01）。但 3 seed 中 s3 显著赢(+27)、s1 边缘(+16, p=.068 未过)、**s2 实际略输(−3, 不显著)**。不能表述为"3/3 碾压"。

2. **gate-size 趋势是脊梁**（gate=40 vs 80 对照）：
   - QD−贪心：+12.5(p=1e-11) → +4.8(p=9.6e-3)，**优势随选择集增大单调衰减但仍显著**。
   - 贪心−baseline：−4.6(负迁移) → +0.4(消失)，**gate 大了贪心不再过拟合**。
   - 三者自洽于一个机制：**QD = 小 gate/高噪声 regime 的隐式正则化器**；正则化只在过拟合存在时有价值。

3. **RCV 盖棺（定位微调）**：gate=80 下 RCV≈QD（net −6, p=0.73 持平）；gate=40 下 RCV<QD（net −99, p=7e-11 显著差）。**从"小 gate 显著有害"到"大 gate 无害无益"，全程无正增益** → 论文消融一节 + future work。

## 诚实边界

- 单 benchmark（SpreadsheetBench）+ 单模型（deepseek-chat）。SearchQA（公司 qwen3.5）平局 = 边界条件。
- gate=80 的显著性靠 s3 撑、s1 边缘、s2 持平 → 中等强度，多 seed 可收窄但方向已定。
- target ±2~3pts 复跑噪声；optimizer seed 经 3 次独立随机实现（OPTIMIZER_SEED 记录，fork enforcement 待第 4 commit）。
- 主张应收窄为："评估预算受限(选择集偏小)时贪心过拟合甚至负迁移，QD 多样性正则化在此 regime 下显著缩小差距，优势随选择集增大而衰减。"

## 复现

`python scripts/run_experiment.py --full --rcv --gate-split train --seed {1,2,3} --tag dpsk-train-s{1,2,3}`（本次在 AutoDL 跑）。
统计：`tools/analyze_returned_stats.py`（pooled_mcnemar）。产物 `runs/full-dpsk-train-s*/summary.json` + 各臂 best_skill.md。
