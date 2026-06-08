"""Adaptive candidate-count and parent-cell scheduling for QD."""
from __future__ import annotations

import math
from dataclasses import dataclass


def is_plateau(scores: list[float], window: int = 3, min_delta: float = 0.0) -> bool:
    """Return True when the best-so-far has not improved over the last ``window`` steps.

    PRECONDITION: ``scores`` is the best-so-far sequence (monotone non-decreasing),
    as produced by the QD loop's global-best history. Plateau = the window's max did
    not exceed the value at the window start by more than ``min_delta``. (For a
    non-monotone input this "no new high in the window" reading still holds.)
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    if len(scores) < window + 1:
        return False
    recent = scores[-(window + 1):]
    return max(recent[1:]) <= recent[0] + min_delta


@dataclass(frozen=True)
class ScheduleDecision:
    n_candidates: int
    min_novel: int
    gamma: float
    plateau: bool


@dataclass
class PlateauScheduler:
    """Small heuristic scheduler for T007 smoke coverage."""

    base_n: int = 4
    plateau_n: int = 8
    base_gamma: float = 0.1
    plateau_gamma: float = 0.5
    novelty_fraction: float = 0.5
    window: int = 3

    def decide(self, best_scores: list[float]) -> ScheduleDecision:
        plateau = is_plateau(best_scores, window=self.window)
        n = self.plateau_n if plateau else self.base_n
        gamma = self.plateau_gamma if plateau else self.base_gamma
        min_novel = max(1, int(round(n * self.novelty_fraction))) if plateau else 0
        return ScheduleDecision(n_candidates=n, min_novel=min_novel, gamma=gamma, plateau=plateau)


def ucb_cell_score(
    predicted_gain: float,
    eval_count: int,
    total_evals: int,
    novelty: float,
    beta: float = 0.1,
    gamma: float = 0.1,
) -> float:
    """UCB-style cell score from SPEC §3.4."""
    n = max(1, int(eval_count))
    t = max(2, int(total_evals))
    return float(predicted_gain) + beta * math.sqrt(math.log(t) / n) + gamma * float(novelty)


def choose_parent_cell(cell_stats: dict[int, dict], gamma: float, beta: float = 0.1) -> int:
    """Choose the next cell to refine from local stats."""
    if not cell_stats:
        raise ValueError("cell_stats cannot be empty")
    total = sum(max(0, int(v.get("eval_count", 0))) for v in cell_stats.values()) + 1
    return max(
        cell_stats,
        key=lambda cell: (
            ucb_cell_score(
                predicted_gain=cell_stats[cell].get("predicted_gain", 0.0),
                eval_count=cell_stats[cell].get("eval_count", 0),
                total_evals=total,
                novelty=cell_stats[cell].get("novelty", 0.0),
                beta=beta,
                gamma=gamma,
            ),
            -cell,
        ),
    )
