"""Rung 0 of the inference ladder — exact-match hashing to skip regenerating
deterministic output (issue #137/#161, docs/agent-memory-plan.md).

A stored result is still valid only if nothing that could change it has
changed: the source content, the prompt version, and the model identity.
`lesson_service.compute_content_hash` set the precedent (source_refs + title
+ prompt_version); this generalises it and adds model identity, which the
original omitted.
"""
import hashlib
import json
from typing import Sequence


def compute_generation_hash(
    source_parts: Sequence[str], prompt_version: str, model: str
) -> str:
    """SHA256 of (sorted source_parts, prompt_version, model).

    source_parts should be whatever actually feeds the generation prompt —
    e.g. chunk/section text, not just an id, so content changing under a
    stable id still invalidates the hash. Order-independent (sorted) so
    callers don't need to track a canonical ordering themselves.
    """
    payload = json.dumps(sorted(source_parts)) + prompt_version + model
    return hashlib.sha256(payload.encode()).hexdigest()
