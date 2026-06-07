# T006 总结
- 做了什么: 建立去重 + 缓存 + 成本计数的零 API 合同。
- 结果: smoke 验证昂贵评估只对去重代表/cache miss 计数，cheap/expensive 分开记录。
- 关键决策: 先按 `(cell, epsilon radius)` 做 v0 去重，保留 probe_score 最高代表。
- 关联实验: `/root/autodl-tmp/skillopt_repro_smoke_20260607`。
- 遗留/后续任务: 真实 selection-set scorer 接入后要把昂贵评估次数写进实验 result。
