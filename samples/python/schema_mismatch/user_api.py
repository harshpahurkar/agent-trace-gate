"""Fetch a user record for the account dashboard.

SEEDED FAILURE — schema-mismatch.

This is the sneaky one: imports resolve, pyright is clean, and the smoke run
executes without raising. But the return value drifts from the UserRecord
contract — `id` comes back as a string and `signup_date` is missing entirely
(a stray `signup` key instead). Only checkpoint.contract catches it, which is
the argument for validating runtime boundaries instead of trusting a diff
that "looks right".
"""


def get_user(user_id):
    return {
        "id": str(user_id),
        "name": "Ada Lovelace",
        "signup": "yesterday",
    }
