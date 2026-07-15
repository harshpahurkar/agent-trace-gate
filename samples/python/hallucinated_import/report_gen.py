"""Profile a dataset and emit an HTML report.

SEEDED FAILURE — hallucinated-import.

'pandas_profiling_lite' does not exist on PyPI. This models the single most
common LLM code-generation failure: 19.7% of packages referenced across
576,000 generated samples were hallucinated (arXiv:2406.10279), and attackers
register those exact names ("slopsquatting"). Expected catch:
checkpoint.static.imports — find_spec misses locally, PyPI answers 404.
"""

import pandas_profiling_lite as ppl


def profile_dataset(rows):
    report = ppl.ProfileReport(rows, minimal=True)
    return {"html": report.to_html(), "row_count": len(rows)}
