"""Budget and deduplication helpers for expensive QD evaluation."""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class BehaviorCandidate:
    """Candidate with a cheap probe descriptor before full selection eval."""

    skill: str
    b: tuple[float, ...]
    cell: int
    probe_score: float = 0.0

    @property
    def skill_hash(self) -> str:
        return hashlib.sha256(self.skill.encode("utf-8")).hexdigest()[:16]


def behavior_distance(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    if len(a) != len(b):
        raise ValueError("behavior vectors must have the same dimension")
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def deduplicate_by_behavior(candidates: list[BehaviorCandidate], epsilon: float = 0.0) -> list[BehaviorCandidate]:
    """Cluster candidates by behavior cell/radius, keeping best probe score."""
    if epsilon < 0:
        raise ValueError("epsilon must be >= 0")
    reps: list[BehaviorCandidate] = []
    for cand in sorted(candidates, key=lambda c: c.probe_score, reverse=True):
        duplicate = any(cand.cell == rep.cell and behavior_distance(cand.b, rep.b) <= epsilon for rep in reps)
        if not duplicate:
            reps.append(cand)
    return reps


@dataclass
class EvalCounter:
    """Count cheap probe work and expensive selection evaluations."""

    cheap_rollouts: int = 0
    expensive_rollouts: int = 0
    expensive_evals: int = 0
    cache_hits: int = 0
    _cache: dict[str, float] = field(default_factory=dict)

    def record_probe(self, n_candidates: int, probe_size: int) -> None:
        self.cheap_rollouts += int(n_candidates) * int(probe_size)

    def evaluate_expensive(
        self,
        candidates: list[BehaviorCandidate],
        selection_size: int,
        scorer: Callable[[BehaviorCandidate], float],
    ) -> dict[str, float]:
        """Score candidates with a hash cache and count only cache misses."""
        scores: dict[str, float] = {}
        for cand in candidates:
            key = cand.skill_hash
            if key in self._cache:
                self.cache_hits += 1
                scores[key] = self._cache[key]
                continue
            score = scorer(cand)
            self._cache[key] = score
            scores[key] = score
            self.expensive_evals += 1
            self.expensive_rollouts += int(selection_size)
        return scores
