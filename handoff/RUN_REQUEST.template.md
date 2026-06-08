<!--
RUN_REQUEST.template.md — 我方 → 公司 的「跑全量」合同。
我方填好后随 tag/zip 一起交付。YAML front-matter 是机器可读的，ingest 会断言公司返回的 FEEDBACK 与此处一致。
没有 preflight_verdict=PASS 的请求无效（=代码没值得花钱的证据）。
-->
---
run_id:                 # RUN-<date>-<slug>，全流程主键
linked_task:            # T0XX（.tasks/INDEX.md）
code_tag:               # run/<slug>/vN（不可变交付单元）
workspace_sha:          # 40 位
submodule_sha:          # vendor/SkillOpt 的 40 位（vendored 则记 fork commit SHA）
model_snapshot:         # 带日期，如 qwen3-235b-a22b-2507-fp8@2026-06-08
target_temperature: 0   # 必须 = 0
inference_seed:         # 传到模型调用（非仅数据采样）
data_split_seed:        # 42
optimizer_model:        # 可与 target 不同；若 temp>0 必须也 seed
benchmark:              # 如 spreadsheetbench
full_n:                 # 280
preflight_n:            # 100（我方已跑）
arms:                   # [K1_vanilla, K_qd]
shared_baseline_arm:    # 哪一臂的冻结 baseline 两臂共用
edit_budget:            # {schedule: cosine, max: 4, min: 2, total_steps: 8}（两臂相同）
expensive_eval_budget_per_arm:   # 来自成本模型；--full 超了硬停
success_criteria:       # C0..C3（见 BRIEF）
statistical_test:       # {name: paired_mcnemar, n: 280, mde: <预登记最小可检测效应>}
falsification_condition: |   # 逐字写死；result.md 须对它做判定
  # 例：合规 descriptor 下若 cross_cell_pickup=0 → QD 主张失败。
preflight_verdict: PASS      # 没有 PASS 本请求无效
acceptance_observed:    # {n_occupied: , cross_cell_pickup: , equal_budget_ok: true}（预检实测）
deliverables_expected:  # [FEEDBACK.md, summary.json, history.json, per_item.jsonl, logs/, run_provenance.json]
hand_delivery_channel:  # email / IM / 文件分享
---

# RUN REQUEST — {{run_id}}

## 1. 要你跑什么（一句话）
按 `code_tag` checkout，跑**两臂全量**（{{full_n}} 题），用冻结 target，照 `RUNBOOK.md` 的一条命令。**不要改任何代码。**

## 2. 我方已做的证据（为什么值得花钱）
- 预检（{{preflight_n}} 题）judgment：**PASS**（见随附 `preflight/PREFLIGHT.md`）。
- 关键实测：`n_occupied={{}}`、`cross_cell_pickup={{}}`、`equal_budget_ok=true`、两跑 determinism 一致。

## 3. 成功判据（这次想验证的）
- C0 K=1==SkillOpt（回归绿）｜C1 楔子上逃逸｜C2 同预算打赢 SkillOpt+EvoSkill｜C3 迁移。
- 本次重点：________；**证伪条件**（见 front-matter）。

## 4. 你要回什么
- 填好的 `FEEDBACK.md`（多数字段 harness 自动填）+ `artifacts/` + `run_provenance.json`，打 zip + sha256，**人手发回**。
- 出 bug 别改码：`status=code_defect` + 日志，描述式 diff 写进 FEEDBACK，停手。

## 5. 红线提醒
target temp=0 + 钉死快照 + seed｜两臂同 cosine 预算｜严格 `>` gate（**不准** `parent−ε`）｜共享一个昂贵评估计数器｜不从脏树跑。
