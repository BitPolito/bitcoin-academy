from sqlalchemy import create_engine
from app.core.config import settings
from app.db.models import Base
import sqlite3
import sys
from pathlib import Path

# Add the parent directory to sys.path to allow imports from app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def init_db():
    print(f"Initializing database at {settings.DATABASE_URL}")

    if "sqlite" in settings.DATABASE_URL:
        db_path = settings.DATABASE_URL.replace("sqlite:///", "")

        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # Create engine and tables
        engine = create_engine(settings.DATABASE_URL)
        Base.metadata.create_all(engine)
        print("Database schema applied successfully.")
    else:
        print("Only SQLite is supported for this script currently.")


if __name__ == "__main__":
    init_db()