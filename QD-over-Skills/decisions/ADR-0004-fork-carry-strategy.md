# ADR-0004 — SkillOpt fork 的携带策略

- 状态: **Accepted — vendored 拷贝**
- 日期: 2026-06-08（确认前提：公司可 `pull` 不可 `push`）
- 关联: `ADR-0003`、`PROCESS.md`、`OPEN_DECISIONS.md` BLOCKER-1。

## 背景
上游 `microsoft/SkillOpt` 的 fork 现为松散目录 `SkillOpt/`：自带 git、只有 `upstream=microsoft` 远程、`azure_openai.py` 改了**未提交**（审计 P7「代码在 git 树外、脏树跑 headline」）。重组要求 fork 进被追踪树，使交付 tag 能同时钉死 workspace + fork 的确切 SHA。

## 决定
**vendored 拷贝**：fork 树直接提交进主仓 `vendor/SkillOpt/`（普通文件，非 submodule），在 `handoff/RELEASES.md` 记对应 upstream commit SHA。

## 理由（公司可 pull 不可 push）
- 公司只需访问**一个**私有仓即可拿到全部代码；submodule 要两个仓 + `--recurse-submodules`（忘了就**静默**拿到空 `vendor/SkillOpt`、跑了空/旧码）。
- 对一个 push-blind、要塞冻结 tag 的下游，**越少活动部件 = 越少静默翻车**（审计核心教训）。
- 唯一代价（手动 re-merge 上游）落在**低频 + 我方机器**一侧——本项目极少 re-merge。
- 两端都靠 `MANIFEST.txt` 的 SHA 断言 + `run_experiment.py` 在 `vendor/SkillOpt` 为空/SHA 不符时**硬中止**兜底。

## 无论如何先做的
1. 给 fork 建 `origin=Yihao-DD/SkillOpt`（私有），**提交那个未提交的 openai-compat 修复**为 fork commit；与 `patches/deepseek-backend-adapter.patch` 对账，二选一保留，避免双重 apply（审计 F1）。
2. workspace `.gitignore` 移除 `SkillOpt/`；fork 树纳入 `vendor/SkillOpt/`；`RELEASES.md` 记基线（workspace SHA + fork commit + upstream SHA）。

## 备选（否决）
- **submodule**：多一个私有仓依赖 + `--recurse` 静默坑；唯一优点（干净 upstream 合并）对本低频项目低价值。若未来频繁 re-merge 上游或有强需求，再写 superseding ADR 改投。
- **subtree**：upstream re-merge 最痛，否决。
