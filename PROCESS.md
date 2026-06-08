# PROCESS — 仓库管理与「我方出码 / 公司跑全量」协作流程

> 权威关系：本文件是**协作流程**的唯一权威；研究内容的权威仍是 `QD-over-Skills/`（`BRIEF.md` 红线、`方案与数学推导.md` SPEC、`.tasks/INDEX.md` SSOT）。本文件**扩展** `QD-over-Skills/PROJECT_MANAGEMENT.md`（文件系统式 PM），不取代它。
> 立项背景：见 `QD-over-Skills/decisions/ADR-0003`（封存旧仓 + 重组 + 本流程的由来 = 审计报告里的 14 类失败模式）。

---

## 1. 核心原则：非对称双单向通道

公司能跑昂贵实验，但**不能 git push**。整个架构就建立在这个非对称上：

- **代码：只能 我们 → 公司**（经 git tag / release zip，**不可变**）。
- **结果：只能 公司 → 我们**（手递 md + 产物包，我们这边**校验后**才入库）。
- **公司 = 纯执行器**：只跑、不改、不提交、不需要 git 写权限。
- **单一代码权威**：只有一棵被追踪的 git 树（`Yihao-DD/skillopt-repro`），只有**一份** `qd/`。
- **凭据或拒收**：公司没有 git，结果唯一入口是 `scripts/ingest_feedback.py`；不带合法 provenance 的 md 是「待拒的数据」，不是可信的散文。

> **根因修复**：上一轮出事的原因是「公司不能 push，却在本地改了代码 → 两份分叉的 `qd/`、无 provenance、脏树跑 headline」。本流程让公司**结构上无法改代码**（见 §2 红线 + §4 整树哈希）。

---

## 2. 角色与两条单向流

### 角色
- **我方**（用户 + Claude，本地 Windows，有 push 权）= **唯一代码权威**：写 `qd/` + config + scripts、跑预检、打 release tag、写 `RUN_REQUEST`/`RUNBOOK`、收 + 校验 + 入库 feedback、算统计、管全部 git 历史 / ADR / INDEX。
- **公司**（venus.oa.com llmproxy / qwen3-235b、AutoDL）= **纯执行器**：checkout 指定 tag → 跑一条命令 → 手递一个包。**永不改码、永不提交、永不需要 git 写权限**。

### Flow A — 代码：我方 → 公司（单向，每个 tag 不可变）
1. 我方在 feature 分支上提交；`master` 保持干净。公司只能消费**打了 tag 的 release**，不能消费分支 tip 或散文件。
2. 预检 PASS 后，打注解 tag `run/<slug>/vN`，同时钉住 workspace SHA 和 fork SHA；记进 `handoff/RELEASES.md`。
3. 公司经 `git checkout run/<slug>/vN`（只读）或导出 zip 拿到。**交付单元 = 不可变 tag。**

> **红线**：公司**永不**改被追踪文件。`run_experiment.py` 在脏树上拒绝启动（见 §4 整树哈希）。本条是根因的直接结构修复。

### Flow B — 结果：公司 → 我方（单向，手递，绝不走 git）
1. 公司那条命令自动产出一个返回文件夹：`FEEDBACK.md`（预填 provenance + 数字）+ `artifacts/` + `run_provenance.json`，打成带 sha256 的 zip。
2. 公司**人手**邮件/IM/文件发这一个 zip。**这是唯一的 公司→我方 通道。**
3. 我方放进 `feedback/INBOX/`，跑 `ingest_feedback.py` 校验；通过才写 `feedback/RUN-<id>/` + 记 `runs/index.csv`。

### 代码改动 = 描述式 diff（替代本地打补丁）
公司若需要改代码（bug、缺 flag），**不准动代码**：在 `FEEDBACK.md` 的 `proposed_changes` 里写「文件 + 行号区间 + 新片段 + 理由」，置 `status=code_defect`，**停手**。我方读、决定、作为正常 commit 应用、重跑预检、打 `run/<slug>/v(N+1)`、再发。**这个往返延迟是故意的——它正是防分叉的机制。**

---

## 3. 运行生命周期（你的「100/1000 → 确认 work → 给公司跑全量」）

| # | 谁 | 动作 | 产物 |
|---|---|---|---|
| 1 | 我方 | `.tasks/INDEX.md` 认领任务 → IN_PROGRESS；开 feature 分支 | INDEX 行 + 分支 |
| 2 | 我方 | 写/改 `qd/`（fork 改动则提交 fork 分支再 bump submodule 指针）；冻结 `configs/frozen/<model>@<date>.yaml`（快照 + temp:0 + seed + 两臂共享 cosine 4→2） | commits + frozen config |
| 3 | 我方 | 全部提交。`git status --porcelain` 在 workspace **和** fork 上都为空，否则中止 | 干净已提交态 |
| 4 | 我方(CI) | `redline_lint.py`：拒 `parent − ε` 软 gate、`torch.cuda`/本地权重（**注意**：descriptor 文字轴 grep 抓不住，靠 §4 测试，不靠 lint） | redline 扫描通过 |
| 5 | 我方(预检) | `run_experiment.py --config preflight100.yaml --preflight`：~100 题端到端跑**两臂**，共享昂贵评估计数器，baseline 算一次冻死共用 | 预检产物 + provenance |
| 6 | 我方(门) | `preflight_gate.py` 断言**验收清单**(§4)。**任一 FAIL → 任务留 IN_PROGRESS、不打 tag、不交付**。错 descriptor 只烧 ~100 题 | `PREFLIGHT.md` PASS/FAIL |
| 7 | 我方(发布) | PASS 才 `stamp_provenance` + `make_handoff` 组装 `handoff/RUN-<id>/`，记 `RELEASES.md`，打 tag `run/<slug>/v1` | tag + 交付包 |
| 8 | 我方→公司 | 交付 tag（git 只读）或 zip + `RUNBOOK.md`。**唯一的代码出站事件** | 公司手里有 tag/zip |
| 9 | 公司 | checkout / 解压 → 核对本地 SHA == `MANIFEST.txt`，不符则停 → 填 `.env`（唯一碰的东西） | 已核验的冻结 checkout |
| 10 | 公司 | **一条命令** `run_experiment.py --config full280.yaml --full`。harness 再断言 clean-tree + frozen-target + equal-budget；按 PID 杀、smoke/full 分端点、原子写 | `returned/`：FEEDBACK + artifacts |
| 11 | 公司 | 填 `FEEDBACK.md` 少数人填字段（异常、go/no-go、proposed_changes）。出 bug 则 `status=code_defect` + 日志，**不打补丁**。打 zip + sha256 | 完整 FEEDBACK + bundle |
| 12 | 公司→我方 | 手递 zip（邮件/IM/文件）。**唯一的结果入站事件** | 手递包 |
| 13 | 我方(ingest) | `ingest_feedback.py`：schema 校验 + 验 `code_sha` 是已发布祖先 + `ran_unmodified=yes` + `dirty=false` + 含 McNemar/预算字段。REFUSE 则不入库、回报错；PASS 则写 `feedback/RUN-<id>/` | 入库 + `INGEST.md` 判定 |
| 14 | 我方(统计) | 同 280 题配对 McNemar + 不一致对数 + delta CI（3–5 重复）；写 `experiments/EXP-*/result.md`（**预测与实测分列**）；记 `runs/index.csv` | result.md + index 行 |
| 15 | 我方(收尾) | 更新 `summary.md` + INDEX + 一行 CHANGELOG；必要时 ADR；若有 described-diff 则应用并打 v(N+1) | 闭环，下一 tag 排队 |

---

## 4. 预检验收门 —— 「work / 有效 / 可用」的机检定义

`scripts/preflight_gate.py`（**代码里、可 grep，不是文档段落**）。**全部满足才 PASS**；任一 FAIL → 不打 tag、不交付。对缺失符号/字段 **fail-closed**（找不到 = FAIL，绝不跳过）。

- **[C0]** K=1 逐步 == SkillOpt：`test_k1_reduces_to_skillopt.py` **和** `test_k1_generation_path.py`（覆盖 cosine 调度 + `rank_and_select` 生成路径）都绿。
- **[descriptor]** `test_descriptor_validation.py` 过：descriptor **只从轨迹 τ 算**；文字扰动但行为相同的 skill 落同格；**两根轴都非退化**（不许有二值饱和轴）。
- **[QD 真在跑]** 100 子集上 `n_occupied > 1` **且** 跨格 pickup ≥ 1（空格 accept 真触发）。若确实预期 K=1 退化，必须在 `PREFLIGHT.md` 写**显式 WAIVER**，绝不静默放宽。
- **[equal-budget]** 两臂共享**同一个**昂贵评估计数器对象、每步 edit_budget 相同（同 cosine 4→2）。不等 → FAIL。
- **[frozen-target]** config 继承 `configs/frozen/`：temp==0 + seed **真传到模型调用**（不只是数据采样）。**跑两遍 100，分数完全一致**（determinism 检查）。
- **[shared-baseline]** baseline temp=0 算一次、冻成常量、两臂共用。
- **[clean-tree + 整树哈希]** workspace **和** `vendor/SkillOpt` 都 `git status --porcelain` 空；provenance 里嵌**整棵被追踪树的 hash**（不只是 clean 标志），ingest 重算 tag 树哈希、不符则拒——把「改了一行、跑完再 reset」从无法检测变可检测。
- **[provenance]** 每个 `summary.json` 盖：workspace SHA + submodule SHA + descriptor 版本 + 合规 ADR + config/env hash + `dirty=false`。

---

## 5. Provenance 规则（每个数字都可三命令复现）

1. **源头盖章**：`stamp_provenance.py` 在我方预检跑、并在公司侧 `run_experiment.py` 内**重跑**；不写 `run_provenance.json` 就跑不完。
2. **交付单元 = 不可变 tag**：每次发布是 `run/<slug>/vN`，钉 workspace + fork SHA，记 `RELEASES.md`。
3. **整树哈希前置**：开跑前对整棵被追踪树 hash 并嵌入；脏/未追踪树跑不出 headline。
4. **frozen-target by schema**：`configs/frozen/*` 带 temp:0 + 带日期快照 + seed；lint + 盖章都断言 `temperature==0` 且 seed 传到**模型**调用。
5. **equal-budget + 统计 by schema**：门和 ingest 都**要求** `equal_expensive_evals_both_arms` + 配对 McNemar p + 不一致对数 + delta CI；缺或不等 = FAIL / 拒收。
6. **ingest 是信任边界**：唯一结果入口；验 `code_sha` 是已发布 tag 祖先 + `bundle.sha256` 匹配 + `ran_unmodified=yes` + `dirty=false`。
7. **唯一权威实现**：tag 钉一份 `qd/`；`summary.json` 盖 `descriptor_version + complied_ADR`，ingest 检查跑的 descriptor 与它声称实现的 ADR 一致——静默推翻 ADR 会被机检抓住。
8. **唯一结果库**：`runs/index.csv` 按 run_id 一行；任何 headline 三命令复现（查表 → `git checkout <tag>` → `run_experiment.py --config <same>`）。**只由 `ingest_feedback.py` 写，绝不手改。**
9. **证据只追加**：`feedback/RUN-<id>/` 只读、不覆盖；重跑 = 新 tag + 新目录。

---

## 6. 结构性 vs 约定（诚实分级 —— 不要重蹈「信任一个啥也没验的门」）

> 来自对抗复核：很多保障**是约定不是机检**，或绑在**还不存在的代码**上。诚实标注，并对结构防不住的**点名到人**。

### ✅ 真正结构性强制（机检 / fail-closed）
- clean-tree + **整树哈希** → 拒脏树/改后 reset 的 headline。
- frozen-target：temp==0 / 带日期快照 / seed 由 schema 强制；determinism 双跑校验。
- equal-budget + 统计字段：门 + ingest 缺则 FAIL。
- ingest 祖先-SHA + sha256 + `ran_unmodified` 校验。
- descriptor **行为不变性测试** + 运行时 `n_occupied>1`/跨格事实（**这才是 P1 的真守卫，不是 grep**）。
- `redline_lint` 仅管真正可 grep 的：`parent − ε` 软 gate、`torch.cuda`/本地权重。
- 成本**硬停**：`--full` 读 `expensive_eval_budget_per_arm`，超了原子写部分结果 + `status=budget_exceeded` 中止。
- 每侧**一条命令、fail-closed**：`make_handoff` 是唯一能打 tag 的路径（自跑预检+redline+clean-tree，任一 FAIL 拒打）；`ingest` 是唯一能写 index 的路径。
- **给门本身写测试**：用故意造坏的 fixture（塌缩 descriptor / 预算不等 / 脏 provenance / temp=0.7 / 非祖先 SHA），门必须拒。

### ⚠️ 只能靠人 / 点名负责（结构防不住，别假装防住）
- **P8 论文抢跑 / 确认偏误**：写文档在 pipeline 外，无机检。缓解 = 预登记 `falsification_condition` + 有效结果前不定稿；**负责人：我方（统计）+ 导师审稿**。
- **R2 理论过度声称**：在数学文档里，无 CI 可管。ADR 把「heavy-ball 等价」降级为「类比」，但没东西强制它保持降级。**负责人：我方（写 SPEC 的人）**。
- **代理模型漂移**：`@日期` 只是个标签，venus 代理可能在标签后悄悄换权重，**我方无法验证**。→ **必须直接问公司**（见 `OPEN_DECISIONS` BLOCKER-1 Q2）。**负责人：公司侧联系人**。

---

## 7. 红线（继承 `BRIEF.md` §4 + 本流程新增）

- 纯 API、无 GPU；**K=1 必须精确退化为 SkillOpt**；**格内严格 `>` gate，平局拒**（`parent − ε` 软 gate 永久禁止）；**descriptor 只从轨迹 τ 算，绝不从 skill 文字或 fitness 算**；**每次对比同等昂贵评估预算**；**frozen target（带日期快照 + temp 0 + seed）**。
- 新增：**公司只跑不改**；**不从脏/未追踪树跑**；**无 provenance 的结果不入库**。

## 8. 与现有 PM 的关系
- `.tasks/INDEX.md` 仍是任务 SSOT；`decisions/` 仍记 ADR；`experiments/` 归档每次跑。本文件只新增 `handoff/`（出站）、`feedback/`（入站）、`runs/index.csv`（结果库）、`configs/frozen/`、`data/benchmarks/`、`scripts/` 这几个面，并由 `decisions/ADR-0003/0004/0005` 记录决策。

---

## 9. 运行上下文硬约定：`在公司，` 标记（区分我方 / 公司）

> 目的：同一套代码 + agent 可能在**我方**或**公司**侧运行；必须能区分，否则公司侧 agent 又会去改代码（上一轮根因）。

- **触发**：prompt 中**每句**以 `在公司，` 开头 ⇒ 当前是 **公司上下文（company mode）**；无此前缀 ⇒ **我方上下文**。
- **公司模式 = runs-only（硬约束，任何 agent 必须遵守）**：
  - ❌ 绝不改任何被追踪代码；绝不 `commit`/`push`/打 tag；不碰 git 写、不碰我方 `.env`/凭据。
  - ✅ 只能：按 `handoff/RUNBOOK.md` 跑 `run_experiment.py`、看产物、填 `FEEDBACK.md`。
  - 需要改代码 ⇒ 写成 `FEEDBACK.md` 的 described-diff，**停手**，等我方重发 tag。
- **我方模式**：完整权限（写码、提交、打 tag、跑预检）。
- **存疑 / 前缀不一致时 ⇒ 按更受限的公司模式处理**（安全默认）。
- 本条是**硬约定**，同时写在 `QD-over-Skills/AGENTS.md`（每个 agent session 入口第一眼读）。

## 10. benchmark 数据自带（公司零下载零改动）

> 见 `decisions/ADR-0005`。公司机器常对 HuggingFace 不通，所以**数据随 tag 一起带走**：
- 我方用 `tools/materialize_*.py` 一次性物化（**公司永不跑**）。
- 小公开 benchmark：**原始 tarball** 提交进 `data/benchmarks/<bench>/raw/` + split `items.json`；`run_experiment.py` 启动**自动解压**到 gitignored `data_root/`；提取出的 xlsx 不提交（运行时从 committed tarball 确定性重建）。
- 大 / gated benchmark：我方物化后 vendored 进仓或随 release zip。
- 每个 benchmark 在 `data/benchmarks/<bench>/SOURCE.md` 记来源 + 版本 + `sha256`（可重建、可审计）。
- → 公司 `git checkout <tag>` 即拥有全部数据，跑一条命令即可，**无需联网 / 物化 / 改动**。
