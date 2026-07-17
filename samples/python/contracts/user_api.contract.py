"""Contract for samples/python/schema_mismatch/user_api.py.

Strict mode is this contract's choice: an API boundary should return exactly
the declared types, so `id` arriving as the string "42" is a violation, not
something to silently coerce.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

ENTRYPOINT = "get_user"
ARGS = (42,)


class Returns(BaseModel):
    model_config = ConfigDict(strict=True)

    id: int
    name: str
    signup_date: datetime
