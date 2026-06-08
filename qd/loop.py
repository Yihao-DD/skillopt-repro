"""Integrated QD-over-Skills search loop (T008 / REORG S4–S7).

Threads ONE frozen baseline, ONE shared :class:`~qd.budget.EvalCounter`
(equal expensive-eval budget — BRIEF §4 red line), and ONE cosine edit-budget
schedule through both arms:

  K=1  → single-cell :class:`~qd.archive.Archive` == SkillOpt (regression C0,
         ADR-0001): every accept is a new best, parent == best == current.
  K>1  → MAP-Elites: each candidate's *trajectory* descriptor (ADR-0006, never
         skill text) picks a cell; per-cell strict ``>`` gate (empty cell
         auto-accepts = exploration).

The per-candidate pipeline :func:`produce_and_score_candidate` reuses SkillOpt's
pure helpers — cosine ``edit_budget`` (``optimizer.scheduler``) →
``rank_and_select`` (``optimizer.clip``; deterministic, zero-API when the edit
pool is within budget) → gate via :class:`Archive` (== ``evaluation.gate``).

The model/env is INJECTED via :class:`CandidateProducer` so the loop runs with
zero API in tests; the production adapter (later) wires the four callables to
SkillOpt's rollout / reflect / apply / eval.

Equal-budget invariant: ``run_search`` is driven by ``eval_budget`` and stops
the instant the shared counter reaches it, so K=1 and K>1 consume the *same*
number of expensive evaluations regardless of candidates-per-step.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from skillopt.optimizer.scheduler import build_scheduler  # pure (math only)

from qd.archive import Archive
from qd.budget import BehaviorCandidate, EvalCounter
from qd.descriptor import descriptor

Patch = dict
Traj = dict


def _default_rank_and_select(skill: str, patch: Patch, *, max_edits: int, update_mode: str = "patch") -> Patch:
    """Lazy wrapper over SkillOpt's ``rank_and_select`` (imports the model layer
    only when actually called, keeping ``import qd.loop`` model-free)."""
    from skillopt.optimizer.clip import rank_and_select

    return rank_and_select(skill, patch, max_edits, update_mode=update_mode)


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
    """One candidate: propose → ``rank_and_select`` (to ``edit_budget``) → apply →
    behavior cell (K>1) → expensive score (counted on the shared counter)."""
    patch = producer.propose(skill, step=step, target_cell=target_cell)
    selected = producer.rank_and_select(skill, patch, max_edits=edit_budget, update_mode=update_mode)
    cand_skill = producer.apply(skill, selected)

    if k == 1 or producer.probe is None:
        b: tuple[float, ...] = (0.0, 0.0)
        cell = 0
    else:
        d = descriptor(producer.probe(cand_skill))
        b, cell = d.b, d.cell

    bc = BehaviorCandidate(skill=cand_skill, b=tuple(b), cell=cell)
    scores = counter.evaluate_expensive([bc], selection_size, scorer=lambda c: producer.score(c.skill))
    score = scores[bc.skill_hash]

    n_edits = len(selected.get("edits", []))
    return CandidateResult(skill=cand_skill, score=score, edit_budget=edit_budget, n_edits=n_edits, cell=cell, b=tuple(b))


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
    parent_selector: Callable[[Archive], str] | None = None,
) -> SearchResult:
    """Run one arm until the shared counter spends ``eval_budget`` expensive evals.

    Both arms called with the same ``eval_budget`` consume exactly that many
    expensive evaluations (equal-budget red line). The cosine schedule anneals
    the edit budget over this arm's step horizon (``eval_budget // cps``).
    """
    if eval_budget < 1:
        raise ValueError("eval_budget must be >= 1")
    counter = counter if counter is not None else EvalCounter()
    cps = candidates_per_step if candidates_per_step is not None else (1 if k == 1 else k)
    total_steps = max(1, eval_budget // cps)
    scheduler = build_scheduler("cosine", max_lr=max_lr, min_lr=min_lr, total_steps=total_steps)
    archive = Archive(k=k, baseline_skill=baseline_skill, baseline_score=baseline_score, baseline_cell=baseline_cell)
    result = SearchResult(arm=("K=1" if k == 1 else f"K={k}"), archive=archive, counter=counter)

    step = 0
    while counter.expensive_evals < eval_budget:
        before = counter.expensive_evals
        step += 1
        edit_budget = scheduler.step()
        # K=1: parent == best == current (ADR-0001). K>1: default global best;
        # uncertainty/novelty cell selection plugs in here at S7.
        parent = parent_selector(archive) if parent_selector is not None else archive.best_skill
        for _ in range(cps):
            if counter.expensive_evals >= eval_budget:
                break
            cr = produce_and_score_candidate(
                parent, edit_budget=edit_budget, producer=producer, counter=counter,
                k=k, step=step, selection_size=selection_size, update_mode=update_mode,
            )
            upd = archive.update(cr.skill, cr.score, step=step, cell=cr.cell)
            result.history.append(StepRecord(step=step, action=upd.action, cell=upd.cell, candidate=cr))
        if counter.expensive_evals == before:
            break  # no new expensive evals this step (all cache hits) — avoid an infinite loop
    return result
