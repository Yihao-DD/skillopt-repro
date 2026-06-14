# QD-over-SkillOpt — 审阅者问题逐条回答（实验协议 / 等价性 / 预算 / 证据 / 统计）

> 面向外部审阅 agent 的操作级答复。一切均以**代码与磁盘实物为依据**（file:line 引用 + verbatim），不是叙述性声明。
> 准备本答复时我们做了一次完整的代码审计，**发现了 3 个我们之前没主动披露的红线/缺口问题**，全部如实写在 §0，不藏。
> 基准事实快照：working tree 未 commit；121 zero-API 测试通过；唯一一次"公平付费对照"= `runs/full-adaptive-s1fast/`（1 seed，n=24 提速版，2026-06-13 22:09Z 完成）。

---

## §0 最重要：本次审计发现的 3 个问题（直接影响你的判断）

你的核心担忧（K=1 等价性、QD 隐性 advantage、descriptor 是否只切噪声、lineage、test 泄漏）非常精准。诚实地说，审计中我们**自己撞到了三处问题**，必须先讲：

### 问题 A —【红线，HIGH】K=1 漏掉了原文的 `merge_patches`（Aggregate）阶段
原文 SkillOpt 每步是 `apply(rank(**merge**(failure_patches, success_patches)))`：merge 是一次**独立的 LLM 调用**，把失败/成功补丁层次化地协调成一个连贯 edit 集（`SkillOpt/skillopt/engine/trainer.py:1122-1130`）。
我们的 K=1 `propose` **没有调用 `merge_patches`**，而是把每个 minibatch 补丁的 edits 直接**扁平拼接**（`qd/adapter_skillopt.py:172-176`，已亲自核对）：
```python
edits = []
for p in patches or []:
    if p and isinstance(p.get("patch"), dict):
        edits.extend(p["patch"].get("edits", []))
return {"edits": edits, ...}     # 然后才 rank_and_select 截断到 edit_budget
```
→ 同一份 rollout 下，原文产 `apply(rank(merge(...)))`，我们产 `apply(rank(concat(...)))`，**候选技能不同**。现有等价性测试只验证了 gate/决策规则的等价（给定 (skill, score) 流），**没有验证生成路径复现原文**，所以这个缺口测试抓不到。
**影响**：K=1 ≠ 原文 SkillOpt 的"逐字"，差在候选生成。是否实质改变结果**未测**。这是我们要修/或显式标注的第一优先级。

### 问题 B —【归因，HIGH，仅 K>1 多 epoch】slow/meta/rejected-buffer 在 K>1 是**全局跨格池化**
- rejected buffer：每个 epoch **一个** buffer，被该 epoch 内**所有 cell** 的 propose 共享（`qd/loop.py:328` 创建，`:395-400` 所有 cell 追加，`:363` 所有 cell 读取）。
- slow lesson：每个 epoch 边界**单次全局** prev-vs-best 比较产出一条 guidance，**广播注入所有 occupied elite**（`qd/loop.py:440-449`）。这是我们刻意做的"缺口1"，为对齐原文"slow=全局领域知识"语义——但在 K>1 下它就成了跨格信息聚合。
- meta skill：**单个全局字符串** `active_meta`，喂给所有 cell 的 propose（`qd/loop.py:316, 453-454, 343`）。
**影响**：在 `num_epochs>1`（我们真跑用 4）时，K>1 **不止是 MAP-Elites**，它额外获得了跨 cell 的失败/成功经验聚合。**你担心的"全局经验池 advantage"确实存在。** 任何 K>1 vs K=1 的增益在多 epoch 下都被这个混淆污染，不能干净归因到 archive。
**注**：K=1 只有一个 cell，这三者都**严格退化**为原文单技能语义（`qd/loop.py:439,453` 受 `num_epochs>1` 守卫，单 cell 下"跨格"为空操作）——所以问题 B 只伤 K>1 的归因，不伤 K=1 的等价。

### 问题 C —【descriptor，GAP】没有任何"random/score-correlated descriptor"消融，complexity 轴与分数的相关性从未测
descriptor **不泄漏**分数（已 trace，见 Q4）。但"archive 散开 ≠ QD 有效"——我们**没有 negative control**（随机 descriptor 把同一批候选乱分格，看 QD 动力学是否还赢），也**没测过 axis0(complexity=代码长度+控制流) 是否其实是质量的单调代理**。更糟：我们自己的离线探针 `DESCRIPTOR-REBIN-probe.json` 在每个 cohort 的判语都是"**diversity is genuinely thin**"——即"散开"很大程度只是把窄带重新归一化填满格子。这是当前**最大的未证明点**，与你的判断完全一致。

> 这三条不是给你"挖好的坑"，而是我们认为你**必须**拿到才能判断方向的事实。下面逐条详答。

---

## §Q1 当前最终实验协议（操作级）

**任务**：SkillOpt = 迭代优化**一个**自然语言 skill 文档，去 condition 一个 target LLM 解 SpreadsheetBench 代码题；优化器 LLM 通过 reflect/merge/rank/slow/meta 编辑该文档。QD-over-SkillOpt = 在其上套 MAP-Elites archive。

**两臂唯一**结构差异**意图**是 archive（K=1 单格=原文；K>1 16 格+UCB 选父）。但实测代码路径差异不止一处（见 Q2 表）。

**三集使用**（忠于原文 Eq 2/3，`docs/FAITHFUL-REPRO-plan.md §1`）：
- **D_tr (gen_items)** → propose/reflect 的 rollout 来源（生成候选）。
- **D_sel (sel_items)** → score（验证门）+ probe（descriptor）的 rollout 来源。
- **D_test** → 只在最后对"单个最好技能"评一次，不参与搜索/选择。
- 代码：`qd/adapter_skillopt.py:76-92`（gen/sel 分离），`score`/`probe` 用 sel（`:102-121`），`propose`/`slow` 用 gen（`:158,190`）。

**关键设置与默认值**（`qd/loop.py` / `scripts/run_experiment.py`，逐条核对）：
| 项 | 值 | 出处 |
|---|---|---|
| num_epochs | 真跑用 **4**（CLI 默认 1） | `run_experiment.py:71`；s1fast plan `num_epochs:4` |
| rollout batch（候选/步 cps） | K=1:1 / K>1:k=4 | `loop.py:286` |
| reflection minibatch | M=8（原文）；slow/meta 样本 slow_n=**20** | `reflect.py`；`adapter.py:85` |
| edit budget（"文本学习率"） | cosine **4→2** | `run_experiment.py:281`；`loop.py:289` |
| K / grid | K=4；2 维(complexity×op_density)×4 bins = **16 格** | `loop.py:287,303` |
| warmup_evals（自适应binning校准点数） | `eval_budget//3`，上限 cap 到一个 epoch | `loop.py:307,310` |
| scheduler | edit-budget 用 cosine（硬编码）；UCB 选父用 `choose_parent_cell` | `loop.py:289,356` |
| teacher refinement | **无**（SkillOpt 无此项；不适用） | — |
| slow update | 原文 §3.6，**force-accept**（无门），注入受保护字段 | `loop.py:439-449`；`slow_update.py` |
| meta skill | 原文 §3.6，仅改 prompt context，不改 skill 文档 | `loop.py:453-454`；`meta_skill.py` |
| rejected buffer | epoch-local，两臂默认开 | `loop.py:328,349` |
| max_tokens / workers | 4096 / 8 | `run_experiment.py:65,64` |
| eval_budget（每臂昂贵评估） | **24**（s1fast；提速值，非 plateau 调出） | s1fast plan `eval_budget:24` |

**每步调哪个模型**（`qd/adapter_skillopt.py:45-67`，`azure_openai.py`）：
- **target model**（`TARGET_DEPLOYMENT`，默认 `deepseek-chat`，**frozen: temp=0, seed=42**）→ rollout（解题→生成代码），喂 score/probe。
- **optimizer model**（`OPTIMIZER_DEPLOYMENT`，默认 `deepseek-chat`，**diverse: temp=0.8**）→ reflect/analyst/rank/slow/meta。
- 默认两者**同一个 `deepseek-chat`**，仅靠"角色温度/seed"区分（同权重，不同解码）；可由 `.env` 的 `TARGET_MODEL`/`OPTIMIZER_MODEL` 拆成两个模型。
- frozen 配置在 `run_experiment.py:225-227` 一次性设好（解决了早先"target temp>0 → 目标非确定"的隐患）。

**harness**：纯 Python 进程（`scripts/run_experiment.py`），**不是** direct-chat / Codex / Claude-Code harness；DeepSeek 走 openai-compatible HTTP（`.env`）。

**benchmark**：SpreadsheetBench（真实 Excel 操作题，硬准确率 0/1）。选它因为 SkillOpt 原文就在它上面报告（`docs/FAITHFUL-REPRO-plan.md §1` Table 3），可对齐。

---

## §Q2 K=1 ≡ 原文 SkillOpt 等价性表

原文循环是**单体** `ReflACTTrainer.train()`（`trainer.py`，~2083 行）。我们**没调用它**，而是在 `qd/loop.py:run_search` 重建编排、逐叶复用 fork helper。所以"复用 fork helper"在**叶子层**成立，在**组合层**是手工重搭——而且漏了一个阶段（问题 A）。

| 组件 | 原文 `[trainer.py]` | 我们 K=1 `[adapter/loop]` | 差异 |
|---|---|---|---|
| train/sel/test split | rollout=train / gate=valid_seen / report=valid_unseen | gen=D_tr / score+probe=D_sel / test 单评 | 意图一致；原文从 dataloader 派生，我们传显式 list |
| rollout batch | `adapter.rollout(train_env,...,use_eval_feedback=True)` `:1031` | `adapter.rollout(gen_items,...)` 缓存(skill,split) `adapter.py:94-100` | **同一叶子调用**；但我们**未传 `use_eval_feedback=True`**（THREAT-2，低） |
| reflection minibatch | `run_minibatch_reflect` M=8 | 同（经同一 `adapter.reflect`）`adapter.py:170` | **identical** |
| failure/success analyst | `reflect.py:534-558` | 同（reflect 内） | **identical — 复用 fork** |
| **merge_failure/success/final** | `merge_patches(...)` 独立 LLM 调用 `:1122-1130` | **无**——扁平拼接 `adapter.py:172-176` | **DIVERGENCE（问题 A，HIGH）** |
| ranking | `rank_and_select(merged, max_edits, meta_skill_context)` `:1176` | `rank_and_select(skill, **concat**, max_edits)` `loop.py:178` | 同叶子，但输入是未 merge 的池 + **未传 meta_skill_context**（THREAT-3，中） |
| 文本学习率 | `build_scheduler(cosine,4,2)` cosine `:741` | 同 helper，cosine 公式逐位一致 `scheduler.py:77-82` | 同；total_steps 视域不同（原文=epoch×steps，我们=eval_budget//cps） |
| strict-`>` gate, ties-reject | `evaluate_gate` `:121-124`（tie→reject `:141`） | `Archive.update` strict `>` else reject `archive.py:72-85` | **identical 决策**；`test_k1_reduces_to_skillopt.py:89-99` 逐位证过（含两个 tie） |
| rejected buffer | epoch-local，每步 append，render 进 `step_buffer_context` `:954,1422,442` | epoch-local `RejectionLedger`，append，faithful 模式只 `ledger.render()` `adapter.py:150-154` | **语义等价**；renderer 是**重写**（中文头/OPRO 升序/折叠，无 `failure_patterns`）→ THREAT-4（低，仅文本不同字节） |
| slow update | `run_slow_update`→受保护字段，force-accept 进 current+best `:1749` | 同 helper + `archive.force_set` `loop.py:439-449` | **同 helper/同 force-accept/同字段**；K>1 注入所有 elite（问题 B） |
| meta skill | `run_meta_skill`→仅 prompt context，不改 skill `:1886` | 同 helper，threaded 进 propose `loop.py:453-454` | **同 helper**；我们只注入 propose，未注入 ranking（部分面） |
| skill artifact selection | best=最高分 accepted step | `Archive.global_best=max(score,-step)` `archive.py:124` | K=1 单 cell 下 identical；K>1 是全格 argmax（= QD 的加法） |

**三红线确认：**
- **(i) K=1 仅多了 archive？** → **NO（PARTIAL）**：gate/rollout/reflect/rank/slow/meta 叶子等价，但**merge 阶段被静默删除**（问题 A）+ 2 个小漂移（use_eval_feedback、meta→ranking）。"archive 是唯一加法"对**决策规则**成立，对**候选生成路径**不成立。
- **(ii) K=1 的 buffer/slow/meta 语义与原文一致？** → **PARTIAL**：faithful 模式 `rcv=False` 确实**只 plain-render，不调 AIM/flips/RCV**（`adapter.py:161-162` 已核对）；slow/meta 是 fork 原函数零改动；唯 buffer renderer 是语义等价的重写（THREAT-4）。
- **(iii) 共享额外全局状态？** → **K=1 无**（单 cell，slow/meta 受 epoch>1 守卫且单格退化）；**K>1 有**（问题 B：buffer/slow/meta 全局跨格池化）。

---

## §Q3 等预算账本（磁盘实物，非估算）

你担心 QD 在隐处多花预算（warmup、更多 parent、更多 selection、更多缓存查询、更多失败分析）。我们**数了磁盘上每个 rollout 目录**（`runs/full-adaptive-s1fast/<arm>/<tag>/<skill_hash>/predictions/<id>/`），这是 target-model 真实 task-solve 的 ground truth：

| 臂 | gen(propose) 技能/题数 | sel(probe∪score) 技能/题数 | slow 技能/题数 | **target task-solves 合计** |
|---|---|---|---|---|
| baseline | 0 / 0 | 1 / 24 | 0 / 0 | 24 |
| **K=1 greedy** | 7 / 168 | 23 / 552 | 6 / 120 | **840** |
| **K=4 QD** | 5 / 120 | 26 / 624 | 5 / 100 | **844** |
| test_eval | 0 / 0 | 3 / 72 | 0 / 0 | 72 |

**结论：K=1=840 vs K=4=844，差 0.5%——目标模型计算实质相等。**
- **昂贵评估（= sel 评分 = expensive_evals）**：K=1=23、K=4=24（capped at eval_budget=24）→ **selection 查询等量**。两臂"最好技能"都是对各自 ~24 个**被评分**候选取 argmax（同等阶数），**无 multiple-comparison 不对称**。
- **probe 不制造预算优势**：probe 与 score **共享 sel rollout 缓存**（同 `(skill_hash,"sel")` key，`adapter.py:96-100`，已核对）。K>1 的 60 个 proposal 经缓存+dedup 塌成 **26 个 distinct skill-hash**，K>1 比 K=1 多 +3 个 sel-rollout、却少 −2 个 gen-rollout（其 parent 是重复的 cell elite），净持平。
- **warmup 校准花 0 额外 rollout**：复用已评分候选的 b 点（`loop.py:296-302,408-409`），与上面 840≈844 持平一致。
- optimizer-model 调用（reflect/rank/slow/meta）：token 摘要把它们**跨臂合并**报告（global `TokenTracker`，`azure_openai.py:180`），**per-arm optimizer 调用数未单独记录（GAP）**；但主导成本（target rollout）已逐臂相等。
- 总 token 7.82M（跨所有臂合计，`summary.json`）。

---

## §Q4 行为描述子定义 + 泄漏检查 + 消融缺口

**定义**（`qd/descriptor.py`，纯静态分析**生成的代码文本**，非 skill 文本、非分数）：
- 原始特征 `code_features(code)`（`:48-57`）：lines、uses_pandas、n_ctrl(=#for+#if)、n_ops(spreadsheet 操作调用 `.iloc/.loc/read_excel/.groupby/...`)。
- φ 5 维（`:64-78`）：code_len=lines/117、uses_pandas、ctrl_density=(for+if)/24、op_density=(ops/line)/0.20、iter_depth=n_turns/5（refs 来自 558 真实记录，ADR-0006）。
- **投影到 2 轴**（`:90-103`）：**axis0 complexity = mean(code_len, ctrl_density)**；**axis1 op_density**。（uses_pandas、iter_depth 算了但**投影时丢弃**。）
- cell = complexity_bin×4 + op_density_bin。

**泄漏检查（你最关心）→ 明确无泄漏。** trace 了 descriptor 的每个输入：`descriptor(trajs)`→`project(mu(trajs))`，`phi` 只读 `traj["code"]` 与 `traj.get("n_turns")`（`:70-71`）。production 端 `probe()` 喂的 traj 是 `{"code":<predictions/<id>/code.py>, "n_turns":int}`（`adapter.py:108-121`，已核对）——**结果里的 `hard`/`soft`/正确性字段没放进 traj**。cell 与 score 作为**独立参数**进 `archive.update(skill, score, cell=cell)`（`loop.py:345,389`）。**descriptor 不见分数，分数不改 cell。**

**落格时机**：**descriptive（评估前、生成后）**——propose→apply→probe(候选代码)→descriptor→cell，**之后**才 score（`loop.py:177-191`）。有一个 soft `target_cell` 提示喂给 optimizer（AIM），但**实际落格按生成代码重算**，可能偏离（计为 cross_cell）。

**CellGrid 自适应分位**（红线修复）：`uniform()`（空 edges）= 原 fixed `cell_of` **逐位一致**（`:154-160`，`test_cell_grid.py:18-22` 证）；`calibrate(points)` 取每轴 3 个经验分位切点（`:141-152`），**per-seed/per-run**（非全局/非 per-benchmark），warmup≥`eval_budget//3` 个点后**一次性 frozen**，re-bin archive。

**消融清单（诚实）：**
- ✅ 有：替代 descriptor 占用率对比（D0 live / D1 12维手工 / D2 TF-IDF 嵌入，离线缓存）`tools/descriptor_rebin_probe.py`→ 三者占用率相近（~12-14/16）且每 cohort 判语 **"diversity is genuinely thin"**；binning 方案消融（native/quantile/CVT）`adaptive_binning_probe.py`。
- ❌ **NOT IMPLEMENTED**：**random/placebo descriptor 控制**（证明 QD 动力学胜过随机分格）；**score-correlated descriptor / axis-vs-score 相关性**（complexity 轴是否质量代理，**从未测**，GAP）；trajectory-vs-skill-text descriptor 定量对比；1D/3D/nbins 维度扫描；**在 run_search 里换 descriptor 的端到端付费消融**（现有全是离线 re-bin 缓存代码）。
- **判断**：泄漏排除；"只切噪声"**未排除**（无 random control + complexity 轴相关性未测 + 自家探针倾向"多样性稀薄"）。**这是 §0 问题 C。**

---

## §Q5 Archive 动态 / lineage 日志 —— 诚实清单（绝大多数 NOT LOGGED）

`summary.json` 的 `k4.history` 每步只存 4 元组 `(epoch, action, score, candidate_cell)`。`LedgerEntry`（`qd/ledger.py`）在**内存**算了几乎全部你要的，但 `rcv=False` 跑（s1fast 就是）**不序列化**。

| 你要的证据 | 磁盘状态 | 说明 |
|---|---|---|
| 每步 parent cell | **NOT LOGGED** | 内存有 `LedgerEntry.parent_cell`，未落盘 |
| parent 历史 sel/test/train 分 | **PARTIAL/NOT** | 内存有 parent_score(仅 sel)，未落盘；test/train parent 分从未算 |
| 候选 cell | **EXISTS** | history 4 元组 field[3] |
| 是否替换 elite | **NOT LOGGED** | 只有 accept/reject，未区分"新格 vs 替换占用格" |
| 是否成 global-best | **NOT LOGGED（可重构）** | history 跑 running-max 可推 |
| UCB 值/visit/reward | **NOT LOGGED** | `cell_visits` 维护了但未落盘 |
| 占用率随时间 | **NOT LOGGED（仅最终）** | 仅最终 n_occupied=6 |
| per-cell elite lineage | **NOT LOGGED** | 仅最终 elite 文本，无产生步/父 |
| global-best 父系 | **NOT LOGGED** | parent_hash→cand_hash 链内存有，丢弃 |
| "greedy 会拒但 QD 留→后成 global best" 事件 | **NOT LOGGED** | 仅最终整数 `cross_cell=8`，无逐事件、无与"成 global best"的链接 |

**能否事后重构踏脚石？→ 弱，且无法证 lineage。** history 只够重构"running-max 何时出现新 best"和"哪些 cell 收过 accept"，**重构不出父→子链**（无 parent 链接、无"greedy 会拒"判定所需的父子分数链）。
**而且关键：s1fast 里 K=4 的 global best 0.667 出现在 epoch 1 第 3 个候选（cell 9），此后再没被超过**——它是**第一个 4 候选批次里就找到的**，**不是**经长链踏脚石爬上来的。所以即便慷慨重构，这一跑也**给不出"踏脚石→后续突破"叙事**。

---

## §Q6 slow/meta/buffer × archive 交互规则

见 §0 问题 B。精确 scope（verbatim 见 `qd/loop.py`）：
- **rejected buffer**：epoch-local，但 epoch 内**跨所有 cell 共享一个**（`:328` 建、`:395` 所有 cell append、`:363` 所有 cell read）→ K>1 = **全局(跨格)池**。
- **slow update**：单次全局 prev-vs-best 比较（`:440`）→ **广播注入所有 occupied elite**（`:442-449`，force-accept）。
- **meta skill**：单个全局 `active_meta`（`:316,453-454`）→ 喂所有 cell propose。
- 一个 cell 的失败**会**经共享 buffer 影响别的 cell 的后续 edit；success 经 meta 跨 cell 合并。
- **→ K>1 在多 epoch 下是"MAP-Elites + 全局经验聚合"，不是纯 archive。你的担忧成立。**
- **K=1**：单 cell，三者严格退化为原文单技能语义（`:439,453` 受 `num_epochs>1` 守卫；单格下"跨格"为空）。

---

## §Q7 当前公平实验的 split manifest + benchmark

- **benchmark**：SpreadsheetBench。
- **canonical split**（`SkillOpt/data/spreadsheetbench_split/`，**零重叠已验证**）：train=80(D_tr) / val=40(D_sel) / test=280(D_test)。
- **s1fast 实跑用了 `--n 24` 子集**：gen=train[:24]、gate=val[:24]、test 评 24（`test_eval_n=24`）。完整 task-id manifest 在 `runs/full-adaptive-s1fast/summary.json` 的 `gen_tasks`/`gate_tasks`/`test_tasks`。
- split **固定**、**跨 seed 不变**、**所有方法同 split**（同一 run 内两臂共享）。
- **determinism**：target temp=0+seed=42（`run_experiment.py:225-227`）→ 目标确定（modulo API 抖动）；evaluator 是硬准确率比对，确定。
- **同技能重评方差**：**未测（GAP）**——temp=0+seed 下应≈0，但没正式量化。
- **泄漏风险**：splits 零 id 重叠已验；**但"同 workbook 不同 task 的近重复跨 split"未显式检查（GAP）**。
- **"plateau 预算"诚实说明**：s1fast 的 eval_budget=24 是**为提速选的，不是看 greedy 曲线调出的 plateau 预算**——所以**无 stopping-rule 偏置**，但也**还不是**计划里要的"greedy 会 plateau 的预算"（那是后续全量跑的事）。

---

## §Q8 统计计划 + raw table

**已实现并单测**（`tools/analyze_returned_stats.py`，`qd/tests/test_paired_stats.py`）：
- **精确 McNemar**（双侧，discordant 对）`mcnemar_exact`，主显著性检验。
- **seeded paired bootstrap CI**（默认 1e4 重采样，seed 42，95%）`paired_bootstrap_ci`。
- **多 seed pooling 已实现** `pooled_mcnemar`（跨 seed 汇总 b/c 再一次精确 McNemar）。
- endpoint = **per-item 0/1 正确性**，按 task id 在两臂交集配对；判 "SIGNIFICANT" 仅当 `p<0.05 且 CI 下界>0`。
- 伴随 `analyze_selection_generalization.py`：split-half 选择泛化复盘（selection_mean / holdout_mean / gap=winner's-curse 税 / stability），量化"报告的 best 有多少 survive 出选择集"。

**GAP**：上述 harness **尚未在本跑上运行**——它要 `{id,correct}` 文件，数据在 `sel/<hash>/results.jsonl`（字段 `id`,`hard`）但**没导出成那个形状**；且**只有 1 seed**，pooling 路径未用。

**Raw table（s1fast，1 seed）：**
| 臂 | best(gate/val) | n_occupied | cross_cell | expensive_evals | n_proposed | **test(held-out)** |
|---|---|---|---|---|---|---|
| baseline | 0.333 | — | — | — | — | **0.458** |
| **K=1 greedy** | **0.625** | 1 | 0 | 23 | 0 | **0.542** |
| **K=4 QD** | **0.667** | 6 | 8 | 24 | 60 | **0.417** |

test_eval_n=24。verdict：`q1_qd_explores=true`、`q2_payoff_at_equal_budget=true`(在 val)、`q2_test_holdout=false`。
**诚实读法**：val 上 QD +0.042（=**24 题里 1 题**）；**held-out test 上 QD 反输 greedy −0.125（且低于 baseline 0.458）**。1 seed + 1 题级 val 边际，**任何显著性检验都过不了**（参 `test_paired_stats.py:33-38`：280 题 +6 才 p≈0.18）。**纯方向信号，不显著。**
- 预定 endpoint：**held-out test 分**（"按 selection 选 best 后只评一次 test"）；**无中途停止**；多 benchmark 时做多重比较校正；最小有意义效应 size 预登记为 **+0~3pts**（`docs/FAITHFUL-REPRO-plan.md §6`）。

---

## §Q9 旧结果原始摘要（哪些 failure mode 已被证伪 / 哪些只是叙述归因）

权威细节见 `docs/QD-GAIN-investigation.md` + `docs/FAITHFUL-REPRO-plan.md §2`。
- **ensemble/路由 5-fold CV**（`tools/router_kfold_probe.py`）：细描述 kNN 路由单切分 +5.3pts（132-test）是**幸运切分**；5 折 CV 大样本 **+0.01±0.08**（有折 −0.12）→ **ensemble/路由路无稳健增益（已证伪）**。
- **in-sample headroom**（`headroom_probe.py`）：互补 headroom 巨大（+10~25，2800/2850 对技能互补）；**but** 粗 type-router 样本外无增益（`competence_headroom_probe.py`，132-test −0.03）→ **in-sample headroom 是选择性海市蜃楼**。
- **早期合并集"QD +12.5"**（gate=40，DeepSeek）/ **"+4.8" pooled p=9.6e-3**（gate=80）：**不可信**——greedy 阉割了 slow/meta(−22.5)+rejected buffer(−4.6) + gate==生成集放大选择税（利好 QD）+ 无一跑是原文逐字。**这是"评估口径污染正结果"的已证伪 failure mode。**
- **qwen3.5/venus "+2.1"**（公司）：完整条件存档 `docs/RESULTS-venus-qwen35.md`；同样在阉割基线下，不作数。
- **archive 塌缩**：历史每次 QD 跑 archive 因 fixed [0,1] binning 塌成 2-4/16 → K>1 退化"近 greedy+更差 gate"→ **"QD 输"被 binning 污染（已定位为 binning 假象，`descriptor_rebin_probe.py`：native 4/16 → min-max 13/16）**。
- **忠实化但未修 binning 的结果**：无（我们是先忠实化 + 同期修 binning，第一次合在一起跑就是 s1fast）。
- **修 binning 后 pilot 中间结果**：就是 s1fast（§Q8）——archive 真散开(6 格)了，但 1-seed test 上 QD 反输。

---

## §Q10 实际 skill/edit 样例 —— cell 是否语义不同？

**好消息**：skill 文本**已持久化**（`k{1,4}/best_skill.md`、`k4/elite_cell{0,4,7,9,12,13}.md`）。
**坏消息（诚实）**：cell 大多**不语义独立**，两个甚至字节相同：
- `diff` 实测：**`k4/best_skill.md` 与 `k4/elite_cell4.md`、`k4/elite_cell12.md` 三者字节相同**——三个不同 archive cell 装**同一份 skill 文本**。
- 原因：descriptor 按**生成代码行为**分格（非 skill 文本，Q4）→ 同一 skill prompt 在不同候选代码下落不同格。**cell 身份 ≠ skill 里的不同 procedural 策略；cell 4/12 正好反证。**
- cell 0：最小（只系统角色 + 共享 SLOW_UPDATE 块）。cell 4/12/best：加标准 preamble。**cell 7/9/13 是仅有的弱区分**：cell7=多"Python 内逐行逻辑/网格查找"、cell9=openpyxl 防御性属性、cell13=日期/lookup 变体——但都是**在共享底座 + 同一 meta 块上加一节**，paraphrase-plus-one-section，不是独立推导的策略。
- **持久化缺口**：决定 cell 的**生成代码**只存在 `sel/<hash>/predictions/<id>/code.py`，**无 cell/step 标签**；且**只有 global-best 三技能(baseline/k1/k4)上过 test**，非 best 的 cell elite 0/7/9/13 **从没在 test 上评过**，样本外价值未测。
- **判断**：持久化的 artifacts 对"cell 语义独立"给**弱/混合**支持（6 格里 ~3 格有真 procedural twist，2 格字节相同）——与"该 model/benchmark 上 descriptor 行为分辨率稀薄"的长期担忧一致。

---

## §Q11 关键伪代码

**K=1（greedy，`qd/loop.py:336-354` 内联）：**
```
for epoch in 0..E-1:
  epoch_start = archive.best_skill
  buffer = fresh RejectionLedger()          # epoch-local
  while counter.expensive_evals < epoch_target:
    edit_budget = cosine.step()
    parent = archive.best_skill              # 单 cell：parent==best==current
    patch  = producer.propose(parent, ledger=buffer, meta=active_meta)   # ⚠ 无 merge_patches（问题A）
    sel    = rank_and_select(parent, patch, max_edits=edit_budget)
    cand   = apply(parent, sel)              # K=1: 不 probe，b=(0,0) cell=0
    score  = producer.score(cand)            # EXPENSIVE, D_sel, 计数
    upd    = archive.update(cand, score, cell=0)   # strict-> ties-reject
    buffer.append(step, upd.action, score, parent_score, ...)
  # epoch 边界（仅 E>1）：
  guidance = producer.slow_update(epoch_start, archive.best_skill)   # force-accept
  archive.force_set(0, apply_slow(elite, guidance), elite.score)
  active_meta = producer.meta_update(epoch_start, archive.best_skill, active_meta)
```
**K>1（QD，`:355-422`）：**
```
parent_cell = argmax_c [ elite(c).score + 0.1*sqrt(ln T / visits(c)) ]   # UCB, novelty≡0
visits[parent_cell]++ ; parent = elite(parent_cell).skill
proposals = [ propose(parent, target_cell=parent_cell, ledger=buffer, meta=active_meta) for _ in range(k) ]
for p in proposals:                      # 每个候选：
  b = descriptor(producer.probe(p.skill))    # PROBE rollout(D_sel)→代码→行为 b（与 score 共享缓存）
  p.cell = grid.cell_of(b)
survivors = dedup_by_behavior(proposals, eps)    # 同 cell 去重，省预算
for bc in survivors:
  if counter.expensive_evals >= epoch_target: break    # 永不超等预算
  score = producer.score(bc.skill)         # EXPENSIVE, D_sel, 计数
  upd   = archive.update(bc.skill, score, cell=bc.cell)   # per-cell strict->
  if upd.action=="accept" and bc.cell != bc.parent_cell: cross_cell++
  buffer.append(...)                       # 全局跨格 buffer（问题B）
  if adaptive and not calibrated: warmup_bs.append(b)
if adaptive and not calibrated and evals>=warmup_target:
  grid = CellGrid.calibrate(warmup_bs); archive.replace_elites(re-bin); calibrated=True   # 0 额外评估
# epoch 边界 slow/meta：guidance 广播注入所有 occupied elite（问题B）
```
- **UCB**：`predicted_gain + β·√(ln t / n) + γ·novelty`，β=γ=0.1，**novelty 硬编码 0**（`scheduler.py:51-83`）→ novelty 项当前失效。
- **cell 替换 / gate**：strict `>` ties-reject（`archive.py:72`）。
- **best 选择**：`global_best=max(score,-step)`（`archive.py:124`，对 archive elites 即 D_sel 分，非 test）。
- **cache key**：rollout 缓存 `(skill_hash, tag∈{gen,sel,slow})`（`adapter.py:96`）；eval 缓存 `skill_hash`（`budget.py:64`）；**均 per-arm**（两臂各自 producer/counter，`run_experiment.py:263-282`）。
- **warmup 校准**：`CellGrid.calibrate`，复用已评分候选 b（0 额外评估）。

---

## §Q12 材料包

你列的包，对照现状：
- ✅ 现成：`protocol`/`equivalence`/`descriptors`/`stats_plan`/`old_results` = **本文档 §Q1/Q2/Q4/Q8/Q9**；`splits` = `summary.json` 的 task-id 列表；`budget_ledger` = §Q3 磁盘表；`skills/` = `runs/full-adaptive-s1fast/k{1,4}/*.md`（含 cell elites）；`configs` = `summary.json.plan`。
- ⚠️ **需新生成**（都可做，多为零 API）：`results_by_seed.csv`（现 1 seed）、`archive_events.csv` + `candidate_lineage.csv`（**当前 NOT LOGGED**，要么解析 `LedgerEntry` 加落盘再重跑、要么从 `--rcv` 跑导出）、`logs/{accepted,rejected}_edits.jsonl`（同上）。
- 若你要，我可以：(1) 跑零 API 脚本把 `sel/<hash>/results.jsonl` 导成 `{id,correct}` 喂 McNemar；(2) 给 `run_search` 加 `events.jsonl` lineage 落盘后重跑一个 seed；(3) 跑 axis-vs-score Spearman + random-descriptor control（零 API，读缓存）。

---

## §现在在跑什么 / 状态 / 给你的直接判断

**在跑什么**：唯一一次"公平付费 search-dynamics 对照"= `runs/full-adaptive-s1fast/`（**已完成**，非在跑）。它是**第一次** archive 真展开（n_occupied 2→6）后的 faithful K=1 vs K=4 对照，1 seed，n=24 提速版。全量 N=80/40 版本（tag `adaptive-s1`）曾启动但因 DeepSeek 吞吐太慢被杀，**未完成**。当前**没有**后台任务在跑。

**对你 5 个判断标准的直接回答：**
1. **K=1 是否真等价原文** → 基本等价（gate/rollout/reflect/rank/slow/meta 叶子逐位），**但发现 merge_patches 阶段缺失（问题A）+ 2 小漂移**；slow/meta/buffer 在 K=1 严格退化。**红线有一处实质破口，需修或显式标注。**
2. **QD 是否获额外 selection 查询/全局经验池 advantage** → selection 查询**等量**（磁盘 840 vs 844，expensive_evals 24/23）；**但 K>1 多 epoch 下 slow/meta/buffer 全局跨格池化（问题B）= 确有额外经验聚合，非纯 archive**。多 epoch 的 K>1 增益被此混淆。
3. **descriptor 是否泄漏/只切噪声** → **不泄漏**（已 trace，cell 与 score 独立）；**"只切噪声"未排除**——**无 random-descriptor control，complexity 轴 vs 分数相关性从未测（问题C）**，且自家 rebin 探针每 cohort 判"diversity genuinely thin"。
4. **archive lineage 是否真产生踏脚石** → **未记录**，无法从磁盘证 lineage；且 s1fast 的 global best **第一 epoch 就出现**，无长链踏脚石证据。
5. **held-out test 是否只用于最后确认** → **是**，仅 baseline/k1-best/k4-best 三技能各在 test 上评过**一次**；非 best 的 cell elite 从未碰 test。

**我们的判断**：你说"现在最需要的是机制证据，不是更多最终分数"——**完全同意**。在补齐问题 A（merge 等价 or 显式隔离）、问题 B（要么把 slow/meta/buffer 在 K>1 也做成 per-cell 以隔离 archive 效应、要么把它当"QD+经验聚合"显式命名）、问题 C（random-descriptor control + axis-score 相关性，零 API 先做）**之前**，再多花钱跑 seed 2/3 价值有限——会被这三个混淆吃掉归因。建议顺序：先零 API 把 C 和 lineage 落盘补上，再决定要不要修 A/B，最后才是多 seed 付费。
