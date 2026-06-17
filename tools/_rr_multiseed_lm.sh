#!/bin/bash
# RR-Boost LiveMath multi-seed hardening.
# For each given seed: D_cal power-adjusted probe (probe_cal) -> routed test (--bar sign).
# Tests whether the gate OPENS consistently across seeds AND whether the within-run gain
# replicates. Per-seed eval-shuffle varies; target stays temp=0/seed=42 (frozen).
#
# Usage: bash _rr_multiseed_lm.sh <key> <consensus> <seed> [seed ...]
#   consensus = 0  -> v1 single-pass math-AVP (tags rr_*_lm_s<seed>)
#   consensus >=2  -> v2 consensus-correction (tags rr_*_lm_v2_s<seed>, --lm-consensus N)
#   e.g.  x2 3 1 2 3   (v2, 3 verify passes, seeds 1/2/3)
set -u
ROOT=/root/skillopt-fullrun-gatesweep
PY=/root/miniconda3/bin/python
KEY="${1:-x2}"; CONS="${2:-0}"
shift 2
SUF=""; EXTRA=""
if [ "$CONS" -ge 2 ]; then SUF="_v2"; EXTRA="--lm-consensus $CONS"; fi
exec > /tmp/rr_ms_lm${SUF}.log 2>&1
SKILL=outputs/lm_k1_s1/best_skill.md
cd "$ROOT" || exit 1
for S in "$@"; do
  RJ=outputs/rr_router/livemathematicianbench_dcal${SUF}_s${S}.json
  echo "==================== SEED ${S} probe_cal (cons=${CONS}) ===================="
  $PY repro/official/rver_probe.py --env livemathematicianbench --mode probe_cal \
      --skill $SKILL --key $KEY --seed $S --workers 24 --tag rr_pcal_lm${SUF}_s${S} \
      --router-json $RJ $EXTRA
  echo "==================== SEED ${S} routed test (bar=sign, cons=${CONS}) ===================="
  $PY repro/official/rver_probe.py --env livemathematicianbench --mode test \
      --skill $SKILL --key $KEY --seed $S --workers 24 --tag rr_boost_test_lm${SUF}_s${S} \
      --router-json $RJ --bar sign $EXTRA
done
echo "==================== ALL SEEDS DONE ===================="
