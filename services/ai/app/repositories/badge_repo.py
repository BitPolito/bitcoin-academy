"""Badge repository - data access for badge definitions and awards."""
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.db.models import Badge, UserBadge


def get_all_badges(db: Session) -> List[Badge]:
    return db.query(Badge).all()


def get_badge_by_slug(db: Session, slug: str) -> Optional[Badge]:
    return db.query(Badge).filter_by(slug=slug).first()


def get_user_badges(db: Session, user_id: str) -> List[UserBadge]:
    return (
        db.query(UserBadge)
        .filter_by(user_id=user_id)
        .order_by(UserBadge.earned_at.desc())
        .all()
    )


def has_user_badge(db: Session, user_id: str, badge_id: str) -> bool:
    return (
        db.query(UserBadge)
        .filter_by(user_id=user_id, badge_id=badge_id)
        .first()
    ) is not None


def award_badge(
    db: Session,
    user_id: str,
    badge_id: str,
    context_id: Optional[str] = None,
) -> UserBadge:
    record = UserBadge(
        user_id=user_id,
        badge_id=badge_id,
        earned_at=datetime.now(),
        context_id=context_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
