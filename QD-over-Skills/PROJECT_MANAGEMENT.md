# PROJECT MANAGEMENT — QD-over-Skills

> 文件系统式项目管理：**所有跨 session 协调都通过文件**（不同 agent session 之间无共享内存）。任何 session 开工前必须按 §3 的顺序读文件，收工前必须按 §2 更新文件。配套阅读：`BRIEF.md`（做什么）、`方案与数学推导.md`（SPEC，形式定义/证明）。

---

## 1. 目录结构

```
repo/
  BRIEF.md                     # 做什么（先读）
  PROJECT_MANAGEMENT.md        # 本文件：怎么协作/维护
  方案与数学推导.md             # SPEC：定义/算法/证明/诚实分级
  AGENTS.md                    # 极短入口：指向 BRIEF + 本文件 + .tasks/INDEX.md
  CHANGELOG.md                 # 每次合并/重要变更一行
  GLOSSARY.md                  # 名词（与 BRIEF §8 同步）

  .tasks/
    INDEX.md                   # 看板：所有任务 + 状态 + 依赖（唯一事实来源 SSOT）
    T000-reproduce-skillopt/
      spec.md                  # 目标/范围/验收标准
      status.md                # 当前状态/最后更新/blocker/下一步
      summary.md               # 完成时写：做了什么/结果/决策/遗留
    T001-.../ ...

  decisions/                   # ADR：非平凡设计决策（含理由），跨 session 留底
    ADR-0001-descriptor-axes.md

  experiments/                 # 实验运行 + 结果，与任务 ID 绑定
    EXP-2026MMDD-<slug>/
      config.yaml              # 钉死的模型快照版本/种子/超参/split_seed
      result.md                # 指标/曲线/昂贵评估计数/结论
      logs/

  src/                         # 代码 = fork SkillOpt + 我们的扩展（见 BRIEF §3）
```

**SSOT 规则**：`.tasks/INDEX.md` 是任务状态的唯一权威来源；任何状态变化先改 INDEX，再改对应 `status.md`。冲突以 INDEX 为准。

---

## 2. 任务生命周期

状态机：`TODO → IN_PROGRESS → (BLOCKED) → REVIEW → DONE`（另有 `DROPPED`）。

- **认领**：把 INDEX 该行改 `IN_PROGRESS` + 写上日期；在该任务 `status.md` 写「本次目标 + 下一步」。
- **进行中**：每个 session 收工时更新 `status.md`（当前进度、blocker、**下一步具体动作**——给下一个 session 的接力棒）。
- **受阻**：标 `BLOCKED`，在 `status.md` 写明阻塞原因 + 依赖哪个任务/决策。
- **完成**：写 `summary.md`（见 §4 模板）、把 INDEX 改 `DONE`、在 `CHANGELOG.md` 加一行；若产生设计决策 → 写 ADR；若有实验 → 归档到 `experiments/` 并在 summary 链接。
- **决策门（GATE）**：见 §5；门是特殊任务，结论写进 ADR，并据此增/删后续任务。

---

## 3. Session 开工协议（跨 session 通信合同）

每个新 session **按此顺序读，再动手**：

1. `BRIEF.md`（目标与红线）。
2. 本文件（协作约定）。
3. `.tasks/INDEX.md`（看板：哪条在做、依赖是否就绪）。
4. 当前活跃任务的 `spec.md` + `status.md`（尤其 status 的「下一步」）。
5. 最近 2–3 个 `summary.md` + 最近 ADR（了解新近结论与已定决策，**避免重复决策**）。
6. 需要形式细节时查 `方案与数学推导.md`。

**禁止**：在不读 INDEX/status 的情况下直接改代码；重新决策已有 ADR 记录的事项（除非显式开 ADR 推翻）。

---

## 4. 模板

**`spec.md`**
```md
# T0XX <slug>
- 目标(一句话):
- 为什么(它解锁什么/对应 BRIEF 哪个组件或 SPEC 哪个命题):
- 范围内:
- 范围外:
- 依赖: [T0..]
- 验收标准(可勾选、可机检):
  - [ ] ...
- 关联: SPEC §.. / BRIEF §..
```

**`status.md`**
```md
# T0XX 状态
- 状态: TODO|IN_PROGRESS|BLOCKED|REVIEW|DONE
- 最后更新: 2026-..  by <session>
- 进度:
- Blocker:
- 下一步(给下个 session 的具体动作):
```

**`summary.md`**（完成时）
```md
# T0XX 总结
- 做了什么:
- 结果(指标/是否过验收): 
- 关键决策(→ ADR-….): 
- 关联实验: experiments/EXP-….
- 遗留/后续任务: 
```

---

## 5. 任务分解（看板初始内容；依赖有序）

> Phase 0 验「值不值得做」，Phase 1 出低风险结果，Phase 2 冲刺。**门**在阶段之间。

**Phase 0 — 验证 payoff 与可行性**
- **T000 复现 SkillOpt**：一个便宜 benchmark 上跑通并复现分数。依赖: 无。验收: 分数对得上、config 钉死版本。
- **T001 $K=1$ 回归测试**：实现档案在单格时 == SkillOpt（对应 SPEC 命题 3.6）。依赖: T000。验收: 单格 run 与 SkillOpt 逐步一致。
- **T002 descriptor v0**：从轨迹 τ 抽 φ + Tier-A 手设 g + cell 分配（**不碰文字**）。依赖: T000。验收: 能对任意 skill 输出稳定的 cell（probe 重采方差小，SPEC 命题 3.2）。
- **T003 楔子 + 逃逸依赖测**：构造/找到「贪心会 plateau」的任务（payoff）；并测「瞄准着采能否产出行为不同候选」「descriptor 能否分开它们」（SPEC 命题 3.8 依赖 i/ii）。依赖: T001, T002。
- **GATE-0**（ADR）：payoff 在不在？变异源够不够？任一为否 → 转向/止损。

**Phase 1 — 低风险结果**
- **T004 瞄准着采变异 `V`**：archive 条件化的多样化 prompt + 采 $N$ 候选。依赖: T002。
- **T005 档案 + 格内 gate `U`**：MAP-Elites 更新 + 全局最优（SPEC 命题 3.4/3.5）。依赖: T001, T002。
- **T006 去重 + 缓存 + 成本计数 `Π`(一)**：全评前行为空间去重；昂贵/廉价评估计数（SPEC 命题 3.9）。依赖: T002, T005。
- **T007 自适应 k 调度 `Π`(二)**：plateau 触发探索（SPEC §3.4 的 UCB 式打分）。依赖: T005, T006。
- **T008 Phase-1 集成实验**：粗 descriptor + 档案 + 格内 gate，在楔子上**同预算**展示「续爬 vs SkillOpt plateau」。依赖: T004–T007。
- **GATE-1**（ADR）：逃逸在同预算下复现了吗？

**Phase 2 — 冲刺**
- **T009 descriptor 验证实验**：造「文字异/行为同」「文字同/行为异」，证行为 descriptor 判对、文字判错（SPEC §3.1 判别性 C）。依赖: T002。
- **T010 Tier-B 学出 descriptor**：在 φ 上做对比/嵌入。依赖: T002, T009。
- **T011 全面对比**：SpreadsheetBench + LiveMath，**同预算**打 SkillOpt + EvoSkill。依赖: T008, T010。
- **T012 迁移实验**：档案产物跨模型/跨 harness（C3）。依赖: T011。
- **T013（理论，导师向，可选）**：调度 `Π` 的 regret/复杂度推导（SPEC §9 待推导）。依赖: T007。

---

## 6. 实验与可复现

- 每个实验一个 `experiments/EXP-<date>-<slug>/`，含 `config.yaml`：**钉死的 API 模型快照版本**（target + optimizer 分别记）、`split_seed`（沿用 SkillOpt 默认）、所有超参、benchmark 子集定义。
- `result.md` 必含：指标、**昂贵评估次数 vs 廉价评估次数**（红线计数）、是否「同预算」对比、结论。
- 结论回流：在对应任务 `summary.md` 链接该 EXP，并在 `CHANGELOG.md` 记一行。
- **「frozen」诚实**：实验在紧时间窗内跑完，config 锁版本；跨窗重跑须新建 EXP 并标注可能的 API 漂移。

---

## 7. 设计决策记录（ADR）

非平凡选择都写一条 `decisions/ADR-XXXX-<slug>.md`：背景 / 选项 / 决定 / 理由 / 影响。典型触发：descriptor 用哪几根轴、去重半径 $\epsilon$、$k$ 调度参数、GATE-0/1 的结论、是否启用 logprobs。**作用：跨 session 不重复争论同一件事。**

---

## 8. 约定（conventions）

- 代码 = **fork SkillOpt 放 `src/`，扩展而非重写**；复用其 rollout/reflection/gate/buffer/slow-meta/adapter。
- **纯 API 红线**：`src/` 不得出现本地模型 serving / GPU 代码（CI/审查时 grep `torch.cuda`、本地 weights 加载即拒）。
- **同预算红线**：实验 harness 内置昂贵评估计数器；对比脚本默认按「相等昂贵评估次数」对齐，否则报错。
- 命名：任务 `T0XX-<slug>`、实验 `EXP-<date>-<slug>`、决策 `ADR-XXXX-<slug>`。
- 提交即更新 `CHANGELOG.md`；状态变更即更新 `INDEX.md` + `status.md`。

---

## 9. 维护节律（cadence）

- **每个 session**：开工读 §3、收工更新 `status.md`（含「下一步」）。
- **每任务关闭**：写 `summary.md`、更新 INDEX、CHANGELOG，必要时 ADR / EXP。
- **每个 GATE**：结论入 ADR，并据此增删后续任务。
- **定期**：核对 INDEX 与各 status 一致;清理 DROPPED;确认 GLOSSARY 与 BRIEF 同步。
```
