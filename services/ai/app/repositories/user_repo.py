"""User repository - data access for user aggregate."""
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import User, UserRole


class UserRepository:
    """Repository for User database operations."""

    def __init__(self, db: Session):
        """
        Initialize the repository with a database session.

        Args:
            db: SQLAlchemy database session.
        """
        self.db = db

    def get_by_id(self, user_id: str) -> Optional[User]:
        """
        Get a user by their ID.

        Args:
            user_id: The user's unique identifier.

        Returns:
            The User if found, None otherwise.
        """
        return self.db.query(User).filter(User.id == user_id).first()

    def get_by_email(self, email: str) -> Optional[User]:
        """
        Get a user by their email address.

        Args:
            email: The user's email address.

        Returns:
            The User if found, None otherwise.
        """
        return self.db.query(User).filter(User.email == email).first()

    def email_exists(self, email: str) -> bool:
        """
        Check if an email address is already registered.

        Args:
            email: The email address to check.

        Returns:
            True if the email exists, False otherwise.
        """
        return self.db.query(User).filter(User.email == email).first() is not None

    def create(
        self,
        email: str,
        hashed_password: str,
        display_name: Optional[str] = None,
        role: UserRole = UserRole.STUDENT,
    ) -> User:
        """
        Create a new user in the database.

        Args:
            email: The user's email address.
            hashed_password: The bcrypt-hashed password.
            display_name: Optional display name.
            role: The user's role (defaults to STUDENT).

        Returns:
            The newly created User.
        """
        user = User(
            email=email,
            password_hash=hashed_password,
            display_name=display_name,
            role=role,
        )

        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update(self, user: User) -> User:
        """
        Update an existing user in the database.

        Args:
            user: The User object with updated fields.

        Returns:
            The updated User.
        """
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete(self, user_id: str) -> bool:
        """
        Delete a user from the database.

        Args:
            user_id: The user's unique identifier.

        Returns:
            True if the user was deleted, False if not found.
        """
        user = self.get_by_id(user_id)
        if user:
            self.db.delete(user)
            self.db.commit()
            return True
        return False
