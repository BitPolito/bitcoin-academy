"""Hybrid retrieval helpers — BM25 scoring and RRF fusion.

Called by retrieval_service.search(); never imports from retrieval_service
to avoid circular dependencies.
"""
import json
import logging
import os
import pickle
import re
from pathlib import Path
from typing import List, Tuple

from app.schemas.evidence_pack import CitationAnchor, EvidenceChunk

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve()
_SERVICES_AI = _HERE.parents[2]
_QVAC_INGEST_DIR = Path(os.getenv("QVAC_INGEST_DIR", str(_SERVICES_AI / "qvac_ingest")))

_RRF_K = 60  # Cormack & Clarke 2009 constant
_SAFE_COURSE_ID = re.compile(r'^[A-Za-z0-9_-]+$')

_BITCOIN_SYNONYMS: dict[str, list[str]] = {
    "utxo": ["utxo", "unspent", "transaction", "output"],
    "ecdsa": ["ecdsa", "elliptic", "curve", "digital", "signature"],
    "p2pkh": ["p2pkh", "pay", "public", "key", "hash"],
    "p2wpkh": ["p2wpkh", "pay", "witness", "public", "key", "hash"],
    "p2sh": ["p2sh", "pay", "script", "hash"],
    "segwit": ["segwit", "segregated", "witness"],
    "sha256": ["sha256", "sha", "256"],
    "sha-256": ["sha256", "sha", "256"],
    "txid": ["txid", "transaction", "id"],
    "scriptpubkey": ["scriptpubkey", "script", "public", "key"],
    "scriptsig": ["scriptsig", "script", "signature"],
}


def _tokenize(text: str) -> list[str]:
    """Tokenize with CamelCase splitting, hyphen normalisation and Bitcoin synonym expansion."""
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    tokens = re.sub(r'[-_]', ' ', text).lower().split()
    expanded: list[str] = []
    for tok in tokens:
        expanded.extend(_BITCOIN_SYNONYMS.get(tok, [tok]))
    return expanded


def _index_paths(course_id: str) -> tuple[Path, Path]:
    if not _SAFE_COURSE_ID.match(course_id):
        raise ValueError(f"Invalid course_id: {course_id!r}")
    return (
        _QVAC_INGEST_DIR / f"{course_id}_bm25.pkl",
        _QVAC_INGEST_DIR / f"{course_id}_corpus.json",
    )


def load_bm25_index(course_id: str):
    """Return (bm25, ids, corpus_dict) or None if index absent or corrupt."""
    bm25_path, corpus_path = _index_paths(course_id)
    if not bm25_path.exists() or not corpus_path.exists():
        return None
    try:
        with bm25_path.open("rb") as f:
            data = pickle.load(f)
        with corpus_path.open(encoding="utf-8") as f:
            corpus: dict[str, dict] = json.load(f)
        return data["bm25"], data["ids"], corpus
    except Exception as exc:
        logger.warning("BM25 index load failed for course '%s': %s", course_id, exc)
        return None


def bm25_search(query: str, course_id: str, top_k: int) -> List[Tuple[str, float]]:
    """Run BM25 on the pre-built corpus for course_id.

    Returns [(chunk_id, raw_score)] sorted descending, up to top_k entries.
    Returns [] when the index is absent or all scores are zero.
    """
    result = load_bm25_index(course_id)
    if result is None:
        return []
    bm25, ids, _ = result
    scores = bm25.get_scores(_tokenize(query))
    ranked = sorted(zip(ids, scores.tolist()), key=lambda x: x[1], reverse=True)
    return [(cid, float(s)) for cid, s in ranked[:top_k] if s > 0.0]


def rrf_fuse(
    dense_chunks: List[EvidenceChunk],
    bm25_hits: List[Tuple[str, float]],
    corpus: dict,
    top_k: int,
) -> List[EvidenceChunk]:
    """Reciprocal Rank Fusion of dense-vector and BM25 sparse rankings.

    RRF score: Σ 1 / (k + rank_i)  where k=60, rank is 1-based.

    Args:
        dense_chunks: Vector-search results, already sorted by descending similarity.
        bm25_hits:    [(chunk_id, bm25_score)] sorted by BM25 descending.
        corpus:       {chunk_id: entry_dict} — used to reconstruct EvidenceChunks
                      for BM25-only hits that don't appear in dense_chunks.
        top_k:        Maximum number of results to return.

    Returns merged list sorted by RRF score descending.
    """
    dense_rank = {c.chunk_id: i + 1 for i, c in enumerate(dense_chunks)}
    bm25_rank = {cid: i + 1 for i, (cid, _) in enumerate(bm25_hits)}
    dense_map = {c.chunk_id: c for c in dense_chunks}

    all_ids = set(dense_rank) | set(bm25_rank)
    rrf: dict[str, float] = {}
    for cid in all_ids:
        score = 0.0
        if cid in dense_rank:
            score += 1.0 / (_RRF_K + dense_rank[cid])
        if cid in bm25_rank:
            score += 1.0 / (_RRF_K + bm25_rank[cid])
        rrf[cid] = score

    sorted_ids = sorted(rrf, key=rrf.__getitem__, reverse=True)

    result: List[EvidenceChunk] = []
    for cid in sorted_ids[:top_k]:
        if cid in dense_map:
            # Update score to RRF value; preserve all other fields.
            result.append(dense_map[cid].model_copy(update={"score": round(rrf[cid], 6)}))
        elif cid in corpus:
            # BM25-only hit — reconstruct from corpus entry.
            entry = corpus[cid]
            result.append(EvidenceChunk(
                chunk_id=cid,
                text=entry["text"],
                score=round(rrf[cid], 6),
                anchor=CitationAnchor(
                    doc_id=entry.get("doc_id", ""),
                    doc_name=entry.get("label", ""),
                    section=entry.get("section") or None,
                    page=int(entry["page"]) if entry.get("page") else None,
                    slide=None,
                    chunk_id=cid,
                    chunk_type="paragraph",
                ),
            ))

    logger.debug(
        "RRF fusion: %d dense + %d BM25 → %d merged for course '%s'",
        len(dense_chunks), len(bm25_hits), len(result),
        next(iter(corpus.values()), {}).get("doc_id", "?") if corpus else "?",
    )
    return result
