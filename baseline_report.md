# SkillOpt SearchQA 复刻基线报告 (Phase 1)

> 由用户执行训练后回填。指标 hard=Exact Match (EM)，soft=F1。

## 环境
- 日期：
- Python：
- fork commit（upstream）：
- 后端：OpenAI 直连 / Azure（划掉一项）
- optimizer_model / target_model：gpt-5.5 / gpt-5.5
- seed：42

## 指标
| 项 | 命令 | hard(EM) | soft(F1) | n |
|---|---|---:|---:|---:|
| A*（官方 ckpt 复评） | eval_only --skill ckpt/searchqa/gpt5.5_skill.md | | | 1400 |
| initial.md（弱基线） | eval_only --skill .../skills/initial.md | | | 1400 |
| best_skill.md（训练产物） | train → Final test / eval_only | | | 1400 |
| 论文报告 SearchQA 数字 | （arXiv 2605.23904 结果表） | | — | — |

ε（容差）= ___（建议 0.02–0.03）

## 过程
- 训练步数 / epoch：
- val gate 接受次数 / 总步数：
- skill token 数：initial ___ → best ___
- 墙钟时间 / 估算调用数 / 估算费用：

## 验收（逐条勾选 spec §3）
- [ ] Sanity：A* 与论文数字差距 < ε
- [ ] 训练复现：score(best) ≥ A*−ε 且 ≥ 论文数字−ε
- [ ] 正向提升：score(best) > score(initial.md)
- [ ] 可复现：seed/config/commit/history 已存档

## 结论
