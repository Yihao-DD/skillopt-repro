"""Prompt-side variation helpers for QD-over-Skills.

T004's full implementation will call the SkillOpt optimizer/merge stack. This
module keeps the local, zero-API contract small and testable: summarize the
archive for an optimizer prompt, and choose a bounded set of sampled candidate
edits while preserving an explicit novelty quota when such candidates exist.
"""
from __future__ import annotations

from dataclasses import dataclass

from qd.archive import Archive


@dataclass(frozen=True)
class VariationRequest:
    """Local contract for one archive-conditioned variation call."""

    n_candidates: int
    min_novel: int
    top_k: int | None = None
    top_p: float | None = None

    def __post_init__(self) -> None:
        if self.n_candidates < 1:
            raise ValueError("n_candidates must be >= 1")
        if self.min_novel < 0:
            raise ValueError("min_novel must be >= 0")
        if self.min_novel > self.n_candidates:
            raise ValueError("min_novel cannot exceed n_candidates")
        if self.top_k is not None and self.top_k < 1:
            raise ValueError("top_k must be >= 1")
        if self.top_p is not None and not 0.0 < self.top_p <= 1.0:
            raise ValueError("top_p must be in (0, 1]")


@dataclass(frozen=True)
class CandidateEdit:
    """One optimizer-sampled candidate edit/patch for local selection tests."""

    patch: dict
    parent_cell: int
    target_cell: int | None = None
    priority: float = 0.0

    @property
    def is_novel(self) -> bool:
        return self.target_cell is not None and self.target_cell != self.parent_cell


def archive_summary(archive: Archive) -> list[dict]:
    """Compact archive state for prompts/logging."""
    out = []
    for cell in archive.occupied_cells():
        elite = archive.elite(cell)
        if elite is None:
            continue
        out.append({"cell": cell, "score": elite.score, "step": elite.step})
    return out


def build_variation_prompt(archive: Archive, request: VariationRequest) -> str:
    """Build the archive-conditioned prompt fragment for T004 smoke tests."""
    lines = [
        "You are improving a SkillOpt skill document.",
        f"Return {request.n_candidates} bounded edit candidates.",
        f"At least {request.min_novel} candidates must target behavior unlike occupied archive cells.",
        "Archive elites:",
    ]
    for row in archive_summary(archive):
        lines.append(f"- cell={row['cell']} score={row['score']:.6g} step={row['step']}")
    if not archive.occupied_cells():
        lines.append("- empty archive")
    if request.top_k is not None:
        lines.append(f"Sampling hint: top_k={request.top_k}")
    if request.top_p is not None:
        lines.append(f"Sampling hint: top_p={request.top_p:.3g}")
    return "\n".join(lines)


def select_candidate_edits(candidates: list[CandidateEdit], request: VariationRequest) -> list[CandidateEdit]:
    """Select up to ``n_candidates`` edits, honoring novelty quota when possible.

    Candidates are already optimizer samples; this function only enforces the
    local T004 policy contract. Higher ``priority`` wins deterministically.
    """
    ordered = sorted(candidates, key=lambda c: c.priority, reverse=True)
    novel = [c for c in ordered if c.is_novel]
    selected: list[CandidateEdit] = novel[: request.min_novel]
    for cand in ordered:
        if len(selected) >= request.n_candidates:
            break
        if cand not in selected:
            selected.append(cand)
    return selected
