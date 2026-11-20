"""Index the open RAG corpus into a course, in process (used by the RAG CI job).

Runs the same ingestion pipeline as the upload endpoint (parse, chunk, BM25,
QVAC embedding) without starting the API: the evaluation suite
(tests/test_rag.py) also runs in process and finds the course by the corpus
filename, so it only needs the database and QVAC_INGEST_DIR this script writes.

Usage (from services/ai, with QVAC running):
    uv run python ../../scripts/ingest_rag_corpus.py tests/data/corpus/mastering-bitcoin-3e.docx

Exits non-zero unless the document ends up READY and indexed in QVAC. Running
it again on an already indexed corpus is a no-op.
"""
import argparse
import shutil
import sys
from pathlib import Path

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_COURSE_TITLE = "RAG evaluation: Mastering Bitcoin (3rd edition)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("corpus", type=Path, help="Corpus DOCX produced by fetch_rag_corpus.py")
    args = parser.parse_args()

    corpus: Path = args.corpus.resolve()
    if not corpus.is_file():
        print(f"Corpus not found: {corpus}. Run scripts/fetch_rag_corpus.py first.", file=sys.stderr)
        return 1

    # Imported here so --help works without a configured environment.
    from app.db.models import CourseDocument, DocumentStatus
    from app.db.session import get_db_context, init_db
    from app.services import course_service, document_service
    from app.workers import pipeline

    init_db()

    with get_db_context() as db:
        existing = (
            db.query(CourseDocument).filter(CourseDocument.filename == corpus.name).first()
        )
        if existing and existing.status == DocumentStatus.READY and existing.indexing_status == "indexed":
            print(f"Already indexed: course {existing.course_id}, document {existing.id}")
            return 0

        if existing:
            # Retry a previous incomplete run in place: a second course holding
            # the same file would make test_rag.py's discovery ambiguous.
            course_id, document_id = existing.course_id, existing.id
        else:
            course = course_service.create_course(db, title=_COURSE_TITLE)
            doc = document_service.create_document(
                db,
                course_id=course.id,
                filename=corpus.name,
                size=corpus.stat().st_size,
                mime_type=_DOCX_MIME,
                document_type="lecture",
            )
            course_id, document_id = course.id, doc.id

    upload_dir = pipeline.UPLOADS_DIR / course_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{document_id}_{corpus.name}"
    shutil.copyfile(corpus, file_path)

    print(f"Indexing {corpus.name} into course {course_id} (document {document_id})...")
    pipeline.run(
        document_id=document_id,
        course_id=course_id,
        filename=corpus.name,
        file_path=str(file_path),
        material_type="lecture",
    )

    with get_db_context() as db:
        doc = db.get(CourseDocument, document_id)
        status = doc.status if doc else None
        indexing = doc.indexing_status if doc else None
        error = doc.error_message if doc else "document disappeared"

    if status != DocumentStatus.READY or indexing != "indexed":
        print(
            f"Ingestion did not complete: status={status}, indexing_status={indexing}, "
            f"error={error}",
            file=sys.stderr,
        )
        return 1

    print(f"Indexed: course {course_id}, document {document_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
