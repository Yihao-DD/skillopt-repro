"""Integrated QD-over-Skills search loop (T008 / REORG S4–S7).

Threads ONE frozen baseline, ONE shared :class:`~qd.budget.EvalCounter`
(equal expensive-eval budget — BRIEF §4 red line), and ONE cosine edit-budget
schedule through both arms:

  K=1  → single-cell :class:`~qd.archive.Archive` == SkillOpt (regression C0,
         ADR-0001): every accept is a new best, parent == best == current.
  K>1  → MAP-Elites: a UCB rule (``qd.scheduler.choose_parent_cell``) picks the
         parent cell; each candidate's *trajectory* descriptor (ADR-0006, never
         skill text) picks a target cell; behavior-duplicate candidates are
         dropped BEFORE the expensive eval (``qd.budget.deduplicate_by_behavior``)
         so the budget buys distinct behaviors; per-cell strict ``>`` gate.

The per-candidate pipeline reuses SkillOpt's pure helpers — cosine ``edit_budget``
(``optimizer.scheduler``) → ``rank_and_select`` (``optimizer.clip``; deterministic,
zero-API when the edit pool is within budget) → gate via :class:`Archive`
(== ``evaluation.gate``). It is split into a cheap propose stage
(:func:`_propose_candidate`) and an expensive, counted score stage
(:func:`_score_proposed`) so K>1 can dedup between the two.

The model/env is INJECTED via :class:`CandidateProducer` so the loop runs with
zero API in tests; the production adapter (later) wires the four callables to
SkillOpt's rollout / reflect / apply / eval.

Equal-budget invariant: ``run_search`` is driven by ``eval_budget`` and stops the
instant the shared counter reaches it, so K=1 and K>1 consume the *same* number
of expensive evaluations regardless of candidates-per-step or dedup.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from skillopt.optimizer.scheduler import build_scheduler  # pure (math only)

from qd.archive import Archive
from qd.budget import BehaviorCandidate, EvalCounter, deduplicate_by_behavior
from qd.descriptor import descriptor
from qd.ledger import LedgerEntry, RejectionLedger, skill_fingerprint
from qd.scheduler import choose_parent_cell

Patch = dict
Traj = dict


def _default_rank_and_select(skill: str, patch: Patch, *, max_edits: int, update_mode: str = "patch") -> Patch:
    """Lazy wrapper over SkillOpt's ``rank_and_select`` (imports the model layer
    only when actually called, keeping ``import qd.loop`` model-free)."""
    from skillopt.optimizer.clip import rank_and_select

    return rank_and_select(skill, patch, max_edits, update_mode=update_mode)


def _patch_summary(patch: Patch | None) -> str:
    """Compact, schema-agnostic summary of the tried direction (ledger headline)."""
    edits = (patch or {}).get("edits", []) or []
    parts = []
    for e in edits[:2]:
        if isinstance(e, dict):
            text = e.get("text") or e.get("code") or " ".join(str(v) for v in e.values())
        else:
            text = e
        parts.append(str(text)[:60])
    out = "; ".join(parts)
    if len(edits) > 2:
        out += f"; …(+{len(edits) - 2})"
    return out


@dataclass
class CandidateProducer:
    """Injected model/env contract (production = SkillOpt adapter; tests = fakes).

    All scores are in *metric space* (already projected to hard / soft / mixed),
    matching :func:`skillopt.evaluation.gate.evaluate_gate`'s ``current_score``.
    """

    propose: Callable[..., Patch]          # (skill, *, step, target_cell) -> patch {edits:[...]}
    apply: Callable[[str, Patch], str]     # (skill, selected_patch) -> new skill
    score: Callable[[str], float]          # (skill) -> selection-set metric score
    probe: Optional[Callable[[str], list[Traj]]] = None   # (skill) -> probe trajs; K>1 only
    rank_and_select: Callable[..., Patch] = _default_rank_and_select
    # Epoch-wise slow update (原文 §3.6); both None => no slow update (flat loop).
    slow_update: Optional[Callable[[str, str], str]] = None   # (prev_epoch_skill, curr_best) -> guidance
    apply_slow: Optional[Callable[[str, str], str]] = None    # (skill, guidance) -> skill+guidance


@dataclass(frozen=True)
class ProposedCandidate:
    """A candidate after the cheap pipeline (propose → rank_and_select → apply →
    descriptor), before the expensive selection-set score."""

    skill: str
    b: tuple[float, ...]
    cell: int
    edit_budget: int
    n_edits: int
    parent_cell: int
    patch: Patch | None = None   # the selected patch (RCV ledger records the direction)


@dataclass(frozen=True)
class CandidateResult:
    skill: str
    score: float
    edit_budget: int
    n_edits: int
    cell: int
    b: tuple[float, ...]


@dataclass(frozen=True)
class StepRecord:
    step: int
    action: str          # Archive.update action: "accept" | "reject"
    cell: int
    candidate: CandidateResult


@dataclass
class SearchResult:
    arm: str
    archive: Archive
    counter: EvalCounter
    history: list[StepRecord] = field(default_factory=list)
    n_proposed: int = 0          # cheap proposals generated (>= expensive_evals when dedup fires)
    cross_cell_pickups: int = 0  # accepted candidates whose target cell != parent cell
    precheck_skips: int = 0      # RCV pre_check skipped candidates (never spent budget)
    ledger: RejectionLedger | None = None  # RCV outcome record (None when off / K=1)

    @property
    def n_occupied(self) -> int:
        return len(self.archive.occupied_cells())

    @property
    def expensive_evals(self) -> int:
        return self.counter.expensive_evals

    @property
    def best_score(self) -> float:
        return self.archive.best_score

    @property
    def edit_budgets(self) -> list[int]:
        return [r.candidate.edit_budget for r in self.history]


def _propose_candidate(
    skill: str,
    *,
    parent_cell: int,
    edit_budget: int,
    producer: CandidateProducer,
    k: int,
    step: int,
    target_cell: int | None = None,
    update_mode: str = "patch",
    ledger: RejectionLedger | None = None,
) -> ProposedCandidate:
    """Cheap stage: propose → ``rank_and_select`` (to ``edit_budget``) → apply →
    behavior cell (K>1). No expensive eval here. The ledger kwarg is forwarded to
    ``propose`` ONLY when present, so pre-RCV producers keep their old contract."""
    if ledger is not None:
        patch = producer.propose(skill, step=step, target_cell=target_cell, ledger=ledger)
    else:
        patch = producer.propose(skill, step=step, target_cell=target_cell)
    selected = producer.rank_and_select(skill, patch, max_edits=edit_budget, update_mode=update_mode)
    cand_skill = producer.apply(skill, selected)
    if k == 1 or producer.probe is None:
        b: tuple[float, ...] = (0.0, 0.0)
        cell = 0
    else:
        d = descriptor(producer.probe(cand_skill))
        b, cell = d.b, d.cell
    return ProposedCandidate(
        skill=cand_skill, b=tuple(b), cell=cell, edit_budget=edit_budget,
        n_edits=len(selected.get("edits", [])), parent_cell=parent_cell,
        patch=selected,
    )


def _score_proposed(pc: ProposedCandidate, *, producer: CandidateProducer, counter: EvalCounter, selection_size: int) -> float:
    """Expensive stage: counted on the shared counter (cache-hit on identical skill)."""
    bc = BehaviorCandidate(skill=pc.skill, b=pc.b, cell=pc.cell)
    scores = counter.evaluate_expensive([bc], selection_size, scorer=lambda c: producer.score(c.skill))
    return scores[bc.skill_hash]


def produce_and_score_candidate(
    skill: str,
    *,
    edit_budget: int,
    producer: CandidateProducer,
    counter: EvalCounter,
    k: int,
    step: int,
    selection_size: int = 1,
    target_cell: int | None = None,
    update_mode: str = "patch",
) -> CandidateResult:
    """One candidate: cheap propose + expensive score (K=1 convenience / public API)."""
    pc = _propose_candidate(skill, parent_cell=0, edit_budget=edit_budget, producer=producer,
                            k=k, step=step, target_cell=target_cell, update_mode=update_mode)
    score = _score_proposed(pc, producer=producer, counter=counter, selection_size=selection_size)
    return CandidateResult(skill=pc.skill, score=score, edit_budget=pc.edit_budget,
                           n_edits=pc.n_edits, cell=pc.cell, b=pc.b)


def _select_parent_cell(archive: Archive, cell_visits: dict[int, int], *, gamma: float, beta: float) -> int:
    """UCB over occupied cells: predicted_gain = cell elite score, exploration by
    visit count (``qd.scheduler.choose_parent_cell``)."""
    stats = {
        c: {"predicted_gain": archive.elite(c).score, "eval_count": cell_visits.get(c, 0), "novelty": 0.0}
        for c in archive.occupied_cells()
    }
    return choose_parent_cell(stats, gamma=gamma, beta=beta)


def run_search(
    *,
    k: int,
    baseline_skill: str,
    baseline_score: float,
    eval_budget: int,
    producer: CandidateProducer,
    counter: EvalCounter | None = None,
    max_lr: int = 4,
    min_lr: int = 2,
    candidates_per_step: int | None = None,
    selection_size: int = 1,
    update_mode: str = "patch",
    baseline_cell: int = 0,
    dedup_epsilon: float = 0.0,
    parent_gamma: float = 0.1,
    parent_beta: float = 0.1,
    use_ledger: bool = False,
    pre_check: Optional[Callable[[ProposedCandidate, RejectionLedger], bool]] = None,
    num_epochs: int = 1,
) -> SearchResult:
    """Run one arm until the shared counter spends ``eval_budget`` expensive evals.

    Both arms called with the same ``eval_budget`` consume exactly that many
    expensive evaluations (equal-budget red line). The cosine schedule anneals the
    edit budget over this arm's step horizon (``eval_budget // cps``).

    RCV (ADR-0007): ``use_ledger=True`` records every gate outcome in a
    :class:`~qd.ledger.RejectionLedger` and forwards it to ``producer.propose``.
    ``pre_check(pc, ledger) -> bool`` may veto a candidate BEFORE the expensive
    eval (False = skip; fail-open on exceptions; a step never skips ALL
    survivors, so the equal budget always fills). K=1 IGNORES both flags —
    red line C0: the K=1 arm stays byte-for-byte SkillOpt.
    """
    if eval_budget < 1:
        raise ValueError("eval_budget must be >= 1")
    if k > 1 and pre_check is not None and not use_ledger:
        raise ValueError("pre_check requires use_ledger=True (it vets against the ledger)")
    counter = counter if counter is not None else EvalCounter()
    cps = candidates_per_step if candidates_per_step is not None else (1 if k == 1 else k)
    grid_cells = 1 if k == 1 else 16  # K=1 == single-cell SkillOpt; K>1 = full descriptor grid (nbins=4 -> 16)
    total_steps = max(1, eval_budget // cps)
    scheduler = build_scheduler("cosine", max_lr=max_lr, min_lr=min_lr, total_steps=total_steps)
    archive = Archive(k=grid_cells, baseline_skill=baseline_skill, baseline_score=baseline_score, baseline_cell=baseline_cell)
    ledger = RejectionLedger() if (use_ledger and k > 1) else None
    result = SearchResult(arm=("K=1" if k == 1 else f"K={k}"), archive=archive, counter=counter, ledger=ledger)
    cell_visits: dict[int, int] = {}

    step = 0
    max_steps = eval_budget * 4 + 16  # hard cap: avoid an infinite loop if the producer can't make new candidates
    per_epoch = max(1, eval_budget // num_epochs)

    for epoch in range(num_epochs):
        # Slow update (原文 §3.6) compares this epoch's STARTING skill vs its end-of-epoch best.
        epoch_start_skill = archive.best_skill if archive.occupied_cells() else baseline_skill
        epoch_target = eval_budget if epoch == num_epochs - 1 else min(eval_budget, (epoch + 1) * per_epoch)
        stalls = 0
        while counter.expensive_evals < epoch_target and step < max_steps:
            before = counter.expensive_evals
            step += 1
            edit_budget = scheduler.step()

            if k == 1:
                # parent == best == current (ADR-0001); one candidate per step.
                cr = produce_and_score_candidate(
                    archive.best_skill, edit_budget=edit_budget, producer=producer, counter=counter,
                    k=k, step=step, selection_size=selection_size, update_mode=update_mode,
                )
                upd = archive.update(cr.skill, cr.score, step=step, cell=cr.cell)
                result.history.append(StepRecord(step=step, action=upd.action, cell=upd.cell, candidate=cr))
            else:
                parent_cell = _select_parent_cell(archive, cell_visits, gamma=parent_gamma, beta=parent_beta)
                cell_visits[parent_cell] = cell_visits.get(parent_cell, 0) + 1
                parent_elite = archive.elite(parent_cell)
                parent, parent_score = parent_elite.skill, parent_elite.score
                proposals = [
                    _propose_candidate(parent, parent_cell=parent_cell, edit_budget=edit_budget,
                                       producer=producer, k=k, step=step, update_mode=update_mode,
                                       ledger=ledger)
                    for _ in range(cps)
                ]
                result.n_proposed += len(proposals)
                by_skill = {p.skill: p for p in proposals}
                survivors = deduplicate_by_behavior(
                    [BehaviorCandidate(skill=p.skill, b=p.b, cell=p.cell) for p in proposals], dedup_epsilon
                )
                evaluated_this_step = 0
                for idx, bc in enumerate(survivors):
                    if counter.expensive_evals >= epoch_target:
                        break
                    pc = by_skill[bc.skill]
                    if pre_check is not None and ledger is not None:
                        try:
                            skip = not bool(pre_check(pc, ledger))
                        except Exception:
                            skip = False  # fail-open: infrastructure must never lose a candidate
                        # Never skip ALL survivors in a step (the equal budget must fill).
                        if skip and evaluated_this_step == 0 and idx == len(survivors) - 1:
                            skip = False
                        if skip:
                            result.precheck_skips += 1
                            continue
                    evaluated_this_step += 1
                    score = _score_proposed(pc, producer=producer, counter=counter, selection_size=selection_size)
                    upd = archive.update(pc.skill, score, step=step, cell=pc.cell)
                    cr = CandidateResult(skill=pc.skill, score=score, edit_budget=pc.edit_budget,
                                         n_edits=pc.n_edits, cell=pc.cell, b=pc.b)
                    result.history.append(StepRecord(step=step, action=upd.action, cell=upd.cell, candidate=cr))
                    if upd.action == "accept" and pc.cell != pc.parent_cell:
                        result.cross_cell_pickups += 1
                    if ledger is not None:
                        ledger.append(LedgerEntry(
                            step=step, action=upd.action, score=score, parent_score=parent_score,
                            cell=pc.cell, parent_cell=pc.parent_cell, b=pc.b,
                            n_edits=pc.n_edits, edits_summary=_patch_summary(pc.patch),
                            parent_hash=skill_fingerprint(parent), cand_hash=skill_fingerprint(pc.skill),
                        ))

            # Spend the FULL equal budget: tolerate unproductive (all-cache-hit) steps
            # by resampling; give up only after several consecutive stalls.
            if counter.expensive_evals == before:
                stalls += 1
                if stalls >= 8:
                    break
            else:
                stalls = 0

        # ── Epoch boundary: slow update (原文 §3.6, default force-accept) ──────
        # Inject longitudinal guidance into the best elite UNCONDITIONALLY (no gate).
        # num_epochs==1 => this never fires (flat loop == prior behavior).
        if num_epochs > 1 and producer.slow_update is not None and archive.occupied_cells():
            guidance = producer.slow_update(epoch_start_skill, archive.best_skill)
            if guidance:
                # 原文 slow lesson 是全局领域知识 → 注入 ALL occupied elites（不只 best），
                # 使下个 epoch 任何 UCB-parent 都带 lesson（对齐原文 current 带 lesson）。
                # force-accept: 保各格原 score、只换 skill 文本（原文不重评）。
                for cell in archive.occupied_cells():
                    e = archive.elite(cell)
                    injected = (producer.apply_slow(e.skill, guidance)
                                if producer.apply_slow is not None else e.skill + guidance)
                    archive.force_set(cell, injected, e.score, step)
    return result
