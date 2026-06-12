"""Rejection ledger for Reject-Conditioned Variation (RCV, ADR-0007).

Every gate decision already paid for a full expensive rollout; this module
serializes those (direction, outcome) pairs so the proposer can consume them
in-context — the discrete-text analogue of gradient information. Pure data +
deterministic string rendering: zero API, zero filesystem.

Red lines honored here:
  - append-only record of loop outcomes; never mutates entries;
  - ``render`` is deterministic (same ledger state -> byte-identical string),
    ascending-score order (OPRO), char-budgeted by dropping OLDEST entries and
    folding them into an explicit count line (never silently truncates).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

_HEADER = "== 先前尝试与结果（按分数升序）=="
_MAX_FLIPS_SHOWN = 6


def skill_fingerprint(skill: str) -> str:
    """Same algorithm as ``BehaviorCandidate.skill_hash`` / adapter ``_skill_hash``
    so ledger entries can address the adapter's rollout cache."""
    return hashlib.sha256(skill.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class LedgerEntry:
    """One already-paid gate decision: the tried direction and its outcome."""

    step: int
    action: str                 # Archive.update action: "accept" | "reject"
    score: float
    parent_score: float
    cell: int = 0
    parent_cell: int = 0
    b: tuple[float, ...] = ()
    n_edits: int = 0
    edits_summary: str = ""     # the direction, human/LLM readable
    parent_hash: str = ""       # skill_fingerprint(parent) -> adapter cache key
    cand_hash: str = ""         # skill_fingerprint(candidate)
    task_flips: tuple[tuple[str, int, int], ...] = ()   # (task_id, before, after)
    lesson: str = ""            # optional distilled lesson (B-flag), evidence kept

    @property
    def delta(self) -> float:
        return self.score - self.parent_score


def _format_entry(e: LedgerEntry) -> str:
    label = "接受" if e.action == "accept" else "被拒"
    headline = e.lesson or e.edits_summary or f"{e.n_edits} edits"
    moved = "（行为未移动）" if e.cell == e.parent_cell else ""
    lines = [
        f"[step {e.step} | {label}] {headline}",
        f"  分数 {e.parent_score:.4g}→{e.score:.4g} ({e.delta:+.4g})；"
        f"cell {e.parent_cell}→{e.cell}{moved}",
    ]
    if e.task_flips:
        parts = [
            f"#{tid} {'对→错' if before > after else '错→对'}"
            for tid, before, after in e.task_flips[:_MAX_FLIPS_SHOWN]
        ]
        if len(e.task_flips) > _MAX_FLIPS_SHOWN:
            parts.append("…")
        lines.append("  翻转: " + ", ".join(parts))
    return "\n".join(lines)


@dataclass
class RejectionLedger:
    """Append-only record of gate decisions; renders the AVOID prompt fragment."""

    entries: list[LedgerEntry] = field(default_factory=list)

    def append(self, entry: LedgerEntry) -> None:
        self.entries.append(entry)

    def __len__(self) -> int:
        return len(self.entries)

    @property
    def n_accepts(self) -> int:
        return sum(1 for e in self.entries if e.action == "accept")

    @property
    def n_rejects(self) -> int:
        return sum(1 for e in self.entries if e.action == "reject")

    def _select_indices(self, top_m: int) -> list[int]:
        """Recency window plus the best accept and the most informative reject."""
        idxs = set(range(max(0, len(self.entries) - top_m), len(self.entries)))
        accept_idxs = [i for i, e in enumerate(self.entries) if e.action == "accept"]
        reject_idxs = [i for i, e in enumerate(self.entries) if e.action == "reject"]
        if accept_idxs:
            idxs.add(max(accept_idxs, key=lambda i: (self.entries[i].score, self.entries[i].step)))
        if reject_idxs:
            idxs.add(max(reject_idxs, key=lambda i: (abs(self.entries[i].delta), self.entries[i].step)))
        return sorted(idxs)

    def render(self, char_budget: int = 2000, top_m: int = 6) -> str:
        if not self.entries:
            return ""
        chosen = [(i, self.entries[i]) for i in self._select_indices(top_m)]
        # OPRO: ascending score so the best-scoring attempts sit closest to generation.
        chosen.sort(key=lambda pair: (pair[1].score, pair[1].step, pair[0]))

        def assemble(pairs: list[tuple[int, LedgerEntry]]) -> str:
            blocks = [_format_entry(e) for _, e in pairs]
            folded = len(self.entries) - len(pairs)
            out = [_HEADER, *blocks]
            if folded > 0:
                out.append(f"（另有 {folded} 条更早记录未列出）")
            return "\n".join(out)

        while True:
            text = assemble(chosen)
            if len(text) <= char_budget:
                return text
            if not chosen:
                return ""  # budget too small for even the fold line: degenerate, stay honest
            # Drop the OLDEST entry (smallest step, then insertion order).
            oldest = min(chosen, key=lambda pair: (pair[1].step, pair[0]))
            chosen.remove(oldest)
