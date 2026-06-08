"""Build the self-contained air-gapped release zip for the company full run.

Packages the repo + the local-only substrate (the gitignored ``SkillOpt/`` fork
engine + materialized SpreadsheetBench data + ``.env.example``) into ONE zip the
company unzips on an air-gapped box, then: edit ``.env`` ->
``python scripts/run_experiment.py --full``.

EXCLUDES secrets + bulk so the zip stays lean and safe:
  - ``.env`` (the only secret), ``.git`` / ``SkillOpt/.git`` / ``.venv`` / ``dist`` / ``runs``,
    ``__pycache__`` / ``.pytest_cache`` / ``*.egg-info`` / ``*.pyc``,
  - the fork's ``ckpt`` / ``outputs`` (run-time only),
  - every NON-SpreadsheetBench benchmark under ``SkillOpt/data/``.

Prints + writes a sha256 next to the zip for the integrity hand-off (paste it in
the delivery message; the company checks it after download).

  python scripts/make_bundle.py                  # -> dist/skillopt-fullrun-<git-sha>.zip
  python scripts/make_bundle.py --tag redo-v1    # custom tag
  python scripts/make_bundle.py --dry-run        # list count + total size, write nothing
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Directory names pruned wherever they appear in the tree.
EXCLUDE_DIR_NAMES = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules",
                     "dist", ".idea", ".vscode", ".mypy_cache", ".ruff_cache"}
# Path prefixes (posix, relative to ROOT) pruned entirely.
EXCLUDE_PREFIXES = ("runs/", "dist/", "SkillOpt/ckpt/", "SkillOpt/outputs/")
EXCLUDE_SUFFIXES = (".pyc", ".pyo")
# Any .env / .env.<variant> / .envrc at ANY depth is a potential secret — exclude by
# basename so a nested e.g. SkillOpt/.env can never ship; keep only safe templates.
_ENV_KEEP = {".env.example", ".env.sample", ".env.template"}


def _included(rel: str) -> bool:
    """rel is a posix path relative to ROOT. True => goes in the bundle."""
    base = rel.rsplit("/", 1)[-1]
    if base == ".envrc" or ((base == ".env" or base.startswith(".env.")) and base not in _ENV_KEEP):
        return False
    if rel.endswith(EXCLUDE_SUFFIXES):
        return False
    if rel.startswith(EXCLUDE_PREFIXES):
        return False
    if rel.endswith(".egg-info") or ".egg-info/" in rel:
        return False
    # Under SkillOpt/data, keep only SpreadsheetBench (+ the data README); drop the
    # other benchmarks (searchqa/alfworld/docvqa/... not needed for this run).
    if rel.startswith("SkillOpt/data/"):
        seg = rel[len("SkillOpt/data/"):].split("/", 1)[0]
        if seg != "README.md" and not seg.startswith("spreadsheetbench"):
            return False
    return True


def collect_files() -> list[str]:
    """Walk ROOT, prune excluded dirs in-place, return included posix rel paths."""
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIR_NAMES]
        for name in filenames:
            rel = os.path.relpath(os.path.join(dirpath, name), ROOT).replace(os.sep, "/")
            if _included(rel):
                out.append(rel)
    return sorted(out)


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=ROOT, text=True).strip() or "local"
    except Exception:  # noqa: BLE001
        return "local"


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build the air-gapped release zip.")
    p.add_argument("--tag", default=None, help="release tag (default: git short SHA)")
    p.add_argument("--dry-run", action="store_true", help="list count + size, write nothing")
    args = p.parse_args(argv)

    files = collect_files()
    total = sum(os.path.getsize(os.path.join(ROOT, f)) for f in files)
    print(f"files: {len(files)}   uncompressed: {total / 1e6:.1f} MB")
    fork = sum(os.path.getsize(os.path.join(ROOT, f)) for f in files if f.startswith("SkillOpt/"))
    print(f"  of which SkillOpt/ (fork+data): {fork / 1e6:.1f} MB")
    if args.dry_run:
        print("DRY-RUN: nothing written. Drop --dry-run to build the zip.")
        return 0

    tag = args.tag or _git_sha()
    stem = f"skillopt-fullrun-{tag}"
    dist = os.path.join(ROOT, "dist")
    os.makedirs(dist, exist_ok=True)
    zip_path = os.path.join(dist, f"{stem}.zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for rel in files:
            zf.write(os.path.join(ROOT, rel), arcname=f"{stem}/{rel}")

    digest = _sha256(zip_path)
    with open(zip_path + ".sha256", "w", encoding="utf-8") as fh:
        fh.write(f"{digest}  {stem}.zip\n")
    print(f"\nwrote {zip_path}  ({os.path.getsize(zip_path) / 1e6:.1f} MB)")
    print(f"sha256: {digest}")
    print("Hand the company the zip + paste this sha256 in the delivery message.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
