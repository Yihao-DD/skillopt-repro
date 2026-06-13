"""MAP-Elites archive + selection operator ``U``.

At K=1 the archive has a single cell whose elite plays both SkillOpt's
``current`` and ``best`` — they coincide in SkillOpt's step loop (see
``QD-over-Skills/decisions/ADR-0001``). The per-cell acceptance rule is the
strict gate ``f(candidate) > elite_score`` (ties reject), which at K=1 matches
``skillopt.evaluation.gate.evaluate_gate``'s ``accept_new_best`` / ``reject``.

K>1 (multi-cell descriptor binning) lands in T005.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Elite:
    """One MAP-Elites cell incumbent."""

    skill: str
    score: float
    step: int


@dataclass(frozen=True)
class UpdateResult:
    """Outcome of one ``Archive.update`` call.

    ``action`` is QD-native: ``"accept"`` (new/replacing cell elite) or
    ``"reject"``. K=1 correspondence to SkillOpt: ``"accept"`` ↔
    ``"accept_new_best"``, ``"reject"`` ↔ ``"reject"``.
    """

    action: str
    cell: int = 0
    previous_score: float | None = None
    new_score: float | None = None


class Archive:
    """MAP-Elites archive.

    K=1 keeps the original SkillOpt reduction used by T001. K>1 stores one
    strict-gated elite per behavior cell: an empty cell accepts immediately;
    an occupied cell accepts only when ``cand_score > elite.score``.
    """

    def __init__(
        self,
        k: int = 1,
        baseline_skill: str | None = None,
        baseline_score: float | None = None,
        baseline_cell: int = 0,
    ) -> None:
        if k < 1:
            raise ValueError("k must be >= 1")
        self.k = k
        self._elites: dict[int, Elite] = {}
        # Seed the frozen baseline elite ONLY when explicitly provided (None sentinel):
        # an unparameterised Archive() is truly EMPTY (no phantom skill=''/score=-1 elite).
        # ``baseline_cell`` lets the loop seed the baseline into its descriptor cell for
        # K>1 (normalised to 0 at K=1), supporting the shared-baseline requirement.
        if baseline_skill is not None and baseline_score is not None:
            self._elites[self._normalize_cell(baseline_cell)] = Elite(
                skill=baseline_skill, score=baseline_score, step=0
            )

    def update(self, candidate_skill: str, cand_score: float, step: int, cell: int = 0) -> UpdateResult:
        """Per-cell strict gate (ties reject). K=1 -> single cell (cell 0)."""
        cell = self._normalize_cell(cell)
        old = self._elites.get(cell)
        if old is None or cand_score > old.score:
            self._elites[cell] = Elite(skill=candidate_skill, score=cand_score, step=step)
            return UpdateResult(
                action="accept",
                cell=cell,
                previous_score=None if old is None else old.score,
                new_score=cand_score,
            )
        return UpdateResult(
            action="reject",
            cell=cell,
            previous_score=old.score,
            new_score=old.score,
        )

    def force_set(self, cell: int, skill: str, score: float, step: int) -> None:
        """Unconditional set of a cell's elite (no gate). For the epoch-wise
        slow update's default force-accept mode (原文 §3.6): longitudinal guidance
        is injected into the best skill without passing the step-level gate."""
        self._elites[self._normalize_cell(cell)] = Elite(skill=skill, score=score, step=step)

    @property
    def best_cell(self) -> int:
        """Cell holding the global best elite (ties: earliest step)."""
        if not self._elites:
            raise ValueError("archive is empty")
        return max(self._elites, key=lambda c: (self._elites[c].score, -self._elites[c].step))

    def _normalize_cell(self, cell: int) -> int:
        cell = int(cell)
        if self.k == 1:
            return 0
        if not 0 <= cell < self.k:
            raise ValueError(f"cell must be in [0, {self.k}), got {cell}")
        return cell

    def elite(self, cell: int) -> Elite | None:
        """Return the current elite for ``cell`` if occupied."""
        return self._elites.get(self._normalize_cell(cell))

    def occupied_cells(self) -> tuple[int, ...]:
        return tuple(sorted(self._elites))

    def scores(self) -> dict[int, float]:
        return {cell: elite.score for cell, elite in self._elites.items()}

    @property
    def global_best(self) -> Elite:
        if not self._elites:
            raise ValueError("archive is empty")
        return max(self._elites.values(), key=lambda e: (e.score, -e.step))

    # K=1: the single cell's elite plays both SkillOpt's `current` and `best`.
    @property
    def current_skill(self) -> str:
        return self.global_best.skill

    @property
    def current_score(self) -> float:
        return self.global_best.score

    @property
    def best_skill(self) -> str:
        return self.global_best.skill

    @property
    def best_score(self) -> float:
        return self.global_best.score

    @property
    def best_step(self) -> int:
        return self.global_best.step
