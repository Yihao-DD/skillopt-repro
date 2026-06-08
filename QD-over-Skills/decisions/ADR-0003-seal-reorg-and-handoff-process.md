# ADR-0003 — 封存旧仓 + 重组 + 「我方出码/公司跑全量」单向协作流程

- 状态: Accepted
- 日期: 2026-06-08
- 关联: `PROCESS.md`（落地）、`ADR-0004`（fork 携带）、`审计报告-公司工作记录.md`（14 类失败模式 = 本决策的动机）、`BRIEF.md §4` 红线、`OPEN_DECISIONS.md` BLOCKER-1。
- 决策人: 用户 + 公司（一致决定封存并重组）。

## 背景
公司用内部 API（venus.oa.com llmproxy / qwen3-235b）推进时出了一连串问题，审计核实根因是**流程管理混乱**：公司机器**不能 git push，却在本地改了代码** → 两份分叉的 `qd/`、descriptor 违反红线（文档长度轴 → 档案塌缩到 1 格，"full QD" 实为 vanilla）、未提交/未追踪、脏树跑 headline、target 不冻结（无 seed、temp 0.7）、无统计、还想软化 gate 制造 accept。

## 决策
1. **封存（封存）**旧仓全部内容到 `_sealed_2026-06-08/`（只读、非权威），并打 `archive/pre-reorg-2026-06-08` tag；旧 headline 数（0.4357 / +0.0893…）在 INDEX 标 **ARCHIVED/不可信**。
2. **重组**为单一权威 git 树，确立**非对称双单向通道**：代码只能 我方→公司（不可变 tag）、结果只能 公司→我方（手递 md + 产物包，ingest 校验后入库）。
3. **公司 = 纯执行器**：只跑、不改、不提交。需要改代码 → 写成 `FEEDBACK.md` 的描述式 diff，由我方应用、重打 tag、再发。
4. **单一 `qd/` 不变量**：只有一份权威实现（仓库内 ADR-0002 合规版）；CI 禁止第二份 `loop.py`/`descriptor.py`；`summary.json` 盖 `descriptor_version + complied_ADR`。
5. **凭据或拒收**：`ingest_feedback.py` 是唯一结果入口；验祖先-SHA + sha256 + `ran_unmodified` + `dirty=false` + 统计/预算字段；不合格拒收。
6. **预检门**（`scripts/preflight_gate.py`）在「我们写完」和「公司花钱」之间：~100 题机检 `n_occupied>1`/跨格/K=1/descriptor 不变性/equal-budget/frozen-target/clean-tree+整树哈希，任一 FAIL 不交付。
7. fork 收编为 `vendor/SkillOpt`（携带策略见 ADR-0004），关掉「代码在 git 外」的洞；openai-compat 修复以**已提交的 fork commit** 形式存在（与我方 `deepseek-backend-adapter.patch` 对账，避免重复 apply）。

## 理由
让每一类审计失败模式**结构上不可能**，而非靠自觉。代码出站不可变 + 结果入站需凭据，正中根因（公司改码 → 分叉）。详细的失败模式→机制映射见 `PROCESS.md §6`。

## 影响
- 公司无须 git 写权限即可贡献结果；我方掌握全部 git 历史与统计。
- 多了 `handoff/`、`feedback/`、`runs/index.csv`、`configs/frozen/`、`scripts/`、`vendor/SkillOpt` 几个面。
- 第一个走新流程的任务 = **按合规 descriptor + frozen target + 同 cosine + 预登记 McNemar 重做 headline**（旧数全部作废）。

## 诚实：本流程**结构上防不住**的（点名到人，不假装防住）
- **论文抢跑 / 确认偏误（P8）**：写文档在 pipeline 外，无机检 → 预登记证伪条件 + 有效结果前不定稿；**负责人：我方统计 + 导师审稿**。
- **理论过度声称（R2，heavy-ball 等价）**：在数学文档里，无 CI → ADR 降级为「类比」，但靠人维持；**负责人：写 SPEC 的人**。
- **代理模型漂移**：`@日期` 只是标签，venus 代理可能悄悄换权重，**我方无法验证** → **必须问公司**（BLOCKER-1 Q2）；**负责人：公司联系人**。
- **公司「改了再 reset」**：靠 `run_experiment.py` 开跑时嵌**整树哈希** + ingest 重算比对（≈10 行）把它从无法检测变可检测；signed-tags / Docker-digest 列为未来加固。

## 备选（已否决）
- 给公司 push 权 / 让公司直接改主仓 → 正是出事根因，否决。
- 单仓但代码/结果不分离 → 无法保证 provenance，否决。
- 软化 gate 制造 accept（审计 R1）→ 红线违规，永久禁止。
