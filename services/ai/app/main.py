"""FastAPI application entry point."""
from fastapi import FastAPI
from app.api.courses_api import router as courses_router

app = FastAPI(title="Courses API", version="1.0.0")

# Include the courses router
app.include_router(courses_router)
