"""Verdict model and the error-type taxonomy shared by every checkpoint.

The taxonomy is deliberately small and machine-readable — CI, the console
table, and span attributes all speak these exact strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# error_type taxonomy
HALLUCINATED_IMPORT = "hallucinated-import"  # package/module does not exist anywhere
HALLUCINATED_API = "hallucinated-api"        # module exists, the attribute/function doesn't
MISSING_DEPENDENCY = "missing-dependency"    # real package, just not installed here
TYPE_ERROR = "type-error"                    # static type error outside the two above
SCHEMA_MISMATCH = "schema-mismatch"          # ran fine, returned the wrong shape
CRASH = "crash"                              # unhandled exception at runtime
TIMEOUT = "timeout"                          # exceeded the sandbox wall-clock limit
HARNESS_ERROR = "harness-error"              # our own tooling failed, not the sample

CHECKPOINTS = (
    "checkpoint.provenance",
    "checkpoint.static.imports",
    "checkpoint.static.types",
    "checkpoint.runtime.smoke",
    "checkpoint.contract",
)


@dataclass
class Verdict:
    """Outcome of running the checkpoint pipeline over one file."""

    name: str
    file: str
    language: str
    verdict: str = "pass"          # "pass" | "fail"
    error_type: str | None = None  # one of the taxonomy strings when failing
    checkpoint: str | None = None  # which checkpoint decided the failure
    message: str = ""
    detail: dict = field(default_factory=dict)
    line: int | None = None        # best-known source line for CI annotations
    trace_id: str | None = None    # hex trace id, for Jaeger deep links
    expected: str | None = None    # seeded expectation from checkpoints.toml

    @property
    def passed(self) -> bool:
        return self.verdict == "pass"

    @property
    def outcome(self) -> str:
        """'pass' or the failing error_type — the string compared against `expected`."""
        return "pass" if self.passed else (self.error_type or "fail")

    @property
    def as_expected(self) -> bool:
        """True when the outcome matches the seeded expectation (or none is declared and it passed)."""
        if self.expected is None:
            return self.passed
        return self.outcome == self.expected
