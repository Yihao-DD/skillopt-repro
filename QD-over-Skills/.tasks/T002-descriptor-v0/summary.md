# T002 — descriptor v0 总结
- 做了什么: 实现代码级行为 descriptor(`qd/descriptor.py`)：轨迹 τ → φ∈[0,1]^5 → Tier-A 2 轴 g → cell；**不碰 skill 文字**、纯 stdlib / 零 API、确定性。
- 结果(验收): **8 测试 GREEN**。稳定性：probe 重采 b 各轴 std<0.08(命题 3.2)；区分性：best vs initial 落不同 b（库策略轴 0.98 vs 0.84，复杂度轴亦异）。
- 关键发现(→ `ADR-0002`): **result 级字段(n_turns/exec_ok)在 best/initial 上饱和 = 只反映性能 f**；**代码级(pandas/长度/控制流/op)才反映打法**。坐实 descriptor 必须走代码级，并给 SPEC §8「生死手」一个**正面数据点**——SpreadsheetBench 确有可分的多策略空间。
- 关联实验: `results/ssb_dpsk_run1`(τ 来源)。
- 遗留/后续: 仅 2-skill 区分；多候选分格质量 + 楔子逃逸(命题 3.8 i/ii)= **T003**；Tier-B 学嵌入 = T010；轴判别性(抗 template collapse)= T009。迭代深度轴信号弱（n_turns 多为 1）。
