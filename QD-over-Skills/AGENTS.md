# AGENTS.md — 入口（agent 第一眼读这个）

> ⚠️ **先读 `OPEN_DECISIONS.md`**：有需要**公司侧拍板**的阻塞项（API / 模型访问）。未决前**只做不花钱的本地工作**（读源码、写 `qd/`、T001 回归测试、smoke test），不要跑昂贵付费实验。

你正在参与 **QD-over-Skills** 项目。开工前按顺序读：

1. `OPEN_DECISIONS.md` — 阻塞项（先看，尤其 API）。
2. `BRIEF.md` — 我们在 SkillOpt 之上做什么、红线、成功判据。
3. `PROJECT_MANAGEMENT.md` — 怎么协作/维护（文件系统式；**§3 是 session 开工协议**）。
4. `.tasks/INDEX.md` — 当前看板：哪条任务在做、依赖是否就绪。
5. 活跃任务的 `spec.md` + `status.md`（尤其 status 的「下一步」）。

形式定义 / 算法 / 命题与证明见 `方案与数学推导.md`（SPEC）。

## 不可逾越的红线（详见 BRIEF §4）

- **纯 API、无 GPU**：不写本地模型 serving / `torch.cuda` 代码；target 与 optimizer 都走 API，config 钉死带日期的模型快照版本。
- **$K=1$ 必须精确退化为 SkillOpt**（一条回归测试，命题 3.6）。
- **格内严格 `>` gate**，平局拒（命题 3.4/3.5）。
- **descriptor 只从轨迹 τ（+ 可选 logprobs）算，绝不从 skill 文字算**（template collapse）。
- **每次与 SkillOpt 对比都在「同等昂贵评估次数」下**（命题 3.9）。

## 现状与下一步

- **T000（复现 SkillOpt）已完成**：用 DeepSeek 在 SearchQA 上跑通，观察到**贪心平台期**（4 次 accept 后 36 连拒）。详见 `baseline_report.md` / `results/` / `.tasks/INDEX.md`。
- **下一步（不依赖 API、可立刻做）**：深读 `SkillOpt/` 源码坐实实现 → 做 **T001（K=1 回归测试）**、**T002（descriptor v0）**。
- 注意：SearchQA 饱和，平台期分不清「局部最优 vs 天花板」；**真正的楔子（T003）改在 SpreadsheetBench 上做**（见 INDEX）。

## 前提

你应已读过 SkillOpt（arXiv 2605.23904）；SkillOpt 代码与本地 fork：`SkillOpt/`（已打 `patches/deepseek-backend-adapter.patch`）。
