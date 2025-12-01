from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.config import settings, get_password_hash
from app.db.models import Base, User, UserRole
import sqlite3
import sys
import secrets
from pathlib import Path

# Add the parent directory to sys.path to allow imports from app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Strong default passwords for development (still require change in production)
# These meet password requirements: 12+ chars, upper, lower, digit, special
DEV_ADMIN_PASSWORD = "DevAdmin@2024!Secure"
DEV_STUDENT_PASSWORD = "DevStudent@2024!Learn"


def seed_test_users(engine):
    """Seed database with test users (admin and student).

    WARNING: This function should ONLY be called in development environment.
    Test users have known passwords and should never exist in production.
    """
    # Security check: refuse to seed in production
    if settings.ENVIRONMENT == "production":
        print("⚠️  Skipping user seeding in production environment")
        print("   Create users through secure registration process instead.")
        return

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
                password_hash=get_password_hash(DEV_ADMIN_PASSWORD),
                display_name="Admin User",
                role=UserRole.ADMIN
            )
            session.add(admin_user)
            print(
                f"✓ Created admin user (admin@bitpolito.it / {DEV_ADMIN_PASSWORD})")
        else:
            print("✓ Admin user already exists")

        if not student_exists:
            student_user = User(
                email="student@bitpolito.it",
                password_hash=get_password_hash(DEV_STUDENT_PASSWORD),
                display_name="Student User",
                role=UserRole.STUDENT
            )
            session.add(student_user)
            print(
                f"✓ Created student user (student@bitpolito.it / {DEV_STUDENT_PASSWORD})")
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
