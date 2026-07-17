"""Parse ISO-8601 timestamps out of a log export.

SEEDED FAILURE — hallucinated-api.

`datetime.from_iso()` does not exist; the real constructor is
`datetime.fromisoformat()`. Plausible-but-wrong member names are the
dominant API-hallucination shape (arXiv:2505.05057). Expected catch:
checkpoint.static.types (pyright reportAttributeAccessIssue) — or, with
--skip-static, an AttributeError recorded on the exact `code.call` span
where it detonates at runtime.
"""

from datetime import datetime


def parse_timestamps(raw_lines):
    parsed = []
    for line in raw_lines:
        stamp = line.split(" ", 1)[0]
        parsed.append(datetime.from_iso(stamp))
    return {"count": len(parsed), "first": parsed[0].isoformat()}
