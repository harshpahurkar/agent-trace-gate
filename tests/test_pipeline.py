"""End-to-end pipeline tests over the seeded samples.

Kept to the fast paths (no pyright/tsc invocations): the full static+runtime
matrix is exercised by `agenttrace demo`, which CI runs as the seeded-proof
job. Registry lookups hit the committed registry-cache.json when offline.
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
