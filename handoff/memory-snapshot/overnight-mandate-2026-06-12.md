---
name: overnight-mandate-2026-06-12
description: 2026-06-12/13 凌晨值班授权 — T2 完成后自主判定并直接烧全量，用户 11:00 醒来要现成结果（事后可删）
metadata: 
  node_type: memory
  type: project
  originSessionId: ab7c0e39-798c-4d65-bd7d-6bd2c0ac0325
---

用户 2026-06-12 ~02:00 入睡（~11:00 醒），**全权授权**：T2（bg `ba3kr6e7w`，N=20 三臂 rcv-n20）完成后由我判定——判据 = **机制健康**（账本生长/reflect 可解析/预算花满/RCV≥baseline），**小样本输赢不构成否决**（venus 翻转先例）；放行即直接 `python scripts/run_experiment.py --full --rcv --workers 16 --tag dpsk-rcv-full`（后台，~7-8h，错峰半价，用户已充值明示不省钱）。完成后写好：三臂对比 + Q1/Q2/Q3 + ledger 利用率 + `tools/analyze_returned_stats.py` 配对统计 + 与 venus 对照。并发 16 若 429/超时增多 → 降 8 续跑。**若全量没跑成（用户最不愿见），必须备好后续优化方案**（预检/蒸馏真实现、seed 管道、加厚变异）。见 [[skillopt-repro-project]]。
