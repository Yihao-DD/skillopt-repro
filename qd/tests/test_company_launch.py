"""Zero-API guards for the company entry points (scripts/run_experiment + make_bundle).

These never touch the model or the network — they pin (a) the launcher's full vs
preflight presets and override precedence, and (b) the bundler's exclude rules,
which are SECURITY-critical: ``.env`` must never enter the release zip.
"""
import pytest

from scripts.make_bundle import _included
from scripts.run_experiment import PRESETS, build_parser, main, resolve_plan


def test_full_preset_uses_whole_split_and_equal_budget():
    # Arrange / Act
    plan = resolve_plan(full=True)
    # Assert
    assert plan.mode == "full"
    assert plan.n is None          # None => all 280 test items, resolved at run time
    assert plan.eval_budget == 12  # per arm — the equal-budget red line
    assert plan.k == 4


def test_preflight_preset_is_small_and_cheap():
    plan = resolve_plan(full=False)
    assert plan.mode == "preflight"
    assert plan.n == 2
    assert plan.eval_budget == 6
    assert plan.k == 4


def test_cli_overrides_win_over_presets():
    plan = resolve_plan(full=True, n=5, eval_budget=3, k=1)
    assert (plan.n, plan.eval_budget, plan.k) == (5, 3, 1)


def test_presets_are_well_formed():
    for mode in ("full", "preflight"):
        assert set(PRESETS[mode]) == {"n", "eval_budget", "k"}


def test_parser_accepts_full_preflight_and_dry_run():
    args = build_parser().parse_args(["--full", "--dry-run"])
    assert args.full and args.dry_run and not args.preflight


def test_bundle_excludes_the_secret_and_runtime_bulk():
    # The .env secret and bulky run-time artifacts must NEVER ship.
    assert not _included(".env")
    assert not _included("runs/val/summary.json")
    assert not _included("SkillOpt/outputs/anything.json")
    assert not _included("SkillOpt/__pycache__/x.pyc")
    assert not _included("qd/x.pyc")


def test_bundle_drops_non_spreadsheetbench_benchmarks_but_keeps_ssb():
    # Other benchmarks are dead weight for this run; SpreadsheetBench must stay.
    assert not _included("SkillOpt/data/searchqa_split/test/items.json")
    assert not _included("SkillOpt/data/alfworld_path_split/x")
    assert _included("SkillOpt/data/spreadsheetbench_split/test/items.json")
    assert _included("SkillOpt/data/spreadsheetbench_verified_400/1/x.xlsx")
    assert _included("SkillOpt/data/README.md")


def test_bundle_keeps_the_fork_engine_and_repo_code():
    assert _included("SkillOpt/skillopt/__init__.py")
    assert _included("scripts/run_experiment.py")
    assert _included("qd/loop.py")
    assert _included(".env.example")  # the template the company copies to .env


def test_bundle_excludes_env_variants_and_nested_env_but_keeps_templates():
    # A nested or variant .env must NEVER ship; only the safe templates do.
    assert not _included("SkillOpt/.env")
    assert not _included(".env.local")
    assert not _included("a/b/.env")
    assert not _included(".envrc")
    assert _included(".env.example")
    assert _included(".env.sample")


def test_main_requires_an_explicit_mode_flag():
    # A forgotten flag must NOT silently run partial — it must error out.
    with pytest.raises(SystemExit):
        main([])
