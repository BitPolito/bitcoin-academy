# Course outline evaluation

Issue #138 requires a human evaluation on three real courses with different source structures.
The repository contains three suitable source sets:

| Course fixture | Source | Structure under test |
|---|---|---|
| Bitcoin foundations | `docs/src/bitcoin_technical_document.pdf` | Short, focused document |
| Mastering Bitcoin | `docs/Mastering-Bitcoin.pdf` | Long book with a deep section hierarchy |
| Bitcoin presentation | `docs/src/bitcoin_creative_commons_en.pptx` | Slide-oriented, sparse sections |

For each source, the reviewer must record: topic coverage, duplicate topics, chapter ordering,
source-link correctness, edits required, and behavior after adding, reprocessing and deleting a
source. A result is acceptable only when every lesson opens its originating passage, draft or
stale content is hidden from students, and a human correction survives document invalidation.

## Execution record

The automated structural and re-ingestion checks pass for all source shapes represented by the
pipeline tests. Full model-output scoring was not run on 2026-09-03 because the local QVAC service
was unavailable on port 3001. This is intentionally recorded as pending rather than presenting
synthetic fixtures as a completed human evaluation.
