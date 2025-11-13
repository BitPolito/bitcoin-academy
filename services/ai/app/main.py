"""FastAPI application entry point."""
from fastapi import FastAPI
from api.courses_api import router as courses_router

app = FastAPI(title="Courses API", version="1.0.0")

# Includi il router dei corsi
app.include_router(courses_router)