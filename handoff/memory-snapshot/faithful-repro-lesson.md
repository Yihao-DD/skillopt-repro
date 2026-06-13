---
name: faithful-repro-lesson
description: 忠于原文复现的教训 + 当前重构进度/待办 — 2026-06-13 起 QD-over-SkillOpt 的最新权威状态（覆盖 skillopt-repro-project 中的旧结论）
metadata: 
  node_type: memory
  type: project
  originSessionId: ab7c0e39-798c-4d65-bd7d-6bd2c0ac0325
---

**权威入口文档：`E:\skillopt\docs\FAITHFUL-REPRO-plan.md`**（流程/进度/待办/教训全在那，新会话先读它 + `paper-local/skillopt-paper-fulltext.txt`）。

## 核心教训（用户要求详细记住）
**对照基线必须完全忠于原文，绝不能阉割——否则一切"提升"不可信。** 我们犯的错：当初造 `qd/loop.py` 时没意识到 fork `SkillOpt/skillopt/engine/trainer.py`(`ReflACTTrainer.train()`) 就是原文完整实现（三集分离+slow/meta+rejected buffer+epoch+gate），造了简化版**绕过它**，引入三重偏差全部同向高估 QD：① **合并集**(gate==生成集，原文 train 生成/val gate 分离)放大选择税而 QD 抗选择税；② **阉割 slow/meta**(原文 Table 3 在 SSB 贡献 **+22.5**)；③ **阉割 rejected buffer**(贡献 **+4.6**)。结果之前所有 gate=40/80/120 的「QD 赢 +12.5/+4.8」**对原文完全不可信**(greedy 被砍 ~27pts 组件 + 评估口径利好 QD)。可信的只是「QD archive 机制 > 单点贪心机制」(同简化 harness 公平消融)。

衍生教训：(a) 架构关键事实查原文/代码逐字，别凭记忆——我**两次搞错** gate=40 vs 80 哪个是原文，最终靠 Eq 2/3 定案：**gate=selection(val=40)，train(80)=生成集 C(D_tr)，test=报告**；(b) 大重构先读透再估工期(A 改 trainer 我先估半天实则 1-2 天，改推 B)；(c) 越忠于原文 QD 优势越可能缩小(预测 +0~3/不显著)——无论结果诚实测量都有产出。

## 决策：B 方案
qd/loop.py 补齐原文缺的组件(复用 fork helper run_slow_update/format_meta_skill_context/replace_slow_update_field)，**只在 archive 一维扩展，两臂其余逐字对称**(防"为赢堆 buff")。完全忠于原文配置 = `python scripts/run_experiment.py --full --gen-split train --gate-split val --num-epochs 4 --seed {1,2,3}`。

## 进度(commit)
三集分离`d1dfae1` / epoch+slow update`0f6a003` / adapter slow_update+--num-epochs`a62c006` / **缺口1 slow lesson 注入所有 occupied elite**`7d1a56b`(非只 best，对齐原文全局领域知识语义) / 权威文档`33668fb`。**105 zero-API tests pass**。

## 待办(新会话从这接，见 doc §5)
1. **缺口3 rejected buffer**(+4.6，优先)：两臂(**含 K=1**)默认开原文 buffer = run_search 维护 ledger + adapter propose 传 `ledger.render`(不含 RCV 的 AIM/flips)。难点：改 K=1 propose 契约传 ledger 但不破 K=1==原文红线(buffer 只改 propose 输入不碰 gate)。原文 buffer = RCV 的「裸基础」(RCV 已盖棺)。
2. **缺口2 meta skill**(+1.8，次要)：两臂都接 fork format_meta_skill_context。
3. **真跑**：AutoDL 重部署(代码全变,重传 qd/+scripts/) + **轮换 DeepSeek key**(多轮暴露) + ~¥300-500(num_epochs=4+slow 比单 epoch 贵 4-5×) + 统计 `tools/analyze_returned_stats.py`(pooled_mcnemar)。

## 已盖棺/已知
RCV(拒绝条件化变异 ADR-0007)：五设定全负，gate=80 与 QD 持平、gate=40 显著差，无正增益 → 论文消融一节。venus 公司 qwen3.5 SSB 正结果(QD 0.600>greedy 0.579)和我们 deepseek 复现都在**合并集口径**(同样不可信于原文)。SearchQA 公司测平局(边界条件)。AutoDL 3080(<autodl-host:port-redacted>)曾用于全量跑，实例可能已关。
见 [[skillopt-repro-project]]（更早阶段背景）、[[overnight-mandate-2026-06-12]]。
