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

import os
from dataclasses import dataclass, field, replace

from qd.ledger import LedgerEntry, RejectionLedger, skill_fingerprint
from qd.loop import CandidateProducer

_AXIS_LEVELS = ("很低", "较低", "较高", "很高")
_NBINS = 4  # == qd.descriptor cell grid (cell = complexity_bin * 4 + op_density_bin)


def _verbalize_cell(cell: int) -> str:
    """AIM: turn a target cell into ADR-0006 axis language the optimizer can act on."""
    row, col = (cell // _NBINS) % _NBINS, cell % _NBINS
    return (f"瞄准行为格 {cell}：解法复杂度{_AXIS_LEVELS[row]}、"
            f"spreadsheet 操作密度{_AXIS_LEVELS[col]}的实现风格。")


def _flips(parent_results: list, cand_results: list, cap: int = 8) -> tuple:
    """Per-task correctness flips (parent vs candidate), from already-paid rollouts."""
    def _hardmap(results: list) -> dict:
        return {str(r.get("id")): int(float(r.get("hard", 0)) > 0.5) for r in results}

    pa, ca = _hardmap(parent_results), _hardmap(cand_results)
    flips = [(tid, pa[tid], ca[tid]) for tid in sorted(pa.keys() & ca.keys()) if pa[tid] != ca[tid]]
    flips.sort(key=lambda f: (f[2] - f[1], f[0]))  # regressions (对→错) first
    return tuple(flips[:cap])


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
    return skill_fingerprint(s)  # single hash source (qd.ledger) — same algo as before


@dataclass
class SkillOptProducer:
    """Faithful to SkillOpt Eq 2/3: candidates are GENERATED on D_tr (``gen_items``,
    propose) and GATED on D_sel (``sel_items``, score/probe). Caches one rollout
    per (skill, split); when ``gen_items is sel_items`` (merged mode) the two
    collapse to a single shared rollout (back-compat with the old single-set runs)."""

    adapter: object              # skillopt SpreadsheetBenchAdapter
    gen_items: list              # D_tr — generation/reflection set (propose)
    sel_items: list              # D_sel — validation-gate set (score/probe)
    out_root: str
    _cache: dict = field(default_factory=dict)   # (skill_hash, tag) -> rollout results

    def _tag(self, items: list) -> str:
        # Same object as sel_items -> "sel" (also the merged-mode single tag);
        # the generation set gets its own "gen" tag only when truly separate.
        return "sel" if items is self.sel_items else "gen"

    def _rollout(self, skill: str, items: list) -> list[dict]:
        tag = self._tag(items)
        key = (_skill_hash(skill), tag)
        if key not in self._cache:
            self._cache[key] = self.adapter.rollout(
                items, skill, os.path.join(self.out_root, tag, _skill_hash(skill)))
        return self._cache[key]

    def score(self, skill: str) -> float:
        from skillopt.utils import compute_score

        hard, _soft = compute_score(self._rollout(skill, self.sel_items))
        return float(hard)

    def probe(self, skill: str) -> list[dict]:
        # Behavior trajectories from the SEL rollout (cell ~ gate behavior): the
        # code DeepSeek generated per item, saved to predictions/<id>/code.py.
        results = self._rollout(skill, self.sel_items)
        pred_dir = os.path.join(self.out_root, self._tag(self.sel_items), _skill_hash(skill), "predictions")
        trajs = []
        for r in results:
            code_path = os.path.join(pred_dir, str(r.get("id", "")), "code.py")
            code = ""
            if os.path.exists(code_path):
                with open(code_path, encoding="utf-8") as f:
                    code = f.read()
            trajs.append({"code": code, "n_turns": r.get("n_turns", 1)})
        return trajs

    def _enrich(self, e: LedgerEntry) -> LedgerEntry:
        """Lazily attach per-task flips from the rollout cache. Parent was rolled
        out at generation (gen tag unless merged), candidate at the gate (sel).
        Under true split the two sets are disjoint, so flips degrade to empty."""
        if e.task_flips:
            return e
        ptag = "sel" if self.gen_items is self.sel_items else "gen"
        pk, ck = (e.parent_hash, ptag), (e.cand_hash, "sel")
        if pk not in self._cache or ck not in self._cache:
            return e
        return replace(e, task_flips=_flips(self._cache[pk], self._cache[ck]))

    def _rcv_context(self, *, target_cell: int | None, ledger: "RejectionLedger | None") -> str:
        """AVOID (ledger render + flips) + AIM (verbalized target cell), or ""."""
        parts = []
        if ledger is not None and len(ledger):
            enriched = RejectionLedger(entries=[self._enrich(e) for e in ledger.entries])
            parts.append(enriched.render())
        guidance = []
        if target_cell is not None:
            guidance.append(_verbalize_cell(target_cell))
        if parts:
            guidance.append("不要重复上述被拒方向的同类编辑；优先提出与失败方向语义不同的修改。")
        if guidance:
            parts.append("== 指引 ==\n" + "\n".join(guidance))
        return "\n".join(parts)

    def propose(self, skill: str, *, step: int, target_cell: int | None = None,
                ledger: "RejectionLedger | None" = None) -> dict:
        results = self._rollout(skill, self.gen_items)   # generate candidates on D_tr
        kwargs = {}
        ctx = self._rcv_context(target_cell=target_cell, ledger=ledger)
        if ctx:
            # Upstream-blessed injection channel: reflect renders this under
            # "## Previous Steps in This Epoch" — exactly the AVOID semantics.
            kwargs["step_buffer_context"] = ctx
        patches = self.adapter.reflect(
            results, skill, os.path.join(self.out_root, self._tag(self.gen_items), _skill_hash(skill)), **kwargs)
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
    items: list | None = None,
    gen_items: list | None = None,
    sel_items: list | None = None,
    data_root: str,
    out_root: str,
    mode: str = "single",
    workers: int = 8,
    max_completion_tokens: int = 4096,
    edit_budget: int = 4,
) -> CandidateProducer:
    """Build a DeepSeek-backed CandidateProducer over SpreadsheetBench items.

    Call :func:`configure_deepseek` first. Two modes:
      - faithful split (原文 Eq 2/3): pass ``gen_items`` (D_tr, generate) and
        ``sel_items`` (D_sel, gate);
      - merged/legacy: pass ``items`` (gen == sel == one set; old single-set runs).
    ``data_root`` is the dir holding the task xlsx.
    """
    if items is not None:
        gen_items = sel_items = items   # legacy single-set == merged mode
    if gen_items is None or sel_items is None:
        raise ValueError("make_producer needs either items=, or both gen_items= and sel_items=")
    from skillopt.envs.spreadsheetbench.adapter import SpreadsheetBenchAdapter

    adapter = SpreadsheetBenchAdapter(
        data_root=data_root,
        mode=mode,
        workers=workers,
        max_completion_tokens=max_completion_tokens,
        edit_budget=edit_budget,
    )
    p = SkillOptProducer(adapter=adapter, gen_items=gen_items, sel_items=sel_items, out_root=out_root)
    return CandidateProducer(propose=p.propose, apply=p.apply, score=p.score, probe=p.probe)
