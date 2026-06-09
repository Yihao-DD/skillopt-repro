# LOCAL_ONLY — GitHub clone 里没有、但全量跑必须的东西

> **一句话**：`git clone` 这个仓库**跑不起来**——引擎和数据都被 `.gitignore` 排除了。
> 公司侧靠**一个 air-gap zip**（我方 `scripts/make_bundle.py` 打）拿到完整可跑包，
> 然后**只改 `.env`（换 API）→ 一条命令启动全量**。本文件就是这条路的 SSOT。

读完本文，公司侧的全流程 = **解压 → 填 `.env` → `python scripts/run_experiment.py --full`**。

---

## 1. GitHub 上没有、只在本地/zip 里的 4 样（gitignore 排除）

| 本地独有 | 是什么 | 大小 | 怎么进 zip |
|---|---|---|---|
| **`SkillOpt/`（fork 引擎）** | 上游 `microsoft/SkillOpt`，自带独立 git。HEAD `0948d2d` = upstream `ee9931e` + 2 个 patch：`05a023c`（openai-compat 后端：`max_tokens`、去 `reasoning_effort`）+ `0948d2d`（角色温度：frozen target / diverse optimizer）。fork 代码本体 ≈ 11M。 | ~11M | `make_bundle` 收（去掉 `.git`/`ckpt`/`outputs`） |
| **`SkillOpt/data/spreadsheetbench_*`** | 已物化的 SpreadsheetBench（`spreadsheetbench_split`=train80/val40/**test280** + `spreadsheetbench_verified_400` 评测集）。由 `tools/materialize_spreadsheetbench.py` 从 HF 物化。 | ~24M | `make_bundle` 收（**只收 spreadsheetbench**，其它 benchmark 丢弃） |
| **`.env`（凭据 = 换 API 的开关）** | `AZURE_OPENAI_ENDPOINT/_API_KEY/TARGET_MODEL/OPTIMIZER_MODEL`。openai-compatible。 | — | **永不进 zip**；zip 里给 `.env.example` 模板，公司自己填 |
| **`.venv/`** | 本机环境 | — | 不进 zip；公司自己 `pip install`（见 §4） |

> fork 的 SHA/provenance 权威记录在 [`handoff/RELEASES.md`](handoff/RELEASES.md)；冻结目标配置在 `configs/frozen/`。

---

## 2. 换 API = 只改 `.env` 这一个文件

`qd/adapter_skillopt.py:configure_deepseek()` 只读下面 4 个变量，配 SkillOpt 的 openai-compatible 客户端。**换任何 OpenAI 兼容后端，只改这里，代码一行不动。**

| `.env` 变量 | 含义 | 被谁读 |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | base URL（如 `https://api.deepseek.com` 或公司 llmproxy 地址） | `configure_deepseek` → `configure_azure_openai(auth_mode="openai_compatible", ...)` |
| `AZURE_OPENAI_API_KEY` | 公司自己的 key（**不缺省、不外传**） | 同上 |
| `TARGET_MODEL` | 被评估模型名（如 `deepseek-chat`） | `set_target_deployment` |
| `OPTIMIZER_MODEL` | 反思/变异模型名 | `set_optimizer_deployment` |

复制模板：`cp .env.example .env`，填上面 4 行即可（路线 A/B/C 见 `.env.example` 注释）。

---

## 3. 我方：打 air-gap zip 并交付

```bash
python scripts/make_bundle.py            # -> dist/skillopt-fullrun-<git-sha>.zip + .sha256
python scripts/make_bundle.py --dry-run  # 先看清单+体积，不写盘（实测 1474 文件 / ~25M）
```
- **进 zip**：仓库代码 + `SkillOpt/` fork + `spreadsheetbench` 数据 + `.env.example`。
- **不进 zip**（安全/瘦身）：`.env`（唯一密钥）、`.git`/`SkillOpt/.git`、`.venv`、`runs/`、`SkillOpt/outputs`（256M）、`ckpt`、非 SpreadsheetBench 的其它 benchmark、`__pycache__`/`*.pyc`。
- 交付：`gh release create <tag> dist/*.zip` 传成 **GitHub Release 资产**，公司从仓库 **Releases** 页一键下载（或 `gh release download <tag> -p '*.zip'`）；sha256 写进 release notes 供核对。（内网 air-gap 也可人手发同一个 zip。）

> 这条 exclude 规则有单测兜底（`qd/tests/test_company_launch.py`，`.env` 绝不进包）。

---

## 4. 公司：解压 → 换 API → 启动全量（直接跑）

```bash
# 0) 解压 release zip，进入 skillopt-fullrun-<sha>/
# 1) 装环境（Python 3.10+；fork 用 editable 装，extra deps 跟上）
python -m venv .venv
.venv\Scripts\python.exe -m pip install -U pip
.venv\Scripts\python.exe -m pip install -e ./SkillOpt -r requirements-extra.txt

# 2) 换 API：复制模板，填 4 个变量（§2）
copy .env.example .env      # 然后编辑 .env

# 3) 先 dry-run 自检（零调用、零费用：确认 fork/数据/key 都在）
.venv\Scripts\python.exe scripts\run_experiment.py --full --dry-run
#    期望最后一行： DRY-RUN: READY ...

# 4) 小试冒烟（2 题，确认真能调通你的 API）
.venv\Scripts\python.exe scripts\run_experiment.py --preflight

# 5) 启动全量（一条命令）
.venv\Scripts\python.exe scripts\run_experiment.py --full
```
产物：`runs/full/summary.json`（plan + baseline + K=1/K=4 两臂 best + verdict + token，**不含 key**）。把 `runs/` 回传即可。

---

## 5. “全量”到底跑什么 + 旋钮 + 成本

`--full` = SpreadsheetBench **test 全集 N=280**，**K=1 贪心 vs K=4 QD**，**等预算** `eval_budget=24`/臂，frozen target（temp=0+seed=42）/ optimizer temp=0.8。两臂共享同一 baseline。

| 旋钮 | 默认（full） | 覆盖方式 |
|---|---|---|
| 任务数 N | 280（test 全集） | `--n 50` |
| 每臂昂贵评估预算 | 24 | `--eval-budget 12`（降浅省钱）/ `48`（加深） |
| QD 臂的 K | 4 | `--k 8` |
| 并发 / 单次 token | 8 / 4096 | `--workers` / `--max-tokens` |
| 输出分目录（多 API 对比） | `runs/full/` | `--tag deepseek` → `runs/full-deepseek/`（各 API 不互相覆盖） |

**成本量级**（随 N × eval_budget × 你的 token 单价线性增长）：我方 DeepSeek 验证 N=20/budget=12 ≈ $0.7；全量 N=280/budget=24 ≈ 28× ≈ **~$20（DeepSeek 价）**。换更贵的模型按 token 单价等比放大。`--dry-run` + `--preflight` 先把风险压掉再上全量；**`--probe-descriptor`**（~8 题、几毛）验该模型 descriptor 散不散（<3 格 = 塌缩 → QD 退化成贪心，别烧全量、回我方重标定 —— 防的就是 Qwen3 那次空跑）。

> ⚠️ **诚实边界**：当前 `adapter.propose` 只是单纯 reflect，QD 的「瞄准着采」（target-cell-conditioned variation，`qd/variation.py`）**还没接进 propose**。所以 `--full` 测的是 QD 的**当前形态**（K>1 分格 + 格内 `>` gate），不是其最强形态。小样本验证里贪心 K=1（0.65）暂赢 QD K=4（0.50）——全量是为了在更大 N/更长 budget 上复核这个结论，不是已经认定 QD 赢。详见 [`README.md`](README.md) 「🎯 验证结果」。

---

## 6. 和 RUNBOOK 的关系

[`handoff/RUNBOOK.md`](handoff/RUNBOOK.md) 是给公司的“运行纪律”（不改码、按 PID 杀、FEEDBACK 回传）。本文件是“**怎么从零跑起来**”的技术 SSOT。两者一致后，RUNBOOK 里历史上引用的 `scripts/run_experiment.py` 现在是**真实存在**的了（本次补齐）。`verify_checkout.py` / MANIFEST 那套更重的校验（S13/S14/S16）仍未做——当前完整性保证 = zip 的 sha256（§3）。
