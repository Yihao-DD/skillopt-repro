# PROJECT BRIEF — QD-over-Skills（给 agent 的项目简报）

> 读这份之前你应已读过 **SkillOpt（arXiv 2605.23904）**。**不要重读论文**——默认你已掌握它的方法。本简报只讲：我们在 SkillOpt 之上**建什么、红线是什么、做成什么样算赢**。形式定义与证明见同仓库 `方案与数学推导.md`（下称「SPEC」）。先读本文 → 再读 `PROJECT_MANAGEMENT.md` → 再看 `.tasks/INDEX.md`。

---

## 1. 一句话目标

在 SkillOpt 之上做 **Quality-Diversity（MAP-Elites）搜索**：不再只保留一个 current skill，而是维护一个**按「行为」分格的 skill 档案**，每格保留该格最优；用 **optimizer 的 top-k/p「瞄准着采」**做变异，用**「格内严格 ≻」**做选择。目的：**逃出 SkillOpt 贪心爬山的局部最优，同时不破坏它的稳定性（SkillOpt = 本方法的 $K=1$ 特例）**。**全程纯 API，不用 GPU。**

---

## 2. 从 SkillOpt 到本项目：只改两处（最小心智模型）

SkillOpt = **单点贪心**：一个 current skill + 「候选必须严格超过它」的 gate。我们**只改两处**：

1. **不留一个 current，改留一个档案 `Archive`**：按 **behavior descriptor** 把 skill 分进格子，每格存该格最优 elite。
2. **gate 从「全局」变「格内」**：候选只与**它所属格的 elite** 比，严格更高才收（空格直接收）。

为支撑这两处，再加两个配套：**behavior descriptor**（怎么分格）+ **样本高效评估**（去重 + 自适应 k，让昂贵评估付得起）。

**SkillOpt 其余一切原样复用、不要重写**：rollout、minibatch reflection、bounded edits/textual LR、rejected buffer、epoch-wise slow/meta update + 受保护字段、harness adapter。

---

## 3. 要建的四个组件（→ 模块）

| 组件 | 做什么 | 建议模块 |
|---|---|---|
| **Variation `V`** | 把 archive 各格行为摘要喂给 optimizer，提 $N$ 条 edit：部分改进当前打法、$\ge M$ 条走**与档案不同**的策略；从 top-k/p 采样 | `variation.py`（包一层 SkillOpt 的 optimizer 调用 + 多样化 prompt） |
| **Descriptor `b`** | 从**轨迹 τ**（非文字！）抽行为特征 φ → 投影 g → 落到 cell。先 Tier-A（手设 2–3 轴），后 Tier-B（学出嵌入） | `descriptor.py` |
| **Selection / Archive `U`** | MAP-Elites 档案：cell→elite；**格内严格 ≻** 更新；全局最优 = 各格 elite 最大值 | `archive.py` |
| **Budget `Π`** | 全量评估前**在行为空间去重**；缓存/代理；plateau 触发的**自适应 k**；昂贵/廉价评估计数 | `budget.py` |
| 主循环 | 串起 SPEC §2 的 7 步 | `loop.py` |

---

## 4. 红线（非协商；违反即错）

- [ ] **纯 API、无 GPU**：禁止写本地模型 serving / torch 推理代码。target 与 optimizer 都走 API，**在 config 里钉死带日期的模型快照版本**（保「frozen」诚实）。
- [ ] **$K=1$ 必须精确退化为 SkillOpt**：单格档案 + 格内 gate 必须与 SkillOpt 行为一致——**这是一条回归测试**（对应 SPEC 命题 3.6）。
- [ ] **严格 `>` gate 保留在「每格」内**：永不接受格内下降，平局拒（SPEC 命题 3.4/3.5）。
- [ ] **descriptor 只从轨迹 τ（+ 可选 logprobs）算，绝不从 skill 文字算**（否则 template collapse）。
- [ ] **保留** SkillOpt 的 bounded edits（$L_t$）、rejected buffer、slow/meta + 受保护字段。
- [ ] **昂贵评估 = 在 $D_{sel}$ 上算 $f(s)$**：必须计数；**先在行为空间去重再付费**；**每次与 SkillOpt 的对比都在「同等昂贵评估次数」下进行**（SPEC 命题 3.9）。

---

## 5. 怎样算赢（win conditions）

- **C0 正确性**：$K=1$ 退化结果与 SkillOpt 一致（回归测试通过）。
- **C1 逃逸**：在一个「楔子」任务上（贪心 SkillOpt 会 plateau），本方法的**全局最优持续上升**。
- **C2 同预算胜出**：在 SpreadsheetBench / LiveMath 上、**同等昂贵评估预算**下，优于 **SkillOpt** 且优于 **EvoSkill**。
- **C3 迁移**：档案产出的最优 skill 跨模型 / 跨 harness 迁移 ≥ baseline。

---

## 6. 范围内 / 范围外

**范围内**：fork 并扩展 SkillOpt；上面四个组件；优先把 Phase 0/1 做完（见 `PROJECT_MANAGEMENT.md` 任务分解）。

**范围外（暂不做）**：Tier-C SAE/探针 descriptor（要本地模型，违反纯 API 红线）；本地模型 serving；跨域 skill library；任何模型权重更新；预算调度的 regret/复杂度**证明**（那是面向导师的理论，agent 侧只实现 `Π` 的启发式）。

---

## 7. 起步动作（按顺序）

1. **复现 SkillOpt**：clone `aka.ms/SkillOpt`，在**一个便宜 benchmark** 上跑通并复现分数（建议先挑成本低的，如 LiveMath 或 SpreadsheetBench 小子集）。
2. **建 $K=1$ 回归测试**（任务 T001）：证明「我们的档案在单格时 == SkillOpt」。
3. **Phase 0**（T002/T003）：descriptor v0（从 τ 抽）+ 楔子可行性——**贪心会不会 plateau？瞄准着采能不能产出行为不同的候选？descriptor 能不能把它们分开？** 任一为否 → 廉价止损或转向（见 SPEC 命题 3.8 的依赖 i/ii）。

---

## 8. 名词对齐（glossary）

- **variation / selection**：进化的两半——怎么造新候选 / 留哪个。本项目 variation = 瞄准着采，selection = 格内 gate。
- **cell / niche（格）**：行为空间里的一个单元。**elite**：某格里目前最优的 skill。**archive**：所有格 + 其 elite。
- **descriptor / 行为指纹**：把 skill 映到行为坐标（决定落哪格）。
- **楔子（wedge）**：一个「贪心必卡局部最优、QD 能逃」的任务设定，用来证明探索真有用。
- **expensive eval（昂贵评估）**：$f(s)$ = 在 $D_{sel}$ 上跑一轮 agent。**cheap eval（廉价）**：在 2–3 道 probe 题上跑（只为算指纹/快筛）。
- **equal-budget（同预算）**：对比时双方昂贵评估次数相等。

---

## 9. 参考

- SkillOpt 代码：`https://aka.ms/SkillOpt`（= github.com/microsoft/SkillOpt）。
- 本项目形式 SPEC（定义/算法/证明/分级）：仓库内 `方案与数学推导.md`。
- benchmark：SearchQA（饱和参照）、SpreadsheetBench、LiveMath（敏感主战场）。
- 必打 baseline：SkillOpt（贪心，$K{=}1$）、EvoSkill（Pareto）。
