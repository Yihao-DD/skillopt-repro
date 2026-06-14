# QD-vs-greedy 增益调查 —— 权威结论与下一步(2026-06-13)

> 本轮(深度研究 + 5 个零 API 离线探针 + 机制分析)重构了整个项目的判断。新会话读这份。
> 数据文件:`docs/{DESCRIPTOR-REBIN,HEADROOM,COMPETENCE-HEADROOM,ROUTER-test,ROUTER-KFOLD,ADAPTIVE-BINNING}-probe.json`。

## 0. 核心结论(一句话)

**"QD 赢不了 greedy" 目前是未经证明的** —— 之前所有 "QD 输" 的运行,archive 都因 binning 错位塌成 ~2-4 格,K>1 退化成 "近 greedy + 更差的 gate",**QD 的搜索机制从没被公平运行过**。真正的 QD 命题(archive 作踏脚石 → 爬到更高的**单个**技能)**尚未测试**。

## 1. 关键的框架纠正

之前几轮把 QD 当 **ensemble/selection**(在搜索产出的最终技能里选/路由)。**那不是 SkillOpt 的机制。** SkillOpt = 单文档迭代积累可迁移 guidance;QD 的增益必须来自**搜索动力学**(archive 帮优化器爬得更高),不是事后选择。用缓存的最终技能只能测 ensemble,测不了 search dynamics。

| 框架 | 测了吗 | 结论 |
|---|---|---|
| Ensemble / 路由(选最终技能) | ✅ 充分 | **负**:无稳健增益 |
| **Search dynamics(archive→更高单技能)** | ❌ **从没公平测**(archive 全塌) | **未知** |

## 2. 五个零 API 离线探针的结果

1. **descriptor 重分格**(`descriptor_rebin_probe.py`):2/16 塌缩是 **binning 假象**,不是行为塌缩。同轴同点,native [0,1] 分格 4/16 → min-max 13/16。技能产出**结构各异**的代码(Metric A:~每个技能每题都不同结构,0% 塌缩)。
2. **headroom**(`headroom_probe.py`):in-sample 互补 headroom **巨大**(+10~25pts;2800/2850 对技能互补)。**但**——
3. **competence/out-of-sample**(`competence_headroom_probe.py`):粗 type-router(2 类)样本外 **无增益**(最可信 132-test cohort −0.03)。in-sample headroom 是**选择性海市蜃楼**。
4. **fine router**(`router_test_probe.py`):细描述 kNN 路由单次切分 **+5.3pts**(132-test),看似有救。
5. **k-fold**(`router_kfold_probe.py`):+5 是**幸运切分**。5 折 CV 大样本 **+0.01 ± 0.08**(有折 −0.12)。→ ensemble/路由路**无稳健增益**,互补性本质不可泛化。

## 3. 为什么 greedy 不是无敌的(机制)

SkillOpt greedy = 在带噪声 val 上做**不可逆 strict-`>` 坐标上升**,三个可证次优:
- **val 过拟合棘轮**:只接受 val 严格变好的 edit,永久锁定 → 卡在 val-optimum(< test-optimum)。
- **过不去中性平台**:val 中性但能解锁后续大改进的侧移,被 strict-`>` 拒绝。
- **路径依赖**:第一个 improving edit 锁定 basin。

**QD 的 per-cell gate 严格更宽松**(候选只需赢自己那格)→ **留住 greedy 丢弃的踏脚石** → UCB 从踏脚石继续爬 → 机制上能逃这三个陷阱。**这个机制真实存在,只是从没在非塌缩 archive 上跑过。** 而本会话刚建好的 slow(注入所有 elite)+meta+buffer 正是 "并行专门化 guidance 再蒸馏" 的武器。

⚠️ 诚实保留:k-fold 的 ensemble-负**弱**暗示搜索多样性也可能是噪声;不能据此断定 search dynamics 也无效 —— 必须公平跑一次才知道。

## 4. binning 修复(已建,离线验证)

- **CellGrid**(`qd/descriptor.py`,纯 stdlib,TDD,`test_cell_grid.py` 3 passed):uniform 默认 == 原 `cell_of`(红线);`CellGrid.calibrate(points)` 按搜索分布设 per-axis quantile 切点,frozen。
- **离线验证**(`adaptive_binning_probe.py`):warmup 半数校准 quantile/CVT,held-out 半数分格 **native 2-4/16 → quantile 13-15/16**。实现方案(warmup 校准 + frozen)样本外成立。

## 5. 下一步

1. ✅ **接线 CellGrid 进 run_search 完成**(task #11,TDD,**121 passed**,过 code-review 2 HIGH 已修):K>1 用前 `warmup_evals` 个已评估候选的 b 校准 frozen quantile grid(= 正常步,**不额外花评估 → 等预算红线保住**;warmup 上限 cap 到一个 epoch,在 slow force_set 前完成),校准点 re-bin archive(loop 跟 `elite_b` + 传 `baseline_b`),之后用 calibrated grid。K=1 / adaptive_bins=False 不动(uniform grid == 原 cell_of)。已接 `scripts/run_experiment.py`(K>1 自动 `adaptive_bins=True`)。测试 `test_loop_adaptive_bins.py`、`test_cell_grid.py`。
2. **← 唯一剩下的:第一次公平的 search-dynamics 付费对照**:在**greedy 会 plateau 的预算**(不是 12 evals)下跑 faithful K=1 vs K>1(现在 archive 真能展开),比**单个最好技能的 held-out 分**,几个 seed + 配对统计。**这才第一次真正回答 "QD 能不能赢"。** 前置:AutoDL 重部署 + 轮换 DeepSeek key。
3. 若仍负 → 诚实负结果 + 机制解释(领域 guidance 天花板低);若正 → QD 命题首次被证。

**判定:在第 2 步跑出来前,不下 "QD 没用" 的结论。** 框架之前错了,机制上 greedy 有口子,我们刚把武器和 binning 都备齐。
