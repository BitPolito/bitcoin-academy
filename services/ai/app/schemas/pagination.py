"""Shared cursor-pagination contracts."""
import base64
import json
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")

# Paginate once a list exceeds a normal screenful; callers may request more for
# bulk work, but the server cap prevents accidentally unbounded responses.
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class CursorPage(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False


def encode_cursor(*values: str) -> str:
    payload = json.dumps(values, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(cursor: str, parts: int) -> tuple[str, ...]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        values = json.loads(base64.urlsafe_b64decode(padded).decode())
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid pagination cursor") from exc
    if not isinstance(values, list) or len(values) != parts or not all(
        isinstance(value, str) for value in values
    ):
        raise ValueError("Invalid pagination cursor")
    return tuple(values)
