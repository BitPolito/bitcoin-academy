from fastapi import FastAPI, UploadFile, File, HTTPException

app = FastAPI(title="BitPolito Academy API")

fake_courses_db = {}
fake_documents_db = {}

@app.post("/courses")
def create_course(name: str):
    
    course_id = f"course_{len(fake_courses_db) + 1}"
    
    fake_courses_db[course_id] = {"id": course_id, "name": name}
    
    return fake_courses_db[course_id]

@app.post("/courses/{course_id}/documents")
def upload_document(course_id: str, file: UploadFile = File(...)):
    
    if course_id not in fake_courses_db:
        raise HTTPException(status_code=404, detail="No such lesson was found.")
    
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files can be uploaded!")

    doc_id = f"doc_{len(fake_documents_db) + 1}"
    doc_data = {
        "id": doc_id,
        "course_id": course_id,
        "filename": file.filename,
        "status": "pending" 
    }
    fake_documents_db[doc_id] = doc_data
    
    return {"message": "File has succesfully uploaded", "document": doc_data}

@app.get("/courses/{course_id}/documents")
def list_documents(course_id: str):
    docs = [doc for doc in fake_documents_db.values() if doc["course_id"] == course_id]
    return {"course_id": course_id, "documents": docs}

@app.get("/courses/{course_id}/processing-status")
def get_processing_status(course_id: str):
    docs = [doc for doc in fake_documents_db.values() if doc["course_id"] == course_id]
    if not docs:
        return {"course_id": course_id, "status": "No files have been uploaded yet."}
    
    return {"course_id": course_id, "documents_status": docs}