# T004 总结
- 做了什么: 增加 `qd/variation.py`，覆盖 archive 摘要、prompt 条件化、top-k/p 元数据、候选 novelty quota 的本地选择合同。
- 结果: 远程 AutoDL smoke GREEN；全套 `tools/test_materialize_searchqa.py qd/tests/` 为 **29 passed in 0.42s**。
- 关键决策: 不在 smoke 中调用 optimizer API；先锁定 prompt/sampling contract，避免产生付费和随机性。
- 关联实验: `/root/autodl-tmp/skillopt_repro_smoke_20260607`。
- 遗留/后续任务: 真实 optimizer wrapper 与多候选生成接入仍需后续集成。
