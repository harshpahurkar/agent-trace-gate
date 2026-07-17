"""Contract for samples/python/hallucinated_attr/date_utils.py."""

from pydantic import BaseModel

ENTRYPOINT = "parse_timestamps"
ARGS = (
    [
        "2026-08-27T09:15:00 boot sequence ok",
        "2026-08-27T09:16:11 sensors online",
    ],
)


class Returns(BaseModel):
    count: int
    first: str
