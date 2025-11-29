import os
from pathlib import Path

class Settings:
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/app.db")

settings = Settings()
