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
class UpdateResult:
    """Outcome of one ``Archive.update`` call.

    ``action`` is QD-native: ``"accept"`` (new/replacing cell elite) or
    ``"reject"``. K=1 correspondence to SkillOpt: ``"accept"`` ↔
    ``"accept_new_best"``, ``"reject"`` ↔ ``"reject"``.
    """

    action: str
    cell: int = 0


class Archive:
    """MAP-Elites archive. K=1 = a single cell (reduces to SkillOpt)."""

    def __init__(self, k: int = 1, baseline_skill: str = "", baseline_score: float = -1.0) -> None:
        self.k = k
        # K=1: one cell; its elite is (skill, score, step) and plays current==best.
        self._elite_skill = baseline_skill
        self._elite_score = baseline_score
        self._elite_step = 0

    def update(self, candidate_skill: str, cand_score: float, step: int) -> UpdateResult:
        """Per-cell strict gate (ties reject). K=1 → single cell (cell 0)."""
        if cand_score > self._elite_score:
            self._elite_skill = candidate_skill
            self._elite_score = cand_score
            self._elite_step = step
            return UpdateResult(action="accept", cell=0)
        return UpdateResult(action="reject", cell=0)

    # K=1: the single cell's elite plays both SkillOpt's `current` and `best`.
    @property
    def current_skill(self) -> str:
        return self._elite_skill

    @property
    def current_score(self) -> float:
        return self._elite_score

    @property
    def best_skill(self) -> str:
        return self._elite_skill

    @property
    def best_score(self) -> float:
        return self._elite_score

    @property
    def best_step(self) -> int:
        return self._elite_step
