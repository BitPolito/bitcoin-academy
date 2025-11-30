from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.config import settings, get_password_hash
from app.db.models import Base, User, UserRole
import sqlite3
import sys
from pathlib import Path

# Add the parent directory to sys.path to allow imports from app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def seed_test_users(engine):
    """Seed database with test users (admin and student)."""
    session = Session(engine)

    try:
        # Check if users already exist
        admin_exists = session.query(User).filter_by(
            email="admin@bitpolito.it").first()
        student_exists = session.query(User).filter_by(
            email="student@bitpolito.it").first()

        if not admin_exists:
            admin_user = User(
                email="admin@bitpolito.it",
                password_hash=get_password_hash("admin123"),
                display_name="Admin User",
                role=UserRole.ADMIN
            )
            session.add(admin_user)
            print("✓ Created admin user (admin@bitpolito.it / admin123)")
        else:
            print("✓ Admin user already exists")

        if not student_exists:
            student_user = User(
                email="student@bitpolito.it",
                password_hash=get_password_hash("student123"),
                display_name="Student User",
                role=UserRole.STUDENT
            )
            session.add(student_user)
            print("✓ Created student user (student@bitpolito.it / student123)")
        else:
            print("✓ Student user already exists")

        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Error seeding test users: {e}")
    finally:
        session.close()


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

        # Seed test users for development
        print("\nSeeding test users...")
        seed_test_users(engine)
        print("Database initialization complete!")
    else:
        print("Only SQLite is supported for this script currently.")


if __name__ == "__main__":
    init_db()
