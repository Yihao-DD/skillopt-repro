"""Real SkillOpt + DeepSeek adapter for the QD loop (REORG S15).

Wires :class:`qd.loop.CandidateProducer` to the FROZEN SkillOpt fork's actual
SpreadsheetBench rollout / reflect / apply against DeepSeek. ONE rollout per
skill is cached (by skill hash) and serves all three of:
  - ``score(skill)``  → ``compute_score`` (hard accuracy on the selection set),
  - ``probe(skill)``  → the generated code per item → behavior descriptor,
  - ``propose(skill)``→ ``reflect`` on the rollout results → an edit patch.

The model client is configured from ``.env`` (openai-compatible / DeepSeek).
This is the EXPENSIVE path — used only by run_experiment / the preflight smoke,
never in unit tests. SkillOpt is imported lazily so ``import qd.loop`` stays
model-free.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field

from qd.loop import CandidateProducer


def configure_deepseek(*, optimizer_model: str | None = None, target_model: str | None = None) -> dict:
    """Configure SkillOpt's model clients for DeepSeek (openai-compatible) from .env.

    Reads ``AZURE_OPENAI_ENDPOINT`` / ``AZURE_OPENAI_API_KEY`` (+ optional
    ``TARGET_MODEL`` / ``OPTIMIZER_MODEL``). Returns the resolved {endpoint, models}
    WITHOUT the key (safe to log).
    """
    from skillopt.model.azure_openai import (
        configure_azure_openai,
        set_optimizer_deployment,
        set_target_deployment,
    )

    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "https://api.deepseek.com")
    key = os.environ.get("AZURE_OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("AZURE_OPENAI_API_KEY not set (load .env first)")
    configure_azure_openai(auth_mode="openai_compatible", endpoint=endpoint, api_key=key)
    tm = target_model or os.environ.get("TARGET_MODEL", "deepseek-chat")
    om = optimizer_model or os.environ.get("OPTIMIZER_MODEL", "deepseek-chat")
    set_target_deployment(tm)
    set_optimizer_deployment(om)
    return {"endpoint": endpoint, "target_model": tm, "optimizer_model": om}


def _skill_hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


@dataclass
class SkillOptProducer:
    """Caches one SpreadsheetBench rollout per skill; serves score/probe/propose."""

    adapter: object              # skillopt SpreadsheetBenchAdapter
    items: list                  # selection set (list of item dicts from items.json)
    out_root: str
    _cache: dict = field(default_factory=dict)   # skill_hash -> rollout results

    def _rollout(self, skill: str) -> list[dict]:
        h = _skill_hash(skill)
        if h not in self._cache:
            self._cache[h] = self.adapter.rollout(self.items, skill, os.path.join(self.out_root, h))
        return self._cache[h]

    def score(self, skill: str) -> float:
        from skillopt.utils import compute_score

        hard, _soft = compute_score(self._rollout(skill))
        return float(hard)

    def probe(self, skill: str) -> list[dict]:
        # Real behavior trajectories: the code DeepSeek generated per item, saved
        # by the rollout to predictions/<id>/code.py (NOT in the result dict).
        results = self._rollout(skill)
        pred_dir = os.path.join(self.out_root, _skill_hash(skill), "predictions")
        trajs = []
        for r in results:
            code_path = os.path.join(pred_dir, str(r.get("id", "")), "code.py")
            code = ""
            if os.path.exists(code_path):
                with open(code_path, encoding="utf-8") as f:
                    code = f.read()
            trajs.append({"code": code, "n_turns": r.get("n_turns", 1)})
        return trajs

    def propose(self, skill: str, *, step: int, target_cell: int | None = None) -> dict:
        results = self._rollout(skill)
        patches = self.adapter.reflect(results, skill, os.path.join(self.out_root, _skill_hash(skill)))
        edits: list = []
        for p in patches or []:
            if p and isinstance(p.get("patch"), dict):
                edits.extend(p["patch"].get("edits", []))
        return {"edits": edits, "reasoning": f"deepseek-reflect@step{step}"}

    def apply(self, skill: str, patch: dict) -> str:
        from skillopt.optimizer.skill import apply_patch_with_report

        new_skill, _reports = apply_patch_with_report(skill, patch)
        return new_skill


def make_producer(
    *,
    items: list,
    data_root: str,
    out_root: str,
    mode: str = "single",
    workers: int = 8,
    max_completion_tokens: int = 4096,
    edit_budget: int = 4,
) -> CandidateProducer:
    """Build a DeepSeek-backed CandidateProducer over the given SpreadsheetBench items.

    Call :func:`configure_deepseek` first. ``items`` come from
    ``load_items(.../items.json)``; ``data_root`` is the dir holding the task xlsx.
    """
    from skillopt.envs.spreadsheetbench.adapter import SpreadsheetBenchAdapter

    adapter = SpreadsheetBenchAdapter(
        data_root=data_root,
        mode=mode,
        workers=workers,
        max_completion_tokens=max_completion_tokens,
        edit_budget=edit_budget,
    )
    p = SkillOptProducer(adapter=adapter, items=items, out_root=out_root)
    return CandidateProducer(propose=p.propose, apply=p.apply, score=p.score, probe=p.probe)
