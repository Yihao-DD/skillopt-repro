# ADR-0007 — 拒绝条件化变异（RCV：拒绝账本 + 瞄准着采注入 + 投机预检开关）

- 状态: Accepted（设计经 operator brainstorm 定稿 2026-06-12）
- 关联: 填 T004「瞄准着采」实现槽位；ADR-0001（K=1 红线不动）；ADR-0006（descriptor 轴语义用于 AIM 文本化）；`qd/loop.py`、`qd/adapter_skillopt.py`、fork `reflect`（第 3 个 fork commit）。

## 背景
绝大多数 candidate edits 被严格 `>` gate 拒绝，而**每次拒绝都已支付一次全额昂贵 rollout**（N 题 × target LLM）。被拒候选携带四层信息——patch 方向、Δscore（坡度）、每题对错翻转（分坐标的"梯度分量"，ground truth）、descriptor 格（行为移没移）——目前**全部丢弃**：`adapter.propose` = 对当前 skill 单纯 reflect，完全不知道历史上哪些方向已失败。文本空间离散无梯度算子，唯一能消费「(方向,结果) 对集合」并产出新方向的估计器是 LLM 本身（in-context）。

实证痛点：DeepSeek 验证（N=20）K=1 仅 9 evals 即耗尽不同候选（optimizer 反复重提相似方向）；venus 全量 QD 探索薄（n_occupied=2/16）。OPRO（按分排序历史）与 ProTeGi（文本梯度）证明此类信号有效；我们的信号根基更硬（每题翻转是真实测试结果，非 LLM 自述）。

## 决定
1. **新模块 `qd/ledger.py`**（零 API 纯函数）：`LedgerEntry`（step/action/parent_cell/cell/b/score/parent_score/n_edits/edits 摘要/parent_hash/cand_hash/task_flips 可选/lesson 可选）+ `RejectionLedger`（append-only；`render(char_budget, top_m)` **确定性**输出：最近 m 条 + 最好 accept + 最有信息 reject，按分升序（OPRO），超预算从最旧裁并折叠成计数行）。
2. **loop 集成**：`run_search(..., use_ledger=False, pre_check=None)` 默认全关；**k==1 强制关**（红线 C0：K=1 逐步 == SkillOpt，39 测试不许动）。开启时每次 `archive.update` 后 append；`ledger` 仅在非 None 时作为 kwarg 传 `producer.propose`（现有 fake/测试零回归）。`ProposedCandidate` 增加 `patch` 字段（账本需记录"试过什么编辑"；现 patch 在 apply 后即丢）。
3. **投机预检**（独立开关，默认关）：插槽在 `deduplicate_by_behavior` 之后、昂贵 score 之前（与 dedup 同类：花钱前的便宜过滤器）。`pre_check(pc, ledger) -> bool`，False 则跳过昂贵评估。**四护栏**：① fail-open（预检报错→照常评估）；② 不许全跳（一步内全 SKIP 时强制放行一个，防 stall 计数耗尽导致等预算花不满）；③ 保守契约（prompt 要求指名匹配的具体失败条目才许 SKIP）；④ 全量记录 `precheck_skips` 进 `SearchResult`/summary.json（事后可离线补评校准误杀率）。
4. **adapter**：`SkillOptProducer.propose(ledger=)` 构造 `extra_context` 两节——**AIM**（用 ADR-0006 轴语义把 `target_cell` 文本化："瞄准更高操作密度/中等复杂度"，顺手完成 T004）+ **AVOID**（渲染账本；用 rollout `_cache` diff parent vs 被拒候选的每题正误 → 翻转明细，**零额外 LLM 调用零额外 rollout**）。
5. ~~fork 第 3 commit：`reflect` 加 `extra_context` 参数~~ **作废（2026-06-12 实现时发现）**：上游 `reflect` 已有透传通道 `step_buffer_context`，文档原文 = "Unified summary of previous steps (failure patterns + rejected edits)"，注入为 `## Previous Steps in This Epoch`——语义与 AVOID 完全一致（上游为自家 step-buffer 动量设计；我们受控对比 slow_update/meta=OFF，该通道空闲无碰撞）。**零 fork 改动，fork 保持 `0948d2d`。**
6. **实验面**：`run_experiment.py` 增第三臂 `--rcv`（K=4+账本）；`--rcv-precheck`、`--rcv-distill`（B-flag：每次拒绝一次便宜调用蒸馏一行教训存 `entry.lesson`，render 优先用、恒附证据行）各自独立开关，默认关。

## 理由
- **归因干净**：搜索机器（gate/预算/dedup/rank_and_select）一字不动，只动"问 LLM 什么"。三臂消融 greedy / QD-plain / QD+RCV 中前两臂 venus 数据已有，增量成本 ≈ 一臂。
- **等预算语义不变**：被预检滤掉的候选不碰 counter，stall-tolerant 循环继续提案至预算花满——同样的昂贵评估数花在更有希望的候选上。
- **主主张零风险化**：唯一可能主动伤害搜索的机制（预检误杀）被隔离成开关；核心主张只压在条件化上。

## 影响 / 风险（诚实边界，预先declare）
- RCV 可能无效甚至有害（上下文膨胀干扰 reflect）→ 三臂结构保证负结果同样干净可报。
- 若探索薄根因是模型行为同质性，账本救不了 `n_occupied` → 照实报 ledger 利用率。
- 报告口径：QD+RCV vs greedy 的增益 = QD 机制 + RCV 之和；单独 RCV-on-greedy（2×2 完整消融）已明确不做（operator 决策），列为 limitation/future work。

## 验证计划（自费 DeepSeek，公司 API 只做最终确认）
- T1 烟测 ~$1：preflight 2 题 + 账本开，extra_context 流通、reflect 输出可解析。
- T2 对抗性小跑 ~$5-10：N=20/budget12 —— **QD 已知最不利设定**（贪心 0.65 > QD 0.50），看 RCV 能否缩差 + 候选耗尽是否缓解。
- T3 全量三臂 ~$40-60：DeepSeek N=280/24 —— 双模型证据 + N=20负→N=280正翻转解剖（同模型双规模隔离规模效应）+ RCV 全量增量。
- T4 多 seed 误差棒 ~$100-150（最后跑，覆盖最终方法组合）。
