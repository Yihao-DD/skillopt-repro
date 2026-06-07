# T007 总结
- 做了什么: 实现 plateau 触发的候选数/novelty 调度与 UCB 式 cell 选择。
- 结果: smoke 验证非平台期偏 exploitation，平台期提升探索强度；cell 选择受 novelty/gamma 控制。
- 关键决策: 该调度仍是启发式，不声称 regret/sample-complexity 已证。
- 关联实验: `/root/autodl-tmp/skillopt_repro_smoke_20260607`。
- 遗留/后续任务: 参数 `window/base_n/plateau_n/gamma` 需要在楔子实验中定档。
