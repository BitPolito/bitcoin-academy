import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(name)s] - %(message)s"
)
logger = logging.getLogger("AIPipeline")

def parse_document(file_path: str) -> str:
    logger.info(f"Stage 1/4 : Parsing -> {file_path}")
    time.sleep(1)

    if not file_path.endswith(".pdf"):
        raise ValueError("Only PDF files can be processed!")

    return ("Bitcoin is a peer-to-peer electronic cash system that allows online "
        "payments to be sent directly from one party to another without "
        "going through a financial institution.")

def chunk_text(text: str) -> list:
    logger.info("Stage 2/4: Chunking")
    time.sleep(1)
    return["piece 1", "piece 2", "piece 3"]

def embed_chunks(chunks: list) -> list:
    logger.info("Stage 3/4: Embedding")
    time.sleep(1)
    return [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]

def store_in_vector_db(vectors : list, course_id: str):
    logger.info("Stage 4/4: Indexing")
    time.sleep(1)
    return True

def process_course_document(file_path: str, course_id: str):
    logger.info(f"The process has started: {file_path}")

    try:
        text = parse_document(file_path)
        chunks = chunk_text(text)
        vectors = embed_chunks(chunks)
        store_in_vector_db(vectors, course_id)

        logger.info(f"The process has successfully completed: {file_path}")
        return{"status": "completed"}

    except Exception as e:
        logger.error(f"Process failure: Crash while processing {file_path}. Error: {str(e)}")
        return {"status": "failed", "error": str(e)}

if __name__ == "__main__":
    print("\n pdf test")
    process_course_document("bitcoin_whitepaper.pdf", "course_1")
    
    print("\n not pdf")
    process_course_document("picture.jpg", "course_1")  