"""Generic cursor pagination — an opaque, base64-encoded cursor over a
(created_at, id) keyset, so pages stay stable under concurrent inserts (an
offset would skip or repeat rows when the underlying set changes between
requests).

CursorPage is meant to be reused as the response envelope for any future
list endpoint that adopts the same (created_at, id) keyset convention —
see issue #73.
"""
import base64
import json
from typing import Generic, List, Optional, Tuple, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class CursorPage(BaseModel, Generic[T]):
    items: List[T]
    next_cursor: Optional[str] = None
    has_more: bool


def encode_cursor(created_at: str, id_: str) -> str:
    raw = json.dumps({"created_at": created_at, "id": id_}).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> Tuple[str, str]:
    """Raises ValueError on any malformed cursor — callers map that to a 422.

    Everything this does to an attacker-controlled string can fail in more
    ways than base64/JSON decoding errors (both already ValueError
    subclasses): a well-formed-but-wrong-shaped payload can raise KeyError
    (missing field) or TypeError (not a dict, or a field of the wrong type).
    Normalize all of it to ValueError so the controller has one exception
    to catch, rather than a 500 slipping through on any shape it didn't
    anticipate.
    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        data = json.loads(raw)
        created_at = data["created_at"]
        id_ = data["id"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Malformed cursor: {exc}") from exc
    if not isinstance(created_at, str) or not isinstance(id_, str):
        raise ValueError("Malformed cursor: created_at and id must be strings")
    return created_at, id_
