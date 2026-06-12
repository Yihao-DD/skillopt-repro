# DeepSeek 全量三臂结果 — dpsk-rcv-full（2026-06-13，自费 ~¥273）

> deepseek-chat ｜ N=280（test 全集）｜ 等预算 24 evals/臂 ｜ workers=16 ~7.5h ｜ frozen target temp=0 seed=42 / optimizer temp=0.8
> 产物 `runs/full-dpsk-rcv-full/summary.json`；75.65M tokens（55.4M in / 20.3M out）

| 臂 | best hard | n_occupied | cross_cell |
|---|---|---|---|
| baseline | 0.4786 | — | — |
| K=1 贪心 | 0.5607 | 1 | 0 |
| K=4 QD | **0.5786** | 2 | 3 |
| K=4+RCV | 0.5500 | **4** | **6** |

## 三个结论
1. **[Q2 双模型证据] QD>贪心的翻转在第二个模型家族复现**：+1.79pts（venus/qwen3.5 为 +2.1pts；两边都是小样本贪心赢、全量 QD 赢）。McNemar p=0.61（b=28,c=33）、CI [-3.6,+7.1]pts —— 单 run 不显著，与 venus 同病，**两个独立正向 run 构成模式但硬化仍需多 seed**。
2. **[Q3 诚实负结果] RCV 全量不付费**：0.550 < 裸QD 0.579（p=0.39 不显著差）。但机制起效了：**探索翻倍**（4/16 格 vs 2、cross_cell 6 vs 3、账本 25 条全程回流）。
3. **解读**：等预算下 AVOID+AIM 条件化把搜索推向更宽的行为空间（设计目标达成），代价是每格深度变浅 —— 24 evals 的预算被多样性摊薄。探索-开发权衡在这个预算点上偏向了探索过头。

## 后续优化（已备好，按性价比排序）
- **O1 退火条件化**：前半程 AIM+AVOID（铺格），后半程只 AVOID、瞄准已占格深挖（开发）。改 loop 一个 step 阈值即可。
- **O2 拆开消融**：AVOID-only 臂（不推格、只避坑）—— 可能纯增益；AIM 才是摊薄预算的部分。
- **O3 提预算重测**：48 evals/臂下 RCV 的宽探索可能后程发力（QD 自身正是大预算才翻转的）。
- **O4 预检开关**（--rcv-precheck）未测：省下的评估给深挖。
- 多 seed 误差棒（~¥250×2）：硬化 Q2 双模型主张优先于继续调 RCV。
