# ADR-0005 — benchmark 数据自带进仓库（自包含交付，公司零下载零改动）

- 状态: Accepted
- 日期: 2026-06-08
- 关联: `PROCESS.md §10`、`ADR-0003`、`handoff/RUNBOOK.md`、`tools/materialize_spreadsheetbench.py`、`OPEN_DECISIONS.md` BLOCKER-1。

## 背景
公司要求「**不做任何改动就能跑全量**」。但公司机器对 HuggingFace 往往不通（工作记录实测：远程 HF 不通，只能本地物化再传）。所以「run 时去 HF 下载数据」的方案在公司侧会失败，且联网/装依赖 = 「需要改动」。

## 决定
每次交付所需的 benchmark 数据**随 tag 一起带走**（自包含）：
1. 我方用 `tools/materialize_*.py` **一次性**物化（这是 build 步骤，**公司永不跑**）。
2. **小的公开 benchmark**（如 SpreadsheetBench Verified-400，原始 tarball 仅 ~15MB）：把**原始 tarball** 提交进 `data/benchmarks/<bench>/raw/`（单个二进制 blob），split 的 `items.json`（小文本）也提交；`run_experiment.py` 启动若本地缺数据就**自动解压** tarball 到 gitignored 的 `data_root/`。提取出的 xlsx **不提交**（gitignore，运行时从 committed tarball 确定性重建）。
3. **大的 / gated benchmark**（如 OfficeQA gated）：我方一次性获取并物化后 vendored 进仓，或随 release zip；**绝不让公司侧 fetch**。
4. **来源/可重建**：每个 benchmark 在 `data/benchmarks/<bench>/SOURCE.md` 记来源（HF repo + 文件名）+ 版本 + 大小 + `sha256`，使数据可重建、可审计。

## 理由 / 影响
- 公司 `git checkout <tag>` 即拥有全部数据，跑一条命令即可——**零下载、零改动、可复现**（数据随 tag 冻结）。
- 代价：~15MB 二进制进 git（一次性，可接受）；若某 benchmark blob 很大再上 git-lfs。**优先 plain commit 单个 tarball**（公司无需装 git-lfs，更省事）。
- 已验证「获取途径成立」：本 session 实测 `materialize_spreadsheetbench.py` 从 HF `KAKA22/SpreadsheetBench` 拉 15MB → `train=80 / val=40 / test=280` 可用。

## 备选（否决）
- run 时从 HF 下载 → 公司 air-gapped 会失败，否决。
- 只给 materializer 不带数据 → 公司要联网 + 可能装依赖 = 「需要改动」，否决。
- 把提取后的全部 xlsx 提交进 git（~1600 个小文件）→ 仓库膨胀且无谓，否决（改为提交单个 tarball + 运行时解压）。

## 执行（在迁移时落地）
- 迁移 STEP 5 顺带：把 `spreadsheetbench_verified_400.tar.gz` 提交进 `data/benchmarks/spreadsheetbench/raw/`，写 `SOURCE.md`，`items.json` 提交，`data_root` 的解压目录加 `.gitignore`。
