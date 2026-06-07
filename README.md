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

## VM smoke 一键入口
公司侧新虚拟机 clone 后可先跑零 API smoke：
```bash
bash tools/bootstrap_vm_smoke.sh
```

需要同时验证数据物化 + dataloader（要求能访问 HuggingFace）：
```bash
RUN_DATA_SMOKE=1 bash tools/bootstrap_vm_smoke.sh
```

需要跑最小真实 API smoke（需先写 `.env`，会产生少量费用）：
```bash
cp .env.example .env
# 填 AZURE_OPENAI_AUTH_MODE / AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY
RUN_DATA_SMOKE=1 RUN_API_SMOKE=1 bash tools/bootstrap_vm_smoke.sh
```

脚本会自动补 `SkillOpt/`、checkout 到报告使用的 `ee9931e`、创建 `.venv`、安装依赖并运行 `tools/test_materialize_searchqa.py qd/tests/`。

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
