# RUNBOOK — 公司侧跑全量（这是你唯一需要读的文档）

> ⚠️ **你不会改任何代码。** 需要改 → 写进 `FEEDBACK.md` 的 `proposed_changes`，我们来改、重打 tag、再发给你。本地改代码会被结构性拒收，且毁掉结果可信度。
>
> 📦 **数据已随 zip 自带**（`SkillOpt/data/spreadsheetbench_*`）——**无需下载、无需联网、无需物化**。GitHub clone 缺哪些件、怎么补，见 `LOCAL_ONLY.md`。
>
> 🏷️ **如果你用 agent（Codex/Claude）操作**：每句 prompt 前加 `在公司，`，它就会进 runs-only 模式（只跑不改）。详见 `PROCESS.md §9`。

---

## 0. 前置
- Python 3.10+，建独立 venv。
- 在仓库根目录建 `.env`（**唯一你要碰的文件**，已被 gitignore，永不提交）：
  ```
  AZURE_OPENAI_AUTH_MODE=openai_compatible
  AZURE_OPENAI_ENDPOINT=<venus llmproxy 地址>
  AZURE_OPENAI_API_KEY=<key>
  TARGET_MODEL=<RUN_REQUEST 里的 model_snapshot>
  ```

## 1. 取码（从 GitHub Releases 下载自包含 zip）
```bash
# 从仓库 Releases 页下载我方上传的 release 资产（含 fork 引擎 + SpreadsheetBench 数据 + .env.example）
gh release download <tag> -p '*.zip'        # 或网页点下载
unzip skillopt-fullrun-<sha>.zip && cd skillopt-fullrun-<sha>
# 核对：本地算 zip 的 sha256，必须 == release notes 里贴的值
```
> ⚠️ **别用 `git clone`**——引擎/数据被 gitignore 排除，clone 跑不起来（见 `LOCAL_ONLY.md`）。下载 release zip。

## 2. step 0：装环境 + 自检（不 READY 就停，别跑）
```bash
python -m venv .venv && .venv\Scripts\python.exe -m pip install -U pip
.venv\Scripts\python.exe -m pip install -e ./SkillOpt -r requirements-extra.txt
copy .env.example .env        # 填 endpoint/key/model —— 换 API 的唯一入口（LOCAL_ONLY.md §2）
.venv\Scripts\python.exe scripts\run_experiment.py --full --dry-run
```
- 自检最后一行必须是 `DRY-RUN: READY ...`（fork/数据/key 全在）。出现 `FAIL` → **停手**，回我方。

## 3. 跑全量（一条命令）
```bash
.venv\Scripts\python.exe scripts\run_experiment.py --preflight   # 先 2 题冒烟，确认调通你的 API
.venv\Scripts\python.exe scripts\run_experiment.py --full        # 全量 N=280，K=1 贪心 vs K=4 QD，等预算
```
- launcher 自动：冻结 target（temp=0+seed=42）/ optimizer temp=0.8 + 两臂共享同一 baseline 与等昂贵预算（`eval_budget=12`/臂）+ 写 `runs/full/summary.json`（含 verdict、**不含 key**）。
- 规模/预算旋钮（`--n` / `--eval-budget` / `--k`）见 `LOCAL_ONLY.md §5`。
- 尚未做（S16 加固）：clean-tree 断言 / 整树哈希 / `run_provenance.json`。当前完整性保证 = zip 的 sha256。

## 4. 运维纪律（避免上次的坑）
- **按 PID 杀**：用打印出来的 stop 脚本 / `kill <PID>`，**绝不** `pkill run_experiment.py`（会误杀别的 run）。
- **smoke 与 full 用不同/串行的端点**，别让两个 job 抢同一个 fp8 代理（会污染结果）。
- 产物**原子写**（harness 已做 temp+rename）；中途被杀不会留半截 `summary.json`。

## 5. 出 bug 怎么办
- **不要改代码。** 置 `status=code_defect`，把报错 + 日志 + 描述式 diff 写进 `FEEDBACK.md §4`，停手发回。

## 6. 打包回传（唯一回传方式）
```powershell
Compress-Archive runs\full dist\returned-<run_id>.zip       # 打包本次产物
Get-FileHash dist\returned-<run_id>.zip -Algorithm SHA256   # 算 sha256
```
- 把 `dist/returned-<run_id>.zip` **人手**发我方，**并把 sha256 粘进发件正文**（我方据此验完整性）。
- 你**永不** push、永不 commit。（`scripts/make_bundle.py` 是**我方**发包工具，不是你的回传工具。）

## 7. 常见问题
- 代理报 400（`max_completion_tokens`/`reasoning_effort`）→ 已在代码里修好（openai-compat 适配），不用动；若仍报，记进 FEEDBACK。
- `import skillopt` 失败 / `--dry-run` 报 fork 或数据缺失 → 没 `pip install -e ./SkillOpt`，或 zip 解压不完整。重装/重解压，别手改 `sys.path`。
- 跑很久/很贵 → 它到 `expensive_eval_budget_per_arm` 会自己停（`status=budget_exceeded`）；预算在 `RUN_REQUEST` 里，疑问回我方。
