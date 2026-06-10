# SkillOpt QD-over-Skills — SpreadsheetBench 全量结果

> 后端 venus llmproxy · `qwen3.5-397b-a17b` ｜ 全部 **280 题**(test 全集)｜ 等预算 **24 evals/臂** ｜ 总耗时 ~18.6h
> Run tag `venus-qwen35` ｜ 完成时间 2026-06-09T21:31Z ｜ 冻结 target: temperature=0, seed=42；optimizer temperature=0.8

> **归档记录**（2026-06-09）：公司侧结果报告，run tag `venus-qwen35`。权威产物 = 回传包 `returned-venus-qwen35.zip`（321 MB, sha256 `013dec38…4751`）内的 `summary.json`，**未随仓库**（体积太大，需另存）。仓库为 public，venus 内部 endpoint 已脱敏。

## TL;DR

在 SpreadsheetBench 全量 280 题、等 24-eval 预算下,**QD（K=4）以 0.600 击败贪心基线（K=1）的 0.579（+2.1 pts，多解出 6 道题）**，并实证了行为多样性探索（n_occupied=2、cross_cell=1）。论文两个核心问题 **Q1（QD 是否探索）与 Q2（等预算下 QD 是否更优）双双成立**。

## 主结果

| 方法 | best (硬通过率) | 解出 /280 | n_occupied | cross_cell | vs baseline |
|------|----------------|-----------|------------|------------|-------------|
| baseline (INITIAL skill) | 0.4036 | 113 | — | — | — |
| K=1 贪心（对照） | 0.5786 | 162 | 1 | 0 | **+17.5 pts** |
| **K=4 QD（本文方法）** | **0.6000** | **168** | **2** | **1** | **+19.6 pts** |

- **QD vs 贪心(等预算 24 evals）**：0.600 − 0.579 = **+2.14 pts**，即在相同评估预算下多解出 **6 道题**。

## 核心问题验证

| 问题 | 结论 | 证据 |
|------|------|------|
| **Q1** QD 是否产生行为探索？ | **True** | K=4 臂 `n_occupied = 2 > 1`（占据 2 个行为描述符格），而贪心 K=1 仅占 1 格 |
| **Q2** 等预算下 QD 是否优于贪心？ | **True** | K=4 best `0.600` > K=1 best `0.579`，二者均用 24 次昂贵评估 |

`cross_cell = 1`：QD 发生过 1 次**跨行为格的改进迁移**——将一个行为格中探索到的改进迁移到当前精英，这正是 QD 在等预算下超越纯贪心的机制来源。

## 搜索动态

- **K=1 贪心**：单点深挖，曲线呈“长平台 + 偶发突破”——在 0.564 处停滞约 5 轮后于后期跳至 0.579（峰值 eval 20）。典型的局部最优困境。
- **K=4 QD**：在 eval 1 即触达高分格 0.600，随后在 0.52–0.59 区间跨多个行为格持续探索。贪心用满 24 evals 也未够到 QD 早期即达的高分。

```
            0.40        0.50        0.60
baseline ●  ========                       0.404
K=1 贪心  >                > 0.579          单格深挖，长平台
K=4 QD   *         * 0.600                  早达高分格 + 多格探索
```

## 前置可靠性检查（全量前已通过）

- **descriptor 探针**：8 题 baseline 产出 6/16 个不同行为格（cells `{0,4,6,7,12,13}`），描述符在该模型上**有分辨率、未塌缩** → QD 不会退化为贪心（区别于此前 Qwen3 塌缩失败模式）。
- **baseline 落点**：0.404，既非地板亦非天花板，留有充分可改进空间，使方法差异可测量。
- **工程可信度**：14,229 次 rollout 中仅 165 次触发 30/min 限流（429），无致命失败、无限流污染。

## Token 消耗（本次，不含 key）

| 类别 | 调用数 | prompt | completion | total |
|------|--------|--------|------------|-------|
| rollout（评估） | 14,229 | 33.72M | 17.17M | 50.90M |
| analyst（反思变异） | 359 | 7.32M | 0.26M | 7.58M |
| ranking | 53 | 0.55M | 0.01M | 0.56M |
| **合计** | **14,641** | **41.59M** | **17.44M** | **59.03M** |

## 复现信息

| 项 | 值 |
|----|----|
| Release | `fullrun-v4` · `skillopt-fullrun-15f1de3.zip` |
| zip sha256 | `38f9bf7dbc55e65c0a281e39587ca0192ba6044308f4c5fc0af4393626e062cb` |
| 启动命令 | `python scripts/run_experiment.py --full --tag venus-qwen35` |
| backend | endpoint `<venus llmproxy · 内部地址已脱敏>`，target/optimizer = `qwen3.5-397b-a17b` |
| plan | mode=full, n=280, eval_budget=24, k=4, workers=8, max_tokens=4096 |
| 产物 | `runs/full-venus-qwen35/summary.json` |
| 回传包 | `returned-venus-qwen35.zip`（321 MB），sha256 `013dec3859452cb938a449c6ee4278e791a3d5694b305e8fe3e81299504c4751` |

## 备注

- 巡检中途按“已判题数”估算的 K=4 峰值 0.611 为近似；**权威值以 summary.json 为准 = 0.600**（harness 将该批中 ~5 个 TIMEOUT 计为失败、按满 280 计分；实为同样 168 个解出：168/275≈0.611 vs 168/280=0.600）。
- n_occupied=2 属温和探索（descriptor 上限可达 6 格）。若需更强探索证据，可提高 `--eval-budget` 或增大 K 复跑。
