# 忠于原文复现 QD-over-SkillOpt — 流程、进度、待办、教训（权威文档，2026-06-13）

> 新会话冷启动读这一份。它固定：核心教训 / 原文协议 / 我们的偏差史 / 修正进度 / 剩余待办 / 真跑配置 / 预登记预测。

---

## 0. 核心教训（最重要，务必详细记住）

**铁律：对照基线必须完全忠于原文，绝不能阉割。否则一切"提升"都不可信。**

我们犯的错，按因果链：

1. **绕过了 fork 已有的原文完整实现**。fork `SkillOpt/skillopt/engine/trainer.py`（`ReflACTTrainer.train()`, ~1500 行）就是原文 SkillOpt 完整循环（三集分离 + slow/meta + rejected buffer + epoch + gate）。我们当初造 `qd/loop.py` 时**没意识到**这点，造了个简化版绕过它 → 自己引入了一堆偏差。**教训：动手造之前先查 fork 有没有现成的原文实现。**

2. **三重偏差，全部同向高估 QD**：
   - **合并集**：我们 gate==生成集（原文是 train 生成 / val gate 分离）→ 放大选择税，而 QD 抗选择税 → 利好 QD。
   - **阉割 slow/meta**：原文默认开（Table 3：SSB 去掉 slow/meta 77.5→55.0，**−22.5pts**），我们没实现 → greedy 被砍 22 分。
   - **阉割 rejected buffer**：原文标配（Table 3：去掉 −4.6pts），我们只在 RCV 模式传 → greedy 又被砍 4.6 分。
   - 合起来：greedy 被砍 ~27pts 的组件 + 合并集放大 QD → 我们测出 QD 赢 +12.5，**对原文完全不可信**。

3. **评估协议偏差系统性误导**：合并集 + 阉割基线两个 artifact 同向放大 QD 优势。这是整个 skill-optimization 领域的陷阱——**新方法很容易在"自制的弱基线 + 有利评估口径"上看起来赢**。

4. **我两次搞错 split 角色**：先说 gate=40 是原文、又改口 gate=80 是原文，都错。最终靠原文 **Eq 2/3 白纸黑字**定案：gate=**selection(val)**，train 是**生成集** C(D_tr)，test 只报告。**教训：架构关键事实必须查原文/代码逐字，绝不凭记忆或直觉。**

5. **深入调查前的复杂度估计会错**：A 方案（改 trainer）我先估"半天"，深入后发现 1-2 天 + 高风险（1500 行单体、端到端难测）→ 及时改推 B（qd 层补 slow/meta，复用 fork helper）。**教训：大重构先读透再估，发现更贵就及时反馈改方向。**

6. **越忠于原文，QD 优势越可能缩小**（见 §6 预登记预测）。因为之前的大优势部分是 artifact。**这不是坏事**：QD 真有增量 = 经得起忠实化的硬结果；无增量 = "评估协议高估新方法"的方法论警示，同样可发表。诚实测量无论结果都有产出。

**一句话**：我们花了很多轮才认清——之前所有 gate=40/80/120 的"QD 赢"都建立在阉割的 greedy + 有偏的评估口径上。忠于原文是为了得到**能信的**数字，哪怕它更小甚至打平。

---

## 1. 原文协议（基于 fulltext + trainer.py 代码核对）

三集（Eq 2/3, §3.1）：**D_tr 生成候选 C(D_tr) → D_sel 选最优 argmax → D_test 报告**。

| 机制 | 原文 | trainer.py | Table 3 在 SSB 的贡献 |
|---|---|---|---|
| 三集分离 | Eq 2/3 | rollout `split=train` / gate `split="valid_seen"`(:1324) / report test | — |
| 验证门 strict> ties-reject | §3.5 | `evaluate_gate`(:1337) | — |
| **slow update**（跨 epoch 领域 lesson，默认 force-accept 注入 current+best） | §3.6 | `run_slow_update`(:1633) / force-accept(:1755) | **+22.5** |
| **rejected buffer**（epoch 内被拒 edits+score drop → reflect） | §3.5 | `_format_step_buffer`(:442) → `step_buffer_context` | **+4.6** |
| meta skill（optimizer 端编辑经验） | §3.6 | `format_meta_skill_context` | +1.8 |
| edit budget cosine 4→2 | §3.4 | `rank_and_select`(:1176) | — |
| 默认超参 | line 560-567 | 4 epoch / rollout batch 40 / minibatch 8 / slow 20 samples | — |

我们的 split（`SkillOpt/data/spreadsheetbench_split/`，零重叠已验证）：train=80(D_tr) / val=40(D_sel=gate) / test=280(D_test)。

---

## 2. 上次结果可信度判决（已锁定）

- ✅ 可信：「QD archive 机制 > 单点贪心机制」（同简化 harness 公平消融，pooled McNemar 显著）；gate-size 趋势（优势随 gate 增大衰减）。
- ❌ 不可信：「对原文 SkillOpt 提升 X pts」——greedy 阉割了 slow/meta(−22)+rejected buffer(−4.6) + 合并集放大 QD + 无一跑是原文逐字协议。
- 数据存档：`docs/RESULTS-dpsk-3way-3seed.md`(gate=40) / `RESULTS-dpsk-gate80-3seed.md`(gate=80) / `RESULTS-dpsk-rcv-full.md` / `RESULTS-venus-qwen35.md`(公司)。

---

## 3. 决策：B 方案（qd 层补原文组件，复用 fork helper）

A（改 trainer）最忠实但 1-2 天高风险（已否决）。**B：在 qd/loop.py 补齐原文缺的组件，复用 fork 的原文 helper（run_slow_update/format_meta_skill_context/replace_slow_update_field），只在 archive 一个维度扩展，两臂其余完全对称。**

**原则（防止"为赢堆 buff"）**：QD = 原文 + archive 一个维度，其它一切两臂逐字对称。这样归因干净。绝不给 QD 加原文没有的机制。

---

## 4. 修正进度（已完成，commit 索引）

| 项 | commit | 状态 |
|---|---|---|
| 三集分离（adapter gen_items/sel_items；`--gen-split`/`--gate-split`） | `d1dfae1` | ✅ |
| epoch 循环 + slow update force-accept（loop num_epochs；archive force_set/best_cell） | `0f6a003` | ✅ |
| adapter slow_update 包装 fork run_slow_update + `--num-epochs` 接线 | `a62c006` | ✅ |
| **缺口 1**：slow lesson 注入**所有 occupied elite**（非只 best，对齐全局领域知识语义） | `7d1a56b` | ✅ |
| **缺口 3**：epoch-local rejected buffer **两臂默认开**（loop 每 epoch 重置+线程+append；adapter `rcv=False` 原文模式 plain render，`rcv=True` 才 RCV flips/AIM；K=1 inline 保 gate 红线） | 本次(working tree, 待提交) | ✅ |
| **缺口 2**：optimizer meta skill **两臂都接**（loop `active_meta` 每 epoch 边界 `meta_update` 累积+线程；adapter 包装 fork `run_meta_skill`/`format_meta_skill_context`，复用 slow rollout；零 fork 改动） | 本次(working tree, 待提交) | ✅ |
| 本计划文档 | `db5153d`→本次 | ✅ |

当前测试：**115 passed**（zero-API）。缺口 2/3 已在 working tree 完成并通过 code-review（0 CRITICAL/HIGH；2 MEDIUM + 2 LOW 已修），**尚未 commit**（等用户指示）。

---

## 5. 剩余待办（按顺序，新会话从这里接）

### ✅ 缺口 3 + 缺口 2 已完成（本次会话，working tree，115 passed）
- **缺口 3**（rejected buffer 两臂默认开）：epoch-local buffer 在 `qd/loop.py run_search` 每 epoch 重置、线程给两臂 propose（含 K=1，inline 不再走 `produce_and_score_candidate`）、每步 append（accept+reject + 方向 + 分数 delta）。`res.ledger` 仍是 RCV 工件（faithful 模式 None；RCV 跨 epoch 累积）。adapter `rcv=False`=原文模式（`_buffer_context` 只 `ledger.render()`，**不调** AIM/flips）；`rcv=True`=RCV（`_rcv_context`）。红线：K=1 gate 等价不变（buffer 只改 propose 输入）。测试 `test_loop_buffer.py` / `test_adapter_buffer.py`。
- **缺口 2**（optimizer meta skill 两臂都接）：`qd/loop.py` 持 `active_meta`，每 epoch 边界 `producer.meta_update(epoch_start_skill, epoch_best, prev_meta)` 累积、线程给 propose（仅非空时）；**不改 skill 文档**（区别于 slow）。adapter `meta_update` 复用 slow rollout（`_slow_rollout` 缓存共享）+ fork `build_comparison_pairs`/`run_meta_skill`；propose 传 `meta_skill_context=format_meta_skill_context(meta)`（fork reflect 原生支持，**零 fork 改动**）。测试在 `test_loop_slow_meta.py`。
- **L2 修正**（faithful 细节）：epoch 边界先抓 `epoch_best`（slow 注入前）再喂给 slow+meta，对齐 trainer 的 `epoch_last_step_skill`（pre-slow）。
- **已知小偏差**（threats 标注）：`epoch_start_skill`（prev）含上个 epoch 的 slow 注入，而 trainer 的 prev 是 pre-slow last-step —— 与 slow（缺口1）共有的小偏差，未深修。

### 次要简化（threats 标注，可不补）
- minibatch-40 随机采样：原文每 step 采样 40 题 batch，我们用全 gen_items。次要。

### 真跑（**所有缺口已完成 → 现在可跑**）
- **前置**：AutoDL 实例重新部署（代码全变了，重传 qd/ + scripts/）；**旧 DeepSeek key 轮换**（多轮跑暴露过）。
- **配置**：`--full --gen-split train --gate-split val --num-epochs 4 --seed {1,2,3}`（两臂都跑原文完整：三集 + 4 epoch + slow + buffer + meta）。
- **成本**：num_epochs=4 + slow update（每 epoch 额外 2×20 rollout）比单 epoch 贵 ~4-5×，3 seed 估 **~¥300-500**，跑前精算。
- **统计**：`tools/analyze_returned_stats.py`(pooled_mcnemar) + 可选 `analyze_selection_generalization.py`。

---

## 6. 预登记预测（跑前锁定，不许事后挪门柱）

完全忠于原文（三集 + slow + buffer + meta，greedy vs QD+archive）：

| 情形 | 预测 | 概率 |
|---|---|---|
| 中心 | greedy 大幅变强（deepseek ~0.55-0.65）；QD−greedy **+0~+3pts，很可能不显著** | ~50% |
| 悲观 | QD ≈ 持平/不显著 —— 之前优势几乎全是 artifact | ~30% |
| 乐观 | QD 稳定 +2~4pts 显著 —— SSB 真有 off-baseline 更优行为区（gate=80 时 QD best 稳定落 cell 9 暗示） | ~20% |

核心逻辑：越忠于原文 → greedy 越强、过拟合越轻 → QD 正则化红利越小。

---

## 7. 关键文件索引（新会话定位）

- 原文全文：`paper-local/skillopt-paper-fulltext.txt`（Eq 2/3 @310；§3.5 gate @368；§3.6 slow/meta @379；Table 3 @539）。⚠️ paper-local 是 LOCAL-ONLY（`.git/info/exclude`），不 commit。
- fork 原文 trainer：`SkillOpt/skillopt/engine/trainer.py`（gate@1337, slow@1633/1698, force-accept@1755）。
- fork helper：`skillopt/optimizer/slow_update.py`（run_slow_update@309, replace_slow_update_field@80, inject_empty@41）；`meta_skill.py`。
- 我们的 loop：`qd/loop.py`（run_search num_epochs + epoch + slow 注入所有 elite）。
- 我们的 adapter：`qd/adapter_skillopt.py`（gen/sel 分离 + slow_update/apply_slow 包装 fork）。
- archive：`qd/archive.py`（force_set/best_cell）。
- 启动器：`scripts/run_experiment.py`（--gen-split/--gate-split/--num-epochs）。
- 部署工具（不入库，含密码用法）：`tools/_autodl_ssh.py`（exec/put/get/putenv）。
- 测试：`qd/tests/test_loop_slow_meta.py`(epoch+slow)、`test_adapter_split.py`(三集)。
