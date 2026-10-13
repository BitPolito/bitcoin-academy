"""Hybrid retrieval helpers — BM25 scoring and normalized hybrid fusion.

Standalone module; never imports from service modules to avoid circular dependencies.
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

_RRF_K = 60  # kept for rrf_fuse (legacy)
_DENSE_WEIGHT = 0.6   # weight for dense QVAC score in normalized fusion
_SPARSE_WEIGHT = 0.4  # weight for BM25 score in normalized fusion
_SAFE_COURSE_ID = re.compile(r'^[A-Za-z0-9_-]+$')

_BITCOIN_SYNONYMS: dict[str, list[str]] = {
    # Transaction model
    "utxo":         ["utxo", "unspent", "transaction", "output"],
    "txid":         ["txid", "transaction", "id"],
    "coinbase":     ["coinbase", "block", "reward", "mining"],
    "mempool":      ["mempool", "memory", "pool", "pending"],
    "fee":          ["fee", "transaction", "cost"],
    # Cryptography
    "ecdsa":        ["ecdsa", "elliptic", "curve", "digital", "signature"],
    "sha256":       ["sha256", "sha", "256", "hash"],
    "sha-256":      ["sha256", "sha", "256", "hash"],
    "ripemd160":    ["ripemd160", "ripemd", "hash", "digest"],
    "merkle":       ["merkle", "tree", "root", "proof"],
    # Script / addresses
    "p2pkh":        ["p2pkh", "pay", "public", "key", "hash"],
    "p2wpkh":       ["p2wpkh", "pay", "witness", "public", "key", "hash"],
    "p2sh":         ["p2sh", "pay", "script", "hash"],
    "p2tr":         ["p2tr", "taproot", "pay", "taproot"],
    "p2wsh":        ["p2wsh", "pay", "witness", "script", "hash"],
    "segwit":       ["segwit", "segregated", "witness"],
    "taproot":      ["taproot", "schnorr", "merkle", "script"],
    "scriptpubkey": ["scriptpubkey", "script", "public", "key"],
    "scriptsig":    ["scriptsig", "script", "signature"],
    "opcode":       ["opcode", "script", "operation"],
    "witness":      ["witness", "segwit", "signature", "data"],
    # Mining / consensus
    "nonce":        ["nonce", "number", "once", "mining"],
    "difficulty":   ["difficulty", "target", "proof", "work"],
    "pow":          ["pow", "proof", "work", "mining"],
    "hashrate":     ["hashrate", "hash", "rate", "mining", "power"],
    "halving":      ["halving", "block", "reward", "supply"],
    # Network / Lightning
    "lightning":    ["lightning", "channel", "payment", "network"],
    "htlc":         ["htlc", "hash", "time", "locked", "contract"],
    "channel":      ["channel", "lightning", "payment"],
    # Economics
    "seigniorage":  ["seigniorage", "money", "creation", "profit"],
    "hardness":     ["hardness", "hard", "sound", "money", "salability", "stock", "flow"],
    # Monetary properties (Ammous vocabulary: salability across scales/space/time)
    "divisibility":     ["divisibility", "divisible", "scales", "salable", "denomination", "unit"],
    "portability":      ["portability", "portable", "space", "transport", "carry"],
    "durability":       ["durability", "durable", "time", "salable", "perishable", "store"],
    "verifiability":    ["verifiability", "verify", "counterfeit", "genuine", "authentication"],
    "fungibility":      ["fungibility", "fungible", "interchangeable", "identical", "unit"],
    "salability":       ["salability", "salable", "exchange", "scales", "space", "time", "sell"],
    "scarcity":         ["scarcity", "scarce", "supply", "limit", "fixed", "21million", "cap"],
    "debasement":       ["debasement", "inflate", "inflation", "currency", "expand", "supply"],
    "inflation":        ["inflation", "debasement", "currency", "expand", "supply", "monetary"],
    "deflation":        ["deflation", "decline", "price", "sound", "money", "savings"],
    # Energy / mining
    "energy":           ["energy", "electricity", "power", "cost", "mining", "consumption"],
    "electricity":      ["electricity", "energy", "power", "usage", "kilowatt", "watt"],
    "waste":            ["waste", "energy", "electricity", "inefficient", "cost", "mining"],
    # Decentralization / network
    "decentralization": ["decentralization", "decentralized", "distributed", "peer", "node"],
    "node":             ["node", "peer", "network", "validate", "full", "run"],
    "censorship":       ["censorship", "censor", "resistant", "permissionless", "authority"],
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


def _reconstruct_from_corpus(cid: str, score: float, corpus: dict) -> EvidenceChunk | None:
    """Build an EvidenceChunk from a BM25-only corpus entry."""
    entry = corpus.get(cid)
    if not entry:
        return None
    return EvidenceChunk(
        chunk_id=cid,
        text=entry["text"],
        score=round(score, 6),
        anchor=CitationAnchor(
            doc_id=entry.get("doc_id", ""),
            doc_name=entry.get("label", ""),
            section=entry.get("section") or None,
            page=int(entry["page"]) if entry.get("page") else None,
            slide=None,
            chunk_id=cid,
            chunk_type="paragraph",
        ),
    )


def normalized_hybrid_fuse(
    dense_chunks: List[EvidenceChunk],
    bm25_hits: List[Tuple[str, float]],
    corpus: dict,
    top_k: int,
) -> List[EvidenceChunk]:
    """Normalized score fusion: preserves magnitude of dense similarity vs BM25 relevance.

    Dense scores (cosine similarity ∈ [0,1]) and BM25 scores (raw OkapiBM25, variable scale)
    are both normalized to [0,1] then combined with configurable weights:
        hybrid = DENSE_WEIGHT × dense_norm + SPARSE_WEIGHT × bm25_norm

    Chunks present in only one source receive only that source's contribution,
    so a highly confident dense-only hit (0.95 → 0.57) ranks above an average
    BM25-only hit. Pure-BM25 corpus hits are included via corpus reconstruction.
    """
    dense_map = {c.chunk_id: c for c in dense_chunks}
    dense_score = {c.chunk_id: float(c.score) for c in dense_chunks}

    # Normalize BM25 scores to [0, 1]
    max_bm25 = max((s for _, s in bm25_hits), default=1.0) or 1.0
    bm25_norm = {cid: s / max_bm25 for cid, s in bm25_hits}

    all_ids = set(dense_score) | set(bm25_norm)
    hybrid: dict[str, float] = {
        cid: _DENSE_WEIGHT * dense_score.get(cid, 0.0) + _SPARSE_WEIGHT * bm25_norm.get(cid, 0.0)
        for cid in all_ids
    }

    result: List[EvidenceChunk] = []
    for cid in sorted(hybrid, key=hybrid.__getitem__, reverse=True)[:top_k]:
        if cid in dense_map:
            result.append(dense_map[cid].model_copy(update={"score": round(hybrid[cid], 6)}))
        else:
            chunk = _reconstruct_from_corpus(cid, hybrid[cid], corpus)
            if chunk:
                result.append(chunk)

    logger.debug(
        "Normalized hybrid fusion: %d dense + %d BM25 → %d merged",
        len(dense_chunks), len(bm25_hits), len(result),
    )
    return result


def rrf_fuse(
    dense_chunks: List[EvidenceChunk],
    bm25_hits: List[Tuple[str, float]],
    corpus: dict,
    top_k: int,
) -> List[EvidenceChunk]:
    """Reciprocal Rank Fusion (legacy — kept for reference). Use normalized_hybrid_fuse instead."""
    dense_rank = {c.chunk_id: i + 1 for i, c in enumerate(dense_chunks)}
    bm25_rank = {cid: i + 1 for i, (cid, _) in enumerate(bm25_hits)}
    dense_map = {c.chunk_id: c for c in dense_chunks}

    all_ids = set(dense_rank) | set(bm25_rank)
    rrf: dict[str, float] = {
        cid: (1.0 / (_RRF_K + dense_rank[cid]) if cid in dense_rank else 0.0)
           + (1.0 / (_RRF_K + bm25_rank[cid]) if cid in bm25_rank else 0.0)
        for cid in all_ids
    }

    result: List[EvidenceChunk] = []
    for cid in sorted(rrf, key=rrf.__getitem__, reverse=True)[:top_k]:
        if cid in dense_map:
            result.append(dense_map[cid].model_copy(update={"score": round(rrf[cid], 6)}))
        else:
            chunk = _reconstruct_from_corpus(cid, rrf[cid], corpus)
            if chunk:
                result.append(chunk)
    return result
