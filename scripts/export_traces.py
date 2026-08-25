"""Pull the engine's traces back out of Jaeger as JSON.

Useful for attaching a failing run's traces to a bug report, or for reading
them after the Jaeger container is gone. Stdlib only, so it runs from a bare
checkout with nothing installed.
"""

import json
import os
import sys
import urllib.request

JAEGER = os.environ.get("AGENTTRACE_JAEGER_UI", "http://localhost:16686").rstrip("/")
OUT = sys.argv[1] if len(sys.argv) > 1 else "traces.json"


def main() -> int:
    url = f"{JAEGER}/api/traces?service=agenttrace&limit=200"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            payload = json.load(resp)
    except OSError as exc:
        print(f"jaeger not reachable at {JAEGER}: {exc}")
        return 1
    traces = payload.get("data") or []
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    print(f"exported {len(traces)} trace(s) to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
