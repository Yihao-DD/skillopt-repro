#!/usr/bin/env bash
set -euo pipefail

# Bootstrap a fresh VM clone and run the zero/low-cost smoke suite.
#
# Defaults:
#   - clone microsoft/SkillOpt into ./SkillOpt if missing
#   - create .venv
#   - install SkillOpt + extra deps
#   - run local pytest smoke
#
# Optional:
#   RUN_DATA_SMOKE=1 materialize HF datasets and validate SkillOpt dataloaders
#   RUN_API_SMOKE=1  run one-item DeepSeek eval/train smoke (requires .env)
#
# Examples:
#   bash tools/bootstrap_vm_smoke.sh
#   RUN_DATA_SMOKE=1 bash tools/bootstrap_vm_smoke.sh
#   RUN_DATA_SMOKE=1 RUN_API_SMOKE=1 bash tools/bootstrap_vm_smoke.sh

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=python3
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN=python
  elif [[ -x /root/miniconda3/bin/python ]]; then
    PYTHON_BIN=/root/miniconda3/bin/python
  else
    echo "No Python found. Set PYTHON_BIN=/path/to/python." >&2
    exit 1
  fi
fi

SKILLOPT_COMMIT="${SKILLOPT_COMMIT:-ee9931e}"
if [[ ! -d SkillOpt/.git ]]; then
  git clone https://github.com/microsoft/SkillOpt.git SkillOpt
fi
if ! git -C SkillOpt rev-parse --verify "${SKILLOPT_COMMIT}^{commit}" >/dev/null 2>&1; then
  git -C SkillOpt fetch --all --tags
fi
git -C SkillOpt checkout "$SKILLOPT_COMMIT"

"$PYTHON_BIN" -m venv .venv
.venv/bin/python -m pip install -U pip setuptools wheel
.venv/bin/python -m pip install -e ./SkillOpt -r requirements-extra.txt

.venv/bin/python -m pytest tools/test_materialize_searchqa.py qd/tests/ -q

if [[ "${RUN_DATA_SMOKE:-0}" == "1" ]]; then
  .venv/bin/python tools/materialize_searchqa.py
  .venv/bin/python tools/materialize_spreadsheetbench.py
  (
    cd SkillOpt
    ../.venv/bin/python - <<'PY'
from skillopt.config import load_config, flatten_config
from scripts.train import get_adapter

cases = [
    ("searchqa", "configs/searchqa/default.yaml", 400, 200, 1400),
    ("spreadsheetbench", "configs/spreadsheetbench/default.yaml", 80, 40, 280),
]
for name, cfg_path, train_n, val_n, test_n in cases:
    cfg = flatten_config(load_config(cfg_path))
    adapter = get_adapter(cfg)
    adapter.setup(cfg)
    dl = adapter.get_dataloader()
    got = (len(dl.train_items), len(dl.val_items), len(dl.test_items))
    expected = (train_n, val_n, test_n)
    assert got == expected, (name, got, expected)
    print(f"{name}: adapter smoke ok train={train_n} val={val_n} test={test_n}")
PY
  )
fi

if [[ "${RUN_API_SMOKE:-0}" == "1" ]]; then
  if [[ ! -f .env ]]; then
    echo "RUN_API_SMOKE=1 requires .env with backend credentials." >&2
    exit 1
  fi
  (
    cd SkillOpt
    if git apply --check ../patches/deepseek-backend-adapter.patch >/dev/null 2>&1; then
      git apply ../patches/deepseek-backend-adapter.patch
    fi
  )
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
  (
    cd SkillOpt
    ../.venv/bin/python - <<'PY'
import json
from pathlib import Path

src = Path("data/searchqa_split")
dst = Path("data/searchqa_tiny_split")
for split in ["train", "val", "test"]:
    items = json.loads((src / split / "items.json").read_text(encoding="utf-8"))[:1]
    out = dst / split
    out.mkdir(parents=True, exist_ok=True)
    (out / "items.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
PY
    ../.venv/bin/python scripts/eval_only.py \
      --config configs/searchqa/default.yaml \
      --skill skillopt/envs/searchqa/skills/initial.md \
      --split valid_unseen \
      --split_dir data/searchqa_split \
      --target_model "${TARGET_MODEL:-deepseek-chat}" \
      --reasoning_effort "" \
      --test_env_num 1 \
      --out_root outputs/smoke_searchqa_eval1
    ../.venv/bin/python scripts/eval_only.py \
      --config configs/spreadsheetbench/default.yaml \
      --skill skillopt/envs/spreadsheetbench/skills/initial.md \
      --split valid_unseen \
      --split_dir data/spreadsheetbench_split \
      --target_model "${TARGET_MODEL:-deepseek-chat}" \
      --reasoning_effort "" \
      --test_env_num 1 \
      --out_root outputs/smoke_ssb_eval1
    ../.venv/bin/python scripts/train.py \
      --config configs/searchqa/default.yaml \
      --split_dir data/searchqa_tiny_split \
      --optimizer_model "${OPTIMIZER_MODEL:-deepseek-chat}" \
      --target_model "${TARGET_MODEL:-deepseek-chat}" \
      --reasoning_effort "" \
      --num_epochs 1 \
      --train_size 1 \
      --batch_size 1 \
      --minibatch_size 1 \
      --merge_batch_size 1 \
      --analyst_workers 1 \
      --workers 1 \
      --edit_budget 1 \
      --min_edit_budget 1 \
      --sel_env_num 1 \
      --test_env_num 0 \
      --eval_test false \
      --use_slow_update false \
      --use_meta_skill false \
      --out_root outputs/smoke_searchqa_train1
  )
fi

echo "Smoke bootstrap complete."
