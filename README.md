# skillopt-repro — QD-over-Skills

> **任何 agent 第一眼读这里。** 本仓库在 `microsoft/SkillOpt` 之上做 **Quality-Diversity（MAP-Elites）搜索**（"QD-over-Skills"）：用「按行为分格的档案 + 格内严格 `>` gate」替代 SkillOpt 的单点贪心 gate，逃出局部最优、又不破坏其稳定性（**K=1 = SkillOpt 特例**）。研究内容与红线见 `QD-over-Skills/`；协作/交付流程见 `PROCESS.md`。

## ⛓️ 硬约定（最先判断）
prompt **每句**以 `在公司，` 开头 ⇒ **公司模式（runs-only）**：只跑 `run_experiment.py` + 填 `FEEDBACK.md`，**绝不改码 / commit / push**。无前缀 ⇒ 我方全权限。详见 `PROCESS.md §9` / `QD-over-Skills/AGENTS.md`。

## 读序（开工前按顺序读）
1. `QD-over-Skills/AGENTS.md` — agent 入口（红线 + 读序）。
2. `PROCESS.md` — 协作 SSOT：双单向通道（代码 us→公司 经不可变 tag；结果 公司→us 经手递包 + `ingest_feedback.py`）、运行生命周期、预检门、结构 vs 约定诚实分级。
3. `QD-over-Skills/BRIEF.md` + `方案与数学推导.md`（SPEC：命题/证明/诚实分级）。
4. `QD-over-Skills/.tasks/INDEX.md` — 研究任务看板（SSOT）T000–T013。
5. **`REORG_PLAN.md` — ⚠️ 当前活的执行清单（reorg 进行中；先看其 `RESUME HERE`）。**

## 当前状态（2026-06-08）
- 在 **分支 `reorg/2026-06-08`** 上做**封存+重组**：审计（`审计报告-公司工作记录.md`，14 类失败模式）后的响应 = 5 个 ADR + `PROCESS.md`。
- 进度：**S0 / F0 / S1 done（`qd/tests` 29 passed）**；**下一步 = S2 重建 descriptor**（见 `REORG_PLAN.md` 的 RESUME HERE）。
- 旧的 Phase-1（SearchQA + GPT-5.5）脚手架**已被取代**，将在 reorg 时封进 `_sealed_2026-06-08/`。

## 布局
| 路径 | 作用 |
|---|---|
| `qd/` | QD 核心实现（descriptor/archive/variation/budget/scheduler；`loop.py` 待建 S4）+ `tests/` |
| `QD-over-Skills/` | SPEC + 文件系统式 PM（`.tasks/` SSOT、`decisions/` ADR-0001..0005、`BRIEF`/`PROJECT_MANAGEMENT`/`OPEN_DECISIONS`） |
| `PROCESS.md` / `REORG_PLAN.md` | 协作流程 / 当前执行清单 |
| `handoff/` | 出站交付（`RUNBOOK.md` + `RUN_REQUEST`/`FEEDBACK` 模板） |
| `SkillOpt/` | 上游 fork（`ee9931e`，待 vendor 进 `vendor/SkillOpt/`，见 ADR-0004） |
| `tools/` | 数据物化（`materialize_spreadsheetbench.py`）；`conftest.py` 让 `import skillopt/qd` 在干净 clone 上可解析 |
| `审计报告-公司工作记录.md` / `工作记录-完整版.md` | 审计 + 公司工作记录（失败证据，将封进 `_sealed_`） |

## 本地搭建（零 API）
```bash
python -m venv .venv          # Python 3.10+
.venv\Scripts\python.exe -m pip install -U pip
.venv\Scripts\python.exe -m pip install -e ./SkillOpt -r requirements-extra.txt
.venv\Scripts\python.exe -m pytest qd/tests -q     # 应全绿（conftest 自动解析 import）
```

## 跑实验（验证「效果」）
- **付费实验必须先过预检门**（`PROCESS.md §4`）。验证路径：建 `qd/loop.py`（S4–S9）→ 用 DeepSeek 跑 **~100 题预检**（便宜，核心验 `n_occupied>1` = QD 真的探索吗）→ 过了才全量。
- 主战场 benchmark = **SpreadsheetBench**（数据自带，见 ADR-0005）。
