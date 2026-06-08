"""Company-facing launch + packaging entry points.

- ``run_experiment`` — one-command full / preflight runner (.env-driven API swap).
- ``make_bundle``    — build the self-contained air-gapped release zip.

Importable as a package so the zero-API test can exercise ``resolve_plan`` directly
(``conftest.py`` puts the repo root on ``sys.path``).
"""
