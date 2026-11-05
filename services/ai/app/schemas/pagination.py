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
    """Raises ValueError on a malformed cursor — callers should map this to a 422."""
    raw = base64.urlsafe_b64decode(cursor.encode())
    data = json.loads(raw)
    return data["created_at"], data["id"]
