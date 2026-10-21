#!/usr/bin/env python3
"""
ingest_rag_corpus.py

Authenticates with the Bitcoin Academy API as a dev admin, creates a dedicated
course for RAG evaluation, and uploads a target document for ingestion.
Polls the API until the document status is 'ready' or 'error'.
"""

import argparse
import time
import sys
from pathlib import Path
import httpx

def main():
    parser = argparse.ArgumentParser(description="Upload and ingest a document for RAG evaluation.")
    parser.add_argument("file", type=Path, help="Path to the document to upload.")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Base URL of the backend API")
    args = parser.parse_args()

    if not args.file.exists():
        print(f"Error: File {args.file} not found.")
        sys.exit(1)

    client = httpx.Client(base_url=args.base_url, timeout=60.0)

    # 1. Authenticate as seeded Dev Admin
    print(f"Logging into API at {args.base_url}...")
    try:
        login_resp = client.post("/api/auth/login", json={
            "email": "admin@bitpolito.it",
            "password": "DevAdmin@2024!Secure"
        })
        login_resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"Login failed: {e}\nResponse: {e.response.text if hasattr(e, 'response') else 'N/A'}")
        sys.exit(1)
        
    token = login_resp.json()["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create the Evaluation Course
    print("Creating RAG Evaluation course...")
    course_resp = client.post("/api/courses", json={
        "title": "Mastering Bitcoin (RAG Baseline)",
        "description": "Automated ingestion course for GitHub Actions RAG evaluations."
    }, headers=headers)
    course_resp.raise_for_status()
    course_id = course_resp.json()["id"]
    print(f"Course created with ID: {course_id}")

    # Save course ID so test_rag.py can read it
    course_id_path = args.file.parent / "course_id.txt"
    course_id_path.write_text(course_id, encoding="utf-8")

    # 3. Upload the Document
    print(f"Uploading {args.file.name} to course...")
    with open(args.file, "rb") as f:
        mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        files = {"file": (args.file.name, f, mime_type)}
        data = {"document_type": "reference"}
        
        upload_resp = client.post(
            f"/api/courses/{course_id}/documents", 
            data=data, 
            files=files, 
            headers=headers
        )
        
        if upload_resp.status_code >= 400:
            print(f"Upload failed: {upload_resp.text}")
            
        upload_resp.raise_for_status()
        
    doc_id = upload_resp.json()["id"]
    print(f"Document uploaded with ID: {doc_id}")

    # 4. Poll Ingestion Status
    print("Waiting for QVAC to complete vector ingestion", end="")
    while True:
        status_resp = client.get(f"/api/documents/{doc_id}/status", headers=headers)
        status_resp.raise_for_status()
        status = status_resp.json()["status"]
        
        if status == "ready":
            print("\n[SUCCESS] Document ingestion complete and verified!")
            break
        elif status == "error":
            print("\n[ERROR] Document ingestion failed in the backend/QVAC pipeline.")
            sys.exit(1)
        
        print(".", end="", flush=True)
        time.sleep(3)

if __name__ == "__main__":
    main()