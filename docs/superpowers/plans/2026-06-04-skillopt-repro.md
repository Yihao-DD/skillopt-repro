# SkillOpt 忠实复刻 (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fork 官方 `microsoft/SkillOpt` 并在 SearchQA + GPT-5.5 下搭好"一键可跑 + 可验收"的 vanilla 复刻脚手架（训练由用户自跑）。

**Architecture:** 工作根 `E:\skillopt` 是我们的 git 工作区（追踪脚手架）；官方仓库克隆到子目录 `SkillOpt/`（自带 git，`upstream` 远程，被工作区 `.gitignore`）。唯一新写的核心代码是 `tools/materialize_searchqa.py`（从 HuggingFace 还原 SearchQA 全字段，纯逻辑部分走 TDD）。其余为后端模板、验收报告模板、运行手册。

**Tech Stack:** Python ≥3.10、官方 `skillopt` 包（openai/pyyaml/numpy/…，纯 API 无 GPU）、HuggingFace `datasets`（仅物化用）、pytest（仅测物化逻辑）。

**对应 spec：** [docs/superpowers/specs/2026-06-04-skillopt-repro-design.md](../specs/2026-06-04-skillopt-repro-design.md)

**执行归属：** 标 **[Claude-setup]** 的任务可由 Claude 直接跑（无 API 费用）；标 **[User-run]** 的命令需用户的 GPT-5.5 key，写入 README 供用户执行，**Claude 不执行付费训练**。

---

## File Structure

| 文件 | 责任 | 追踪? |
|---|---|---|
| `E:\skillopt\.gitignore` | 忽略 `SkillOpt/`、`.env`、`.venv/`、`__pycache__/` | ✅ 工作区 |
| `E:\skillopt\SkillOpt\` | 官方仓库 fork（自带 git，`upstream` 远程） | ❌ 忽略 |
| `E:\skillopt\SkillOpt\data\searchqa_split\` | 物化产出（config 期望路径） | ❌ 忽略 |
| `E:\skillopt\tools\materialize_searchqa.py` | SearchQA 数据物化（HF join + 校验） | ✅ |
| `E:\skillopt\tools\test_materialize_searchqa.py` | 物化纯逻辑单测 | ✅ |
| `E:\skillopt\requirements-extra.txt` | 物化额外依赖（datasets/huggingface_hub） | ✅ |
| `E:\skillopt\.env.example` | 后端凭据模板（两路，key 留空） | ✅ |
| `E:\skillopt\baseline_report.md` | 验收报告模板（用户跑完回填） | ✅ |
| `E:\skillopt\README.md` | 运行手册（安装/物化/sanity/训练/评估/验收） | ✅ |

> 所有命令默认 **工作目录 = `E:\skillopt`（工作区根）**，除非注明 `cd SkillOpt`。Claude 用 Bash 工具执行；用户在 PowerShell/Git Bash 执行（README 给两种）。

---

## Task 1: 工作区 git 初始化 + .gitignore  [Claude-setup]

**Files:**
- Create: `E:\skillopt\.gitignore`

- [ ] **Step 1: 初始化工作区 git 仓库**

Run（CWD=`E:\skillopt`）:
```bash
git init
```
Expected: `Initialized empty Git repository in .../skillopt/.git/`（若已是仓库则跳过）。

- [ ] **Step 2: 写 `.gitignore`**

写入 `E:\skillopt\.gitignore`：
```gitignore
# 官方 fork 自带 git，独立管理
SkillOpt/

# 凭据
.env

# Python
.venv/
__pycache__/
*.pyc

# 运行产物（如果挪到工作区）
outputs/
```

- [ ] **Step 3: 提交**

Run:
```bash
git add .gitignore docs/
git commit -m "chore: init workspace, ignore fork/venv/secrets, add Phase-1 spec+plan"
```
Expected: 一个提交，包含 `.gitignore` 与已存在的 `docs/superpowers/specs|plans`。

---

## Task 2: 克隆官方 fork 到 `SkillOpt/`  [Claude-setup]

**Files:**
- Create: `E:\skillopt\SkillOpt\`（克隆产物，工作区忽略）

- [ ] **Step 1: 克隆**

Run（CWD=`E:\skillopt`）:
```bash
git clone https://github.com/microsoft/SkillOpt.git SkillOpt
```
Expected: `SkillOpt/` 出现，含 `skillopt/ scripts/ configs/ data/ ckpt/ pyproject.toml`。

- [ ] **Step 2: 远程命名 + 记录 commit**

Run:
```bash
cd SkillOpt
git remote rename origin upstream
git log -1 --format="upstream pinned at %H %ci"
cd ..
```
Expected: 打印一行 `upstream pinned at <hash> <date>`（记入 baseline_report 的 commit 字段）。

- [ ] **Step 3: 校验关键文件存在**

Run:
```bash
ls SkillOpt/configs/searchqa/default.yaml SkillOpt/ckpt/searchqa/gpt5.5_skill.md SkillOpt/data/searchqa_id_split/test/items.json
```
Expected: 三个路径都存在，无 "No such file"。

> 本任务不产生工作区追踪变更（`SkillOpt/` 被忽略），无需提交。

---

## Task 3: Python 环境 + 安装  [Claude-setup]

**Files:**
- Create: `E:\skillopt\requirements-extra.txt`

- [ ] **Step 1: 写 `requirements-extra.txt`**

写入 `E:\skillopt\requirements-extra.txt`：
```text
# 仅数据物化需要（不在官方依赖内）
datasets>=2.19.0
huggingface_hub>=0.23.0
```

- [ ] **Step 2: 建虚拟环境并安装**

Run（CWD=`E:\skillopt`）:
```bash
python -m venv .venv
# 激活： Windows PowerShell→ .venv\Scripts\Activate.ps1 ；Git Bash→ source .venv/Scripts/activate
python -m pip install -U pip
python -m pip install -e ./SkillOpt
python -m pip install -r requirements-extra.txt
```
Expected: 安装成功，末尾 `Successfully installed ... skillopt-0.1.0 ...`。

- [ ] **Step 3: 校验导入**

Run:
```bash
python -c "import skillopt; print('SkillOpt ready!')"
python -c "import datasets; print('datasets', datasets.__version__)"
```
Expected: 打印 `SkillOpt ready!` 与 `datasets <版本>`。

- [ ] **Step 4: 提交**

Run:
```bash
git add requirements-extra.txt
git commit -m "chore: pin extra deps (datasets, huggingface_hub) for SearchQA materialization"
```

---

## Task 4: 数据物化脚本（TDD）  [Claude-setup]

**Files:**
- Create: `E:\skillopt\tools\materialize_searchqa.py`
- Test: `E:\skillopt\tools\test_materialize_searchqa.py`

字段映射（已核对 HF `lucadiliello/searchqa` 与 `rollout.py`/`evaluator.py`）：`key→id`、`question→question`、`context→context`（已是 `[DOC]` 格式）、`answers→answers`（list）。

- [ ] **Step 1: 写失败测试**

写入 `E:\skillopt\tools\test_materialize_searchqa.py`：
```python
import pytest
from materialize_searchqa import build_split, coerce_answers, validate_counts


def test_build_split_maps_fields():
    key_to_row = {"a": {"key": "a", "question": "Q1", "context": "[DOC] C1", "answers": ["X"]}}
    out = build_split(["a"], key_to_row)
    assert out == [{"id": "a", "question": "Q1", "context": "[DOC] C1", "answers": ["X"]}]


def test_build_split_raises_on_missing_id():
    with pytest.raises(KeyError):
        build_split(["missing"], {"a": {"question": "Q", "context": "C", "answers": ["X"]}})


def test_coerce_answers_handles_str_list_none():
    assert coerce_answers("hello") == ["hello"]
    assert coerce_answers(["a", "b"]) == ["a", "b"]
    assert coerce_answers(None) == []


def test_validate_counts_mismatch_raises():
    with pytest.raises(ValueError):
        validate_counts("train", [{"id": "1"}])  # train 期望 400
```

- [ ] **Step 2: 运行测试，确认失败**

Run（CWD=`E:\skillopt\tools`）:
```bash
python -m pytest test_materialize_searchqa.py -v
```
Expected: FAIL，`ModuleNotFoundError: No module named 'materialize_searchqa'`。

- [ ] **Step 3: 写实现**

写入 `E:\skillopt\tools\materialize_searchqa.py`：
```python
#!/usr/bin/env python3
"""Materialize the SearchQA split for SkillOpt from HuggingFace.

官方仓库只发布 ID 清单（data/searchqa_id_split/{train,val,test}/items.json，
每个是 [{"id": <32位 key>}, ...]）。SkillOpt 的 SearchQA env 需要全字段 items
（id/question/context/answers）放在 data/searchqa_split/{train,val,test}/items.json。
本脚本用 key==id 关联 HF `lucadiliello/searchqa` 并写出完整 split。
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any

MANIFEST_COUNTS = {"train": 400, "val": 200, "test": 1400}
SPLITS = ("train", "val", "test")


def load_manifest_ids(id_split_dir: str, split: str) -> list[str]:
    path = os.path.join(id_split_dir, split, "items.json")
    with open(path, encoding="utf-8") as f:
        items = json.load(f)
    return [str(it["id"]) for it in items]


def coerce_answers(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(a) for a in value]


def build_split(manifest_ids: list[str], key_to_row: dict[str, dict]) -> list[dict]:
    """Join manifest IDs to HF rows. Raises KeyError if any ID is missing."""
    missing = [i for i in manifest_ids if i not in key_to_row]
    if missing:
        raise KeyError(
            f"{len(missing)} manifest IDs not found in source dataset; "
            f"first few: {missing[:5]}"
        )
    out: list[dict] = []
    for i in manifest_ids:
        row = key_to_row[i]
        out.append({
            "id": i,
            "question": row["question"],
            "context": row.get("context", ""),
            "answers": coerce_answers(row.get("answers")),
        })
    return out


def validate_counts(split: str, items: list[dict]) -> None:
    expected = MANIFEST_COUNTS[split]
    if len(items) != expected:
        raise ValueError(f"split={split}: expected {expected} items, got {len(items)}")


def write_split(out_dir: str, split: str, items: list[dict]) -> str:
    split_dir = os.path.join(out_dir, split)
    os.makedirs(split_dir, exist_ok=True)
    out_path = os.path.join(split_dir, "items.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    return out_path


def load_key_to_row() -> dict[str, dict]:
    """Load HF lucadiliello/searchqa (train+validation) into {key: row}."""
    from datasets import load_dataset

    key_to_row: dict[str, dict] = {}
    for hf_split in ("train", "validation"):
        ds = load_dataset("lucadiliello/searchqa", split=hf_split)
        for row in ds:
            key_to_row[str(row["key"])] = row
    return key_to_row


def main() -> None:
    ap = argparse.ArgumentParser(description="Materialize SearchQA split from HF.")
    ap.add_argument("--id-split-dir", default="SkillOpt/data/searchqa_id_split")
    ap.add_argument("--out-dir", default="SkillOpt/data/searchqa_split")
    ap.add_argument("--force", action="store_true", help="rebuild even if output exists")
    args = ap.parse_args()

    if not args.force and all(
        os.path.exists(os.path.join(args.out_dir, s, "items.json")) for s in SPLITS
    ):
        print(f"{args.out_dir} already complete; use --force to rebuild.")
        return

    print("Loading HF lucadiliello/searchqa (train+validation)...")
    key_to_row = load_key_to_row()
    print(f"  loaded {len(key_to_row)} source rows")

    for split in SPLITS:
        ids = load_manifest_ids(args.id_split_dir, split)
        items = build_split(ids, key_to_row)
        validate_counts(split, items)
        out_path = write_split(args.out_dir, split, items)
        print(f"  {split}: wrote {len(items)} items -> {out_path}")
    print("Done.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试，确认通过**

Run（CWD=`E:\skillopt\tools`）:
```bash
python -m pytest test_materialize_searchqa.py -v
```
Expected: 4 passed。

- [ ] **Step 5: 提交**

Run（CWD=`E:\skillopt`）:
```bash
git add tools/materialize_searchqa.py tools/test_materialize_searchqa.py
git commit -m "feat: SearchQA materialization script (HF join + validation) with unit tests"
```

---

## Task 5: 运行物化，产出 `data/searchqa_split/`  [Claude-setup]

> 免费（仅 HF 下载，约 325MB，无 API 费用）。

- [ ] **Step 1: 运行物化**

Run（CWD=`E:\skillopt`，已激活 venv）:
```bash
python tools/materialize_searchqa.py
```
Expected:
```
Loading HF lucadiliello/searchqa (train+validation)...
  loaded <≈134364> source rows
  train: wrote 400 items -> SkillOpt/data/searchqa_split/train/items.json
  val: wrote 200 items -> SkillOpt/data/searchqa_split/val/items.json
  test: wrote 1400 items -> SkillOpt/data/searchqa_split/test/items.json
Done.
```

- [ ] **Step 2: 校验产物结构与字段**

Run:
```bash
python -c "import json; d=json.load(open('SkillOpt/data/searchqa_split/test/items.json',encoding='utf-8')); print(len(d), sorted(d[0].keys()))"
```
Expected: `1400 ['answers', 'context', 'id', 'question']`。

> 数据在 `SkillOpt/`（被忽略），无工作区提交。

---

## Task 6: 后端凭据模板 `.env.example`  [Claude-setup]

**Files:**
- Create: `E:\skillopt\.env.example`

- [ ] **Step 1: 写 `.env.example`（两路，key 留空）**

写入 `E:\skillopt\.env.example`：
```ini
# 复制为 .env 后二选一填写；用法： set -a; source .env; set +a   （PowerShell 见 README）

# ── 路线 A：OpenAI 直连 ───────────────────────────────
# AZURE_OPENAI_AUTH_MODE=openai_compatible
# AZURE_OPENAI_ENDPOINT=https://api.openai.com/v1
# AZURE_OPENAI_API_KEY=

# ── 路线 B：Azure OpenAI ──────────────────────────────
# AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
# AZURE_OPENAI_API_VERSION=2024-12-01-preview
# AZURE_OPENAI_API_KEY=
# 或免 key：AZURE_OPENAI_AUTH_MODE=azure_cli

# 模型名（两路通用；亦可用 --optimizer_model/--target_model 覆盖）
OPTIMIZER_MODEL=gpt-5.5
TARGET_MODEL=gpt-5.5
```

- [ ] **Step 2: 提交**

Run:
```bash
git add .env.example
git commit -m "chore: add .env.example with OpenAI-direct and Azure backend routes"
```

---

## Task 7: 验收报告模板 `baseline_report.md`  [Claude-setup]

**Files:**
- Create: `E:\skillopt\baseline_report.md`

- [ ] **Step 1: 写模板**

写入 `E:\skillopt\baseline_report.md`：
```markdown
# SkillOpt SearchQA 复刻基线报告 (Phase 1)

> 由用户执行训练后回填。指标 hard=Exact Match (EM)，soft=F1。

## 环境
- 日期：
- Python：
- fork commit（upstream）：
- 后端：OpenAI 直连 / Azure（划掉一项）
- optimizer_model / target_model：gpt-5.5 / gpt-5.5
- seed：42

## 指标
| 项 | 命令 | hard(EM) | soft(F1) | n |
|---|---|---:|---:|---:|
| A*（官方 ckpt 复评） | eval_only --skill ckpt/searchqa/gpt5.5_skill.md | | | 1400 |
| initial.md（弱基线） | eval_only --skill .../skills/initial.md | | | 1400 |
| best_skill.md（训练产物） | train → Final test / eval_only | | | 1400 |
| 论文报告 SearchQA 数字 | （arXiv 2605.23904 结果表） | | — | — |

ε（容差）= ___（建议 0.02–0.03）

## 过程
- 训练步数 / epoch：
- val gate 接受次数 / 总步数：
- skill token 数：initial ___ → best ___
- 墙钟时间 / 估算调用数 / 估算费用：

## 验收（逐条勾选 spec §3）
- [ ] Sanity：A* 与论文数字差距 < ε
- [ ] 训练复现：score(best) ≥ A*−ε 且 ≥ 论文数字−ε
- [ ] 正向提升：score(best) > score(initial.md)
- [ ] 可复现：seed/config/commit/history 已存档

## 结论

```

- [ ] **Step 2: 提交**

Run:
```bash
git add baseline_report.md
git commit -m "docs: add SearchQA baseline acceptance report template"
```

---

## Task 8: 运行手册 `README.md`  [Claude-setup]（其中命令为 [User-run]）

**Files:**
- Create: `E:\skillopt\README.md`

- [ ] **Step 1: 写 README**

写入 `E:\skillopt\README.md`：
````markdown
# SkillOpt 复刻工作区 (Phase 1)

vanilla `microsoft/SkillOpt` 在 SearchQA + GPT-5.5 上的忠实复刻脚手架。
设计见 `docs/superpowers/specs/`，实现计划见 `docs/superpowers/plans/`。

## 布局
- `SkillOpt/` — 官方 fork（自带 git，`upstream` 远程）
- `tools/materialize_searchqa.py` — 数据物化（HF 还原 SearchQA 全字段）
- `.env.example` — 后端凭据模板（两路）
- `baseline_report.md` — 验收报告模板

## 一次性搭建（无 API 费用）
```bash
python -m venv .venv
# 激活：PowerShell→ .venv\Scripts\Activate.ps1 ；Git Bash→ source .venv/Scripts/activate
python -m pip install -U pip
python -m pip install -e ./SkillOpt -r requirements-extra.txt
python tools/materialize_searchqa.py          # 生成 SkillOpt/data/searchqa_split
```

## 配置后端（用你的 GPT-5.5 key）
```bash
cp .env.example .env        # 填路线 A 或 B 的 key
# Git Bash:   set -a; source .env; set +a
# PowerShell: Get-Content .env | ForEach-Object { if ($_ -match '^\s*([^#=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim()) } }
```

## 运行（需 API key，会产生费用 — 由你执行）
> 以下命令 CWD=`SkillOpt/`。Windows 跑 `run_searchqa.sh` 用 Git Bash/WSL，或直接调 `python scripts/train.py`。

1) Sanity（复评官方 ckpt，得 A*）：
```bash
cd SkillOpt
python scripts/eval_only.py --config configs/searchqa/default.yaml \
  --skill ckpt/searchqa/gpt5.5_skill.md \
  --split valid_unseen --split_dir data/searchqa_split --out_root outputs/eval_ckpt
# 末尾打印： Results: hard=<A*>  soft=<F1>  (n=1400)
```

2) 初始弱基线（可选）：
```bash
python scripts/eval_only.py --config configs/searchqa/default.yaml \
  --skill skillopt/envs/searchqa/skills/initial.md \
  --split valid_unseen --split_dir data/searchqa_split --out_root outputs/eval_initial
```

3) 训练（官方默认超参，不调参；末尾自动评 test）：
```bash
python scripts/train.py --config configs/searchqa/default.yaml \
  --optimizer_model gpt-5.5 --target_model gpt-5.5 \
  --out_root outputs/searchqa_run1
# 末尾打印： Final test: <score>     产物： outputs/searchqa_run1/best_skill.md
```

4) 复评训练产物：
```bash
python scripts/eval_only.py --config configs/searchqa/default.yaml \
  --skill outputs/searchqa_run1/best_skill.md \
  --split valid_unseen --split_dir data/searchqa_split --out_root outputs/eval_best
```

5) 把 A* / initial / best / 论文数字填入 `../baseline_report.md`，逐条核对验收（spec §3）。

## 成本提示
单次 SearchQA 训练约 10⁴ 量级 GPT-5.5 调用（每步在 val=200 上 gating 是主要开销）。先单 seed 打通；如需更稳，再补 1–2 个 seed。
````

- [ ] **Step 2: 提交**

Run:
```bash
git add README.md
git commit -m "docs: add Phase-1 runbook (setup, materialize, sanity, train, eval, acceptance)"
```

---

## Task 9: 交付物自检（Phase 1 完成判定）  [Claude-setup]

- [ ] **Step 1: 核对交付物齐备**

Run（CWD=`E:\skillopt`）:
```bash
ls .gitignore .env.example baseline_report.md README.md requirements-extra.txt tools/materialize_searchqa.py tools/test_materialize_searchqa.py
ls SkillOpt/data/searchqa_split/train/items.json SkillOpt/data/searchqa_split/val/items.json SkillOpt/data/searchqa_split/test/items.json
python -m pytest tools/test_materialize_searchqa.py -q
git log --oneline -8
```
Expected: 所有文件存在；pytest 全过；git log 显示各任务提交。

- [ ] **Step 2: 交接给用户**

打印一句话提示：脚手架就绪，按 `README.md` 的「运行」用你的 GPT-5.5 key 跑 sanity→train→eval，并回填 `baseline_report.md`。

---

## Self-Review

**1. Spec coverage（逐节核对 spec）：**
- §1 fork+可运行 → T2；数据物化 → T4/T5；GPT-5.5 跑通 → README 运行段（User-run）；验收 → T7 模板 + README step5；脚手架 → T1/T3/T6/T8。✅
- §3 验收标准 → baseline_report 勾选项逐条对应。✅
- §4 目录布局 → File Structure + T1/T2 一致（fork 子目录 + 忽略）。✅
- §5 安装 → T3。§6 后端参数化 → T6 `.env.example` 两路 + README 配置段。§7 物化 → T4/T5。✅
- §9 报告字段 → T7 模板覆盖（环境/指标/过程/验收）。✅
- §11 排除项 → 计划无任何扩展/接缝/其他 benchmark 任务。✅

**2. Placeholder scan：** 无 TBD/TODO/"handle edge cases" 等；代码步骤均含完整代码；命令均含预期输出。`<your-resource>`/`<A*>`/`<score>` 为模板/运行期占位（合法）。✅

**3. Type/signature consistency：** `build_split(manifest_ids, key_to_row)`、`coerce_answers(value)`、`validate_counts(split, items)`、`write_split(out_dir, split, items)`、`load_manifest_ids(id_split_dir, split)`、`load_key_to_row()` 在实现与测试中签名/字段一致；输出字段 `id/question/context/answers` 与 `rollout.py::process_one` 消费一致；`items.json` 文件名与 `SplitDataLoader.load_split_items` 的 glob 行为一致。✅
- eval test 用 `--split valid_unseen`（经 `_SPLIT_ALIAS` 映射到 `test`），与 README 一致。✅
