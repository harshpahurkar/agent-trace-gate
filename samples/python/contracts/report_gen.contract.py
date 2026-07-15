"""Contract for samples/python/hallucinated_import/report_gen.py."""

from pydantic import BaseModel

ENTRYPOINT = "profile_dataset"
ARGS = ([{"region": "NA", "revenue": 1250}, {"region": "EU", "revenue": 980}],)


class Returns(BaseModel):
    html: str
    row_count: int
