<!--
FEEDBACK.template.md — 公司 → 我方 的结构化返回表。
多数字段由 run_experiment.py 自动预填；公司只填「人填」标注处。
front-matter 里的字段就是 ingest_feedback.py 会硬校验的 schema：缺字段 / 不达标 → 整个包被拒收（不入库）。
-->
---
run_id:                       # 必须等于 RUN_REQUEST 的 run_id
code_tag:                     # 必须等于所发 tag；ingest 断言
code_sha_used:                # 实际 checkout 的 40 位
sha_matches_manifest:         # yes/no（RUNBOOK step0 核对）；no → 停手别跑
ran_unmodified_code:          # yes/no；no → 包被拒收
dirty_tree: false             # 必须 false
tree_hash:                    # run_experiment 开跑时算的整树哈希；ingest 比对 tag 树
ran_by:                       # 人填：谁跑的
ran_on:                       # 机器/代理（如 venus-llmproxy / AutoDL-A100）
date:                         # 人填
status:                       # completed | code_defect | aborted
model_snapshot_actual:        # 实际服务的快照标签（若代理只给滚动标签，如实写 + 备注）
target_temperature: 0
inference_seed:
data_split_seed:
full_n_completed:             # 应 = 请求的 full_n
equal_expensive_evals_both_arms:   # 两臂昂贵评估次数（不等 → INVALID）
paired_mcnemar_p:             # 缺 → ingest 失败
discordant_pairs:             # b, c（McNemar 2x2 的不一致对数）
delta_CI:                     # [lo, hi]
wall_time_s:
tokens_total:
bundle_sha256:                # 整个返回 zip 的 sha256（也粘到发件正文里）
artifact_sha256:              # {summary.json: , history.json: , per_item.jsonl: }
---

# FEEDBACK — {{run_id}}

## 1. 每臂结果（harness 自动填）
| arm | baseline | final | Δ | n_occupied | cross_cell_pickup | accept/reject | expensive_evals | cheap_evals | tokens |
|---|---|---|---|---|---|---|---|---|---|
| K1_vanilla |  |  |  | (n/a) | (n/a) |  |  |  |  |
| K_qd |  |  |  |  |  |  |  |  |  |

> equal_expensive_evals 两臂是否相等：______（不等则本次对比 INVALID）。

## 2. 统计（harness 自动填；缺则 ingest 拒收）
- 配对 McNemar p = ______；不一致对数 (b,c) = ______；Δtest 95% CI = ______。
- 预登记证伪条件是否触发：______。

## 3. 异常 / 中断（人填）
- 有没有被 kill / 重启 / 代理报错 / 半写产物？按 PID 杀了吗？smoke 和 full 分端点了吗？

## 4. 代码缺陷 / 改动建议（人填；**不要自己改代码**）
`status=code_defect` 时填：
```
proposed_changes:
  - file:        # 路径
    lines:       # 起止行
    new_snippet: # 你建议的新代码
    rationale:   # 为什么
```
> 我方会读、决定、在我方应用、重打 tag 再发给你。

## 5. go / no-go 意见（人填）
- 这次结果可不可信？建议下一步？

## 6. 红线自检（人填，勾选）
- [ ] 全程没改任何被追踪代码（`ran_unmodified_code=yes`）
- [ ] target temp=0 + 钉死快照 + seed
- [ ] 两臂同 cosine 预算、共享一个昂贵评估计数器
- [ ] 没用 `parent−ε` 之类软化 gate
- [ ] zip 的 sha256 已粘进发件正文
