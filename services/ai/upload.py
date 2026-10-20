import httpx
import sys
import time

def upload_and_wait(filepath: str):
    print(f"Uploading {filepath}...")
    with open(filepath, "rb") as f:
        resp = httpx.post(
            "http://127.0.0.1:8000/api/v1/documents",
            data={"course_id": "test-rag-course"},
            files={"file": (filepath.split('/')[-1], f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        )
    resp.raise_for_status()
    doc_id = resp.json()["id"]
    course_id = resp.json()["course_id"]
    
    print("Waiting for ingestion pipeline to complete...")
    for _ in range(60):
        status = httpx.get(f"http://127.0.0.1:8000/api/v1/documents/{doc_id}").json()["status"]
        if status == "ready":
            print(f"Ingestion complete. Course ID: {course_id}")
            with open("tests/data/corpus/course_id.txt", "w") as out:
                out.write(course_id)
            return
        elif status == "failed":
            raise RuntimeError("Document ingestion failed.")
        time.sleep(2)
    raise TimeoutError("Ingestion timed out.")

if __name__ == "__main__":
    upload_and_wait(sys.argv[1])