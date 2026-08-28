"""End-to-end pipeline tests over the seeded samples.

Kept to the fast paths (no pyright/tsc invocations): the full static+runtime
matrix is exercised by `agenttrace demo`, which `scripts/gate.sh` runs as the
seeded proof. Registry lookups hit the committed registry-cache.json.
"""

from pathlib import Path

import pytest

from agenttrace import config, otel, pipeline

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def otel_off():
    otel.configure("off")


@pytest.fixture(scope="session")
def cfg():
    return config.load(ROOT)


def run(cfg, name, **kwargs):
    target = next(t for t in cfg.targets if t.name == name)
    return pipeline.run_target(cfg, target, **kwargs)


def test_hallucinated_import_caught_statically(cfg):
    verdict = run(cfg, "report_gen")
    assert verdict.error_type == "hallucinated-import"
    assert verdict.checkpoint == "checkpoint.static.imports"


def test_hallucinated_import_detonates_at_runtime(cfg):
    verdict = run(cfg, "report_gen", skip_static=True)
    assert verdict.error_type == "hallucinated-import"
    assert verdict.checkpoint == "checkpoint.runtime.smoke"


def test_hallucinated_attr_detonates_at_runtime(cfg):
    verdict = run(cfg, "date_utils", skip_static=True)
    assert verdict.error_type == "hallucinated-api"
    assert verdict.checkpoint == "checkpoint.runtime.smoke"


def test_schema_mismatch_only_contract_catches(cfg):
    verdict = run(cfg, "user_api", skip_static=True)
    assert verdict.error_type == "schema-mismatch"
    assert verdict.checkpoint == "checkpoint.contract"
    assert verdict.detail["violations"], "expected pydantic violation details"


def test_passing_sample_stays_green(cfg):
    verdict = run(cfg, "weather_report", skip_static=True)
    assert verdict.passed


def test_verdict_expectation_logic(cfg):
    verdict = run(cfg, "user_api", skip_static=True)
    assert verdict.expected == "schema-mismatch"
    assert verdict.as_expected


def test_missing_target_is_harness_error_not_crash(cfg):
    """A declared target that isn't on disk is a config problem, not a defect in
    the code under test — and it must not take the whole gate down with an
    uncaught FileNotFoundError."""
    from agenttrace.config import Target

    ghost = Target(
        name="ghost",
        file="samples/python/does_not_exist.py",
        language="python",
        contract=None,
    )
    verdict = pipeline.run_target(cfg, ghost)
    assert verdict.error_type == "harness-error"
    assert verdict.checkpoint == "checkpoint.provenance"


def test_missing_target_does_not_abort_sibling_targets(cfg):
    """One missing file must not stop the remaining targets from being gated."""
    from agenttrace.config import Target

    ghost = Target(name="ghost", file="samples/python/does_not_exist.py", language="python")
    verdicts = [
        pipeline.run_target(cfg, ghost),
        run(cfg, "weather_report", skip_static=True),
    ]
    assert verdicts[0].error_type == "harness-error"
    assert verdicts[1].passed
