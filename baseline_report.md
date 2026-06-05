# SkillOpt SearchQA 复刻基线报告 (Phase 1)

> 指标 hard=Exact Match (EM)，soft=F1。**注意：本次用 DeepSeek 替代论文的 GPT-5.5（无 GPT-5.5 访问）**，
> 所以这是「DeepSeek vanilla 基线」，**不与论文数字 / 官方 gpt5.5 ckpt 直接可比**——但完全满足"端到端跑通 + 作为 Phase-2 相对提升基线"的目的。

## 环境
- 日期：2026-06-04
- Python：3.13.6（venv）
- fork commit（upstream microsoft/SkillOpt）：`ee9931e`（2026-06-03）
- 后端：**DeepSeek**（`https://api.deepseek.com`，`openai_compatible`；需打 `patches/deepseek-backend-adapter.patch`）
- optimizer / target：`deepseek-chat` / `deepseek-chat`（reasoning_effort 关闭）
- seed：42 ｜ 超参：官方默认（epochs=4, batch=40, train=400, edit_budget=4 cosine, minibatch=8, slow_update+meta_skill 开, gate=hard）

## 指标（test = 1400）
| 项 | hard(EM) | soft(F1) | n |
|---|---:|---:|---:|
| initial.md（弱基线，S₀） | 0.7471 | — | 1400 |
| **best_skill.md（训练产物）** | **0.8036** | 0.8689 | 1400 |
| 提升 Δ | **+0.0564** | — | — |
| （val/selection：initial 0.7200 → best 0.7900） | | | 200 |
| 官方 gpt5.5 ckpt 复评 (A*) | 未跑（DeepSeek 下不可比，跳过） | — | — |
| 论文 SearchQA 数字 | GPT-5.5 口径，与 DeepSeek 不可比 | — | — |

## 过程
- steps=40，**accept=4（全在 epoch 1）/ reject=36 / skip=0**；best 在 **step 5** 达到 val=0.79 后进入平台期（epoch 2–4 候选均被 gate 拒）。
- skill 文档体量：**107 → 12,352 字符**（种子→训练后）。
- 墙钟：**2444s（≈40.7 min）** ｜ 调用：**12,866** ｜ tokens：**46,945,117**（prompt 45,996,900 / completion 948,217）。
- 估算花费（deepseek-chat / V4 Flash，$0.14/M in、$0.28/M out，未计缓存折扣）：
  - 输入 45.997M × $0.14 = **$6.44**；输出 0.948M × $0.28 = **$0.27** → **≈ $6.71（≈¥48）**。缓存命中会更低。

## 验收（对照 spec §3，按 DeepSeek 口径调整）
- [x] **端到端跑通**（本阶段首要目标）：rollout→reflect→gate→eval 全通，无集成错误。
- [x] **正向提升**：best > initial（test 0.8036 > 0.7471，+5.6 pts；val 0.79 > 0.72）。趋势与论文一致（训练技能文档显著提升 QA）。
- [x] **可复现**：seed=42；`config.json`/`history.json`/`best_skill.md` 已存档（见 `results/`），fork commit 已记。
- [n/a] **对齐论文 / ckpt A***：因换用 DeepSeek 而不适用；如需对齐论文需 GPT-5.5 重跑。

## 结论
vanilla SkillOpt 在 DeepSeek 上**端到端跑通**，并复现了其核心效果——把 107 字符的种子技能优化成 12KB 文档，使 SearchQA 测试 EM 从 0.7471 提升到 0.8036（+5.6 分）。**"公司可直接训练"已验证**：一次完整 SearchQA 轮约 47M tokens / ~$6.7 / ~41 min。
同时观察到 vanilla 的**平台期**（epoch 1 后 36 连拒）——正是 Phase-2（PBT / Novelty / Entropy）要打破的贪心局部最优。

## 复现命令（DeepSeek）
```bash
git apply patches/deepseek-backend-adapter.patch          # 在 SkillOpt/ 内
# .env: AZURE_OPENAI_AUTH_MODE=openai_compatible / ENDPOINT=https://api.deepseek.com / API_KEY=...
cd SkillOpt && python scripts/train.py --config configs/searchqa/default.yaml \
  --optimizer_model deepseek-chat --target_model deepseek-chat --reasoning_effort "" \
  --out_root outputs/searchqa_dpsk_run1
```
