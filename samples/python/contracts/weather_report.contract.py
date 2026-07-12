"""Contract for samples/python/passing/weather_report.py."""

from datetime import datetime

from pydantic import BaseModel

ENTRYPOINT = "build_report"
ARGS = ([{"temp_c": 18.5}, {"temp_c": 21.0}, {"temp_c": 19.2}],)


class Returns(BaseModel):
    generated_at: datetime
    sample_count: int
    min_c: float
    max_c: float
    avg_c: float
