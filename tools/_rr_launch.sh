#!/bin/bash
# RR-SkillOpt: launch ONE rver_probe run in a detached screen on a box.
# Uploaded to /root/_rr_launch.sh and invoked over ssh so no complex quoting
# crosses the PowerShell -> ssh -> sh boundary.
#
# Usage: _rr_launch.sh <env> <mode> <skill_rel> <key> <tag> [workers]
#   env    : livemathematicianbench | searchqa | spreadsheetbench
#   mode   : probe (val-only) | test
#   skill  : path (relative to SkillOpt/) of the incumbent best_skill.md
#   key    : dion|yh|tt|xx|xnyu|x2  (NOT yw — dead)
#   tag    : output tag (outputs/<tag>/)
set -u
ROOT=/root/skillopt-fullrun-gatesweep
SK="$ROOT/SkillOpt"          # outputs/ + skill paths are relative to SkillOpt/
cd "$ROOT" || exit 1
ENV="$1"; MODE="$2"; SKILL="$3"; KEY="$4"; TAG="$5"; WORKERS="${6:-24}"
ROUTER_JSON="${7:-}"; BAR="${8:-net}"; STRUCT="${9:-}"   # optional: router path, gate bar, struct-precision
EXTRA=""
if [ -n "$ROUTER_JSON" ]; then EXTRA="--router-json $ROUTER_JSON --bar $BAR"; fi
if [ -n "$STRUCT" ]; then EXTRA="$EXTRA --structural-precision"; fi
if [ ! -f "$SK/$SKILL" ]; then echo "MISSING SKILL: $SK/$SKILL"; exit 1; fi
mkdir -p "$SK/outputs/rr_frozen"
cp "$SK/$SKILL" "$SK/outputs/rr_frozen/${TAG}_incumbent_best_skill.md" 2>/dev/null || true
screen -dmS "$TAG" bash -lc "cd $ROOT && /root/miniconda3/bin/python repro/official/rver_probe.py --env $ENV --mode $MODE --skill $SKILL --key $KEY --workers $WORKERS --tag $TAG $EXTRA > /tmp/$TAG.log 2>&1"
sleep 2
if screen -ls | grep -q "$TAG"; then
  echo "LAUNCHED $TAG ($ENV $MODE, key=$KEY, workers=$WORKERS)"
else
  echo "WARN: screen $TAG not visible; log tail:"
  tail -8 "/tmp/$TAG.log" 2>/dev/null
fi
