"""Build a plain-text-friendly weather summary from raw sensor readings.

This sample is intentionally CORRECT — the control for the checkpoint
pipeline. Every checkpoint stays green: imports resolve, pyright is clean,
the smoke run executes with per-function `code.call` spans, and the return
value satisfies the contract. Compare with its siblings in
../hallucinated_import, ../hallucinated_attr, and ../schema_mismatch.
"""

from datetime import datetime, timezone
from statistics import mean


def summarize(readings):
    temps = [r["temp_c"] for r in readings]
    return {
        "min_c": float(min(temps)),
        "max_c": float(max(temps)),
        "avg_c": round(mean(temps), 1),
    }


def build_report(readings):
    stats = summarize(readings)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_count": len(readings),
        **stats,
    }
