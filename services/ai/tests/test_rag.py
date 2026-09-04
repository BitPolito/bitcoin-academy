"""RAG test suite for The Bitcoin Standard.

Usage:
    uv run --no-sync python tests/test_rag.py
    uv run --no-sync python tests/test_rag.py --output results.json
    uv run --no-sync python tests/test_rag.py --course <course_id>
    uv run --no-sync python tests/test_rag.py --query "What is Bitcoin?"

Runs 35 curated queries through the full retrieval pipeline and prints a
color-coded report. Saves full JSON results to --output (default: rag_test_results.json).
"""
import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Environment — must be set before any app import
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_ROOT}/bitcoin_academy.db")
os.environ.setdefault("QVAC_SERVICE_URL", "http://localhost:3001")
os.environ.setdefault("RAG_RETRIEVE_K", "20")
os.environ.setdefault("RAG_TOP_K", "10")
os.environ.setdefault("RAG_MAX_CONTEXT_TOKENS", "6000")
# Load .env for SECRET_KEY and other settings
try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env", override=False)
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Queries — 35 total, 7 categories
# ---------------------------------------------------------------------------
QUERIES: list[tuple[str, str]] = [
    # (category, query_text)
    # Basic factual
    ("basic",       "What is the main argument of The Bitcoin Standard?"),
    ("basic",       "Who is the author of The Bitcoin Standard?"),
    ("basic",       "What problem does Bitcoin aim to solve in the book?"),
    ("basic",       "How does the book define sound money?"),
    ("basic",       "What are the monetary properties discussed in the book?"),
    # Chapter-level
    ("chapter",     "What is the main idea of Chapter 1 in The Bitcoin Standard?"),
    ("chapter",     "What does the book say about primitive moneys?"),
    ("chapter",     "Why does the author discuss gold in the chapter on monetary metals?"),
    ("chapter",     "What is the role of government money in the book?"),
    ("chapter",     "What does the book argue about time preference and money?"),
    # Conceptual
    ("conceptual",  "Why does the book compare Bitcoin to gold?"),
    ("conceptual",  "How does the book explain Bitcoin's scarcity?"),
    ("conceptual",  "What does the book say about proof of work?"),
    ("conceptual",  "Why does the author consider Bitcoin censorship-resistant?"),
    ("conceptual",  "How does the book describe Bitcoin as digital cash?"),
    # Comparative
    ("comparative", "Compare Bitcoin and gold as forms of money according to the book."),
    ("comparative", "Why does the book argue that fiat money is inferior to sound money?"),
    ("comparative", "How does the book connect money and individual freedom?"),
    ("comparative", "What is the relationship between monetary policy and government power in the book?"),
    ("comparative", "Why does the book claim Bitcoin is not controlled by any central authority?"),
    # Multi-hop / synthesis
    ("synthesis",   "According to the book, how do scarcity and decentralization work together in Bitcoin?"),
    ("synthesis",   "What historical examples does the book use to support its theory of money?"),
    ("synthesis",   "How does the book move from the history of money to the case for Bitcoin?"),
    ("synthesis",   "Which monetary properties make Bitcoin suitable as a store of value?"),
    ("synthesis",   "What are the book's arguments against the idea that Bitcoin is mainly for criminals?"),
    # Adversarial / evaluation
    ("adversarial", "Does the book provide evidence that Bitcoin is better than gold?"),
    ("adversarial", "Are the book's arguments about fiat money logically consistent?"),
    ("adversarial", "Which claims in the book rely on historical analogy rather than empirical data?"),
    ("adversarial", "What assumptions underlie the book's critique of central banking?"),
    ("adversarial", "Where does the book make normative claims instead of descriptive claims?"),
    # Retrieval stress-test
    ("stress",      "What does the book say about the salability of money?"),
    ("stress",      "How does the author define durability, divisibility, portability, and verifiability?"),
    ("stress",      "What is the book's view on energy use in Bitcoin mining?"),
    ("stress",      "What does the book say about the blockchain compared with Bitcoin?"),
    ("stress",      "How does the book explain Bitcoin's global settlement properties?"),
]

# Sections we expect to see for specific query categories
_CHAPTER_EXPECTED: dict[str, list[str]] = {
    "Chapter 1":              ["Money", "Primitive Moneys"],
    "primitive moneys":       ["Primitive Moneys", "Money"],
    "gold":                   ["Monetary Metals"],
    "government money":       ["Government Money"],
    "time preference":        ["Money and Time Preference"],
    "proof of work":          ["Bitcoin Questions", "Digital Money"],
    "salability":             ["Monetary Metals", "Money"],
    "durability":             ["Money"],
    "energy use":             ["Bitcoin Questions", "What Is Bitcoin Good For?"],
    "blockchain":             ["Bitcoin Questions", "Digital Money", "What Is Bitcoin Good For?"],
    "global settlement":      ["Bitcoin Questions", "What Is Bitcoin Good For?"],
    "censorship":             ["Bitcoin Questions", "Sound Money and Individual Freedom"],
    "criminal":               ["Bitcoin Questions", "What Is Bitcoin Good For?"],
    "fiat money":             ["Government Money", "Capitalism's Information System"],
    "individual freedom":     ["Sound Money and Individual Freedom"],
    "time preference and money": ["Money and Time Preference"],
}

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class CitationResult:
    label: str
    section: str
    page: int
    score: float
    snippet: str


@dataclass
class QueryResult:
    idx: int
    category: str
    query: str
    answer: str
    citations: list[CitationResult] = field(default_factory=list)
    retrieval_used: bool = False
    elapsed_s: float = 0.0
    error: Optional[str] = None

    # Computed
    @property
    def top_score(self) -> float:
        return max((c.score for c in self.citations), default=0.0)

    @property
    def unique_sections(self) -> list[str]:
        seen, result = set(), []
        for c in self.citations:
            k = c.section or c.label
            if k not in seen:
                seen.add(k)
                result.append(k)
        return result

    @property
    def verdict(self) -> str:
        if self.error:
            return "ERROR"
        if not self.retrieval_used:
            return "FAIL"
        if self.top_score >= 0.35:
            return "PASS"
        return "WARN"


# ---------------------------------------------------------------------------
# Terminal colors
# ---------------------------------------------------------------------------
_NO_COLOR = not sys.stdout.isatty() or os.getenv("NO_COLOR")

def _c(code: str, text: str) -> str:
    if _NO_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"

GREEN  = lambda t: _c("32;1", t)
YELLOW = lambda t: _c("33;1", t)
RED    = lambda t: _c("31;1", t)
CYAN   = lambda t: _c("36;1", t)
BOLD   = lambda t: _c("1", t)
DIM    = lambda t: _c("2", t)

VERDICT_FMT = {
    "PASS":  GREEN("✓ PASS "),
    "WARN":  YELLOW("⚠ WARN "),
    "FAIL":  RED("✗ FAIL "),
    "ERROR": RED("✗ ERROR"),
}

# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------
async def run_query(query: str, course_id: str, idx: int, category: str) -> QueryResult:
    from app.services.chat_service import answer as rag_answer

    result = QueryResult(idx=idx, category=category, query=query, answer="")
    t0 = time.perf_counter()
    try:
        chat = await rag_answer(query, course_id)
        result.elapsed_s = round(time.perf_counter() - t0, 2)
        result.answer = chat.answer
        result.retrieval_used = chat.retrieval_used
        result.citations = [
            CitationResult(
                label=c.label,
                section=c.section,
                page=c.page,
                score=round(c.score, 4),
                snippet=c.snippet[:120],
            )
            for c in chat.citations
        ]
    except Exception as exc:
        result.elapsed_s = round(time.perf_counter() - t0, 2)
        result.error = str(exc)
    return result


async def run_all(queries: list[tuple[str, str]], course_id: str) -> list[QueryResult]:
    results: list[QueryResult] = []
    for idx, (category, query) in enumerate(queries, 1):
        r = await run_query(query, course_id, idx, category)
        results.append(r)
        _print_result(r, total=len(queries))
    return results


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------
def _print_result(r: QueryResult, total: int) -> None:
    verdict = VERDICT_FMT.get(r.verdict, r.verdict)
    prefix = f"[{r.idx:>2}/{total}] {CYAN(r.category.upper()[:10])} "
    print(f"\n{prefix}{BOLD(r.query)}")

    cit_summary = ""
    if r.citations:
        top3 = r.citations[:3]
        parts = [f"{c.section or c.label} ({c.score:.3f})" for c in top3]
        cit_summary = "  " + DIM("└ ") + ", ".join(parts)

    status_line = (
        f"  {verdict}  "
        f"{len(r.citations)} citations  "
        f"top={r.top_score:.3f}  "
        f"{r.elapsed_s}s"
    )
    if r.error:
        status_line += f"  {RED(r.error[:80])}"
    print(status_line)

    if cit_summary:
        print(cit_summary)

    # Answer snippet (first 130 chars, one line)
    answer_preview = r.answer.replace("\n", " ").strip()[:130]
    if len(r.answer) > 130:
        answer_preview += "…"
    print(f"  {DIM('▸')} {answer_preview}")


def _print_summary(results: list[QueryResult], out_path: str) -> None:
    by_verdict = {"PASS": 0, "WARN": 0, "FAIL": 0, "ERROR": 0}
    for r in results:
        by_verdict[r.verdict] = by_verdict.get(r.verdict, 0) + 1

    top_scores = [r.top_score for r in results if r.retrieval_used]
    avg_top = sum(top_scores) / len(top_scores) if top_scores else 0
    avg_cit = sum(len(r.citations) for r in results) / len(results) if results else 0
    avg_lat = sum(r.elapsed_s for r in results) / len(results) if results else 0

    sep = "═" * 68
    print(f"\n{BOLD(sep)}")
    print(BOLD("  SUMMARY"))
    print(sep)
    total = len(results)
    p, w, f_, e = by_verdict["PASS"], by_verdict["WARN"], by_verdict["FAIL"], by_verdict["ERROR"]
    print(
        f"  {GREEN(f'Passed: {p}/{total}')}   "
        f"{YELLOW(f'Warned: {w}/{total}')}   "
        f"{RED(f'Failed: {f_}/{total}')}   "
        f"{RED(f'Errors: {e}/{total}')}"
    )
    print(f"  Avg top score : {avg_top:.3f}")
    print(f"  Avg citations : {avg_cit:.1f}")
    print(f"  Avg latency   : {avg_lat:.2f}s")
    print(f"  Full results  : {out_path}")

    # Worst results (FAIL/WARN)
    weak = [r for r in results if r.verdict in ("FAIL", "WARN", "ERROR")]
    if weak:
        print(f"\n  {YELLOW('Queries needing attention:')}")
        for r in weak:
            v = VERDICT_FMT.get(r.verdict, r.verdict)
            q = r.query[:70] + ("…" if len(r.query) > 70 else "")
            print(f"    {v} [{r.idx:>2}] {q}")

    # Per-category breakdown
    from collections import defaultdict
    by_cat: dict[str, list[QueryResult]] = defaultdict(list)
    for r in results:
        by_cat[r.category].append(r)
    print(f"\n  {'Category':<12}  {'Pass':>4}  {'Warn':>4}  {'Fail':>4}  {'AvgScore':>8}  {'AvgLat':>6}")
    print(f"  {'─'*12}  {'─'*4}  {'─'*4}  {'─'*4}  {'─'*8}  {'─'*6}")
    for cat in ["basic", "chapter", "conceptual", "comparative", "synthesis", "adversarial", "stress"]:
        rows = by_cat.get(cat, [])
        if not rows:
            continue
        p = sum(1 for r in rows if r.verdict == "PASS")
        w = sum(1 for r in rows if r.verdict == "WARN")
        f = sum(1 for r in rows if r.verdict in ("FAIL", "ERROR"))
        avg_s = sum(r.top_score for r in rows) / len(rows)
        avg_l = sum(r.elapsed_s for r in rows) / len(rows)
        print(f"  {cat:<12}  {p:>4}  {w:>4}  {f:>4}  {avg_s:>8.3f}  {avg_l:>5.1f}s")
    print(BOLD(sep))


# ---------------------------------------------------------------------------
# JSON serialisation
# ---------------------------------------------------------------------------
def _to_dict(r: QueryResult) -> dict:
    return {
        "idx": r.idx,
        "category": r.category,
        "query": r.query,
        "verdict": r.verdict,
        "retrieval_used": r.retrieval_used,
        "top_score": r.top_score,
        "num_citations": len(r.citations),
        "unique_sections": r.unique_sections,
        "elapsed_s": r.elapsed_s,
        "answer": r.answer,
        "citations": [asdict(c) for c in r.citations],
        "error": r.error,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def _discover_course_id() -> str:
    """Try to find the Bitcoin Standard course ID from the DB."""
    try:
        from app.db.models import CourseDocument
        from app.db.session import SessionLocal
        db = SessionLocal()
        doc = db.query(CourseDocument).filter(
            CourseDocument.filename.like("%bitcoin%")
        ).first()
        db.close()
        if doc:
            return doc.course_id
    except Exception:
        pass
    return "6a792091-884f-4e40-ba0b-b6d06376c196"


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG test suite")
    parser.add_argument("--course", default=None, help="Course ID (auto-detected if omitted)")
    parser.add_argument("--output", default="rag_test_results.json", help="JSON output file")
    parser.add_argument("--query", default=None, help="Run a single custom query and exit")
    args = parser.parse_args()

    course_id = args.course or _discover_course_id()

    sep = "═" * 68
    print(BOLD(sep))
    print(BOLD("  Bitcoin Academy — RAG Test Suite"))
    print(f"  Course : {course_id}")
    print(f"  Queries: {len(QUERIES)}")
    print(BOLD(sep))

    if args.query:
        # Single-query mode
        result = asyncio.run(run_query(args.query, course_id, 1, "custom"))
        _print_result(result, total=1)
        print()
        return

    results = asyncio.run(run_all(QUERIES, course_id))

    # Save JSON
    out_path = args.output
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "course_id": course_id,
                "total": len(results),
                "results": [_to_dict(r) for r in results],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    _print_summary(results, out_path)


if __name__ == "__main__":
    main()
