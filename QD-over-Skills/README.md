# QD-over-Skills — 文档包

本包两类文档：**给导师 / 自己通读的** 和 **给本地 agent 的**。

## 给导师 / 自己通读
- **`方案与数学推导.md`** — 主文档：完整方案 + 数学形式化（定义 / 算法 / 命题与证明 / 诚实分级）。v0.2。
- `研究框架.md` — 早期高层总览，可当导读发给导师。

## 给本地 agent（直接放进项目仓库根目录）
- `OPEN_DECISIONS.md` — **需公司决策的阻塞项（API），agent 先看这个**。
- `AGENTS.md` — 入口：读序 + 红线 + 现状。
- `BRIEF.md` — 做什么、红线、成功判据。
- `PROJECT_MANAGEMENT.md` — 文件系统式项目管理。
- `.tasks/INDEX.md` — 任务看板（**T000 已 DONE**；其余 TODO）。
- `.tasks/T001-k1-regression/` — 首个待做任务的 spec（K=1 回归测试，**不依赖 API**）。

## 现状
- **T000（复现 SkillOpt）已完成**：DeepSeek / SearchQA，观察到贪心平台期（4 accept 后 36 连拒）。
- **主战场 = SpreadsheetBench**（理由见 INDEX 决策记录；SearchQA 饱和，楔子须在此重测）。
- **API 待公司**（见 `OPEN_DECISIONS.md`）。

## 怎么用
1. 把 agent 那几份放进 agent 仓库根目录（与本地 `SkillOpt/` fork 同处）。
2. agent 从 `AGENTS.md` 进；**未决 API 前先做 T001（K=1 回归）+ 深读 `SkillOpt/` 源码**。
3. `研究框架.md` 发导师当总览，细节指向 `方案与数学推导.md`。

> 前提：agent 已读 SkillOpt（arXiv 2605.23904）；本地 fork 在 `SkillOpt/`（已打 `patches/deepseek-backend-adapter.patch`）。
