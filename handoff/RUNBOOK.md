# RUNBOOK — 公司侧跑全量（这是你唯一需要读的文档）

> ⚠️ **你不会改任何代码。** 需要改 → 写进 `FEEDBACK.md` 的 `proposed_changes`，我们来改、重打 tag、再发给你。本地改代码会被结构性拒收，且毁掉结果可信度。
>
> 📦 **数据已随仓库自带**（`data/benchmarks/`）——**无需下载、无需联网、无需物化**；`run_experiment.py` 启动会自动解压到本地。
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

## 1. 取码（只读，单向）
```bash
# 方式 A：能连 GitHub
git clone --recurse-submodules <repo>
git checkout <code_tag>        # 例 run/redo-headline/v1
# 方式 B：air-gapped → 解压我方发来的 release zip
```

## 2. step 0：核对（不符就停，别跑）
```bash
python scripts/verify_checkout.py     # 比对本地 SHA / 树哈希 == MANIFEST.txt
```
- `vendor/SkillOpt` 必须**非空**且 HEAD == MANIFEST 的 submodule_sha。空或不符 → **停手**，回我方。

## 3. 跑全量（一条命令）
```bash
python scripts/run_experiment.py --config configs/spreadsheetbench/full280.yaml --full
```
- harness 会自动：断言 clean-tree + 算整树哈希 + 校验 target temp=0/seed + 两臂共享昂贵评估计数器 + 实时写 `run_provenance.json`。任一不满足它**自己拒绝启动**——这是在保护你，不是刁难。
- 想先小试：`--config configs/spreadsheetbench/preflight100.yaml --subset 100`。

## 4. 运维纪律（避免上次的坑）
- **按 PID 杀**：用打印出来的 stop 脚本 / `kill <PID>`，**绝不** `pkill run_experiment.py`（会误杀别的 run）。
- **smoke 与 full 用不同/串行的端点**，别让两个 job 抢同一个 fp8 代理（会污染结果）。
- 产物**原子写**（harness 已做 temp+rename）；中途被杀不会留半截 `summary.json`。

## 5. 出 bug 怎么办
- **不要改代码。** 置 `status=code_defect`，把报错 + 日志 + 描述式 diff 写进 `FEEDBACK.md §4`，停手发回。

## 6. 打包回传（唯一回传方式）
```bash
python scripts/make_bundle.py         # 把 returned/ 打成 zip + 算 sha256
```
- 把 `returned/<run_id>.zip` **人手**发我方（邮件/IM/文件分享），**并把 sha256 粘进发件正文**（我方据此验完整性）。
- 你**永不** push、永不 commit。

## 7. 常见问题
- 代理报 400（`max_completion_tokens`/`reasoning_effort`）→ 已在代码里修好（openai-compat 适配），不用动；若仍报，记进 FEEDBACK。
- `run_experiment.py` 说「dirty tree, refusing」→ 你动到了被追踪文件。**重新解压一份干净的**再跑，别去 `git checkout --` 硬抹（那会掩盖问题）。
- 跑很久/很贵 → 它到 `expensive_eval_budget_per_arm` 会自己停（`status=budget_exceeded`）；预算在 `RUN_REQUEST` 里，疑问回我方。
