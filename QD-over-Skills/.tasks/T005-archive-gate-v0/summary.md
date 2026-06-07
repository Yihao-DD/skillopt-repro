# T005 总结
- 做了什么: `Archive` 支持 K>1 格内 gate，同时保持 K=1 与 SkillOpt 逐步等价。
- 结果: K=1 旧测试 + K>1 新 smoke 全绿；验证命题 3.4/3.5 的本地语义。
- 关键决策: K>1 每格采用 `current==best` elite 语义；epoch 级 slow-update 分叉仍不进入本地 archive。
- 关联实验: `/root/autodl-tmp/skillopt_repro_smoke_20260607`。
- 遗留/后续任务: 接入真实 loop 后需记录 rejected buffer 与 parent cell provenance。
