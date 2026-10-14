import httpx
import sys

base_url = "http://localhost:8000/api"
# Updated path to the correct book
pdf_path = r"C:\Users\M. Arda\Desktop\bitcoin-academy\workers\python-ingester\the-bitcoin-standard.pdf"

print("Authenticating...")
try:
    resp = httpx.post(
        f"{base_url}/auth/login", 
        json={"email": "admin@bitpolito.it", "password": "DevAdmin@2024!Secure"},
        timeout=30.0
    )
    resp.raise_for_status()
    token = resp.json()["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
except Exception as e:
    print(f"Login failed: {e}")
    sys.exit(1)

print("Creating Course...")
try:
    resp = httpx.post(
        f"{base_url}/courses", 
        json={"title": "The Bitcoin Standard", "description": "RAG Baseline Test"}, 
        headers=headers,
        timeout=30.0
    )
    resp.raise_for_status()
    course_id = resp.json()["id"]
    print(f"Course ID: {course_id}")
except Exception as e:
    print(f"Course creation failed: {e}")
    sys.exit(1)

print("Uploading PDF to Ingestion Queue...")
try:
    with open(pdf_path, "rb") as f:
        files = {"file": ("the-bitcoin-standard.pdf", f, "application/pdf")}
        resp = httpx.post(
            f"{base_url}/courses/{course_id}/documents", 
            headers=headers, 
            files=files,
            timeout=60.0
        )
        resp.raise_for_status()
    print("\nUpload successful! The ARQ worker is now processing the document.")
except Exception as e:
    print(f"Upload failed: {e}")
    if hasattr(e, 'response') and e.response is not None:
        print(f"Server response: {e.response.text}")
    sys.exit(1)

print("\nWait about 30-60 seconds for ChromaDB ingestion to finish, then run:")
print(f"uv run python tests/test_rag.py --course {course_id} --output ../../baseline_before.json")