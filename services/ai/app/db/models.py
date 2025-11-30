import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


# Enums
class UserRole(str, Enum):
    STUDENT = "student"
    INSTRUCTOR = "instructor"
    ADMIN = "admin"


class QuizScope(str, Enum):
    LESSON = "lesson"
    CHAPTER_TEST = "chapter_test"


class QuestionType(str, Enum):
    MCQ = "mcq"
    TRUEFALSE = "truefalse"
    SHORT = "short"


class ResourceParentType(str, Enum):
    COURSE = "course"
    CHAPTER = "chapter"
    LESSON = "lesson"


# 1. Users
class User(Base):
    __tablename__ = "app_user"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[Optional[str]] = mapped_column(String, unique=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String)
    display_name: Mapped[Optional[str]] = mapped_column(String)
    role: Mapped[UserRole] = mapped_column(
        String, default=UserRole.STUDENT
    )  # Storing as String to match SQL CHECK constraint
    created_at: Mapped[datetime] = mapped_column(
        String, default=func.now()
    )  # SQL uses TEXT for ISO datetime

    # Relationships
    quiz_attempts: Mapped[List["QuizAttempt"]
                          ] = relationship(back_populates="user")
    certificates: Mapped[List["Certificate"]
                         ] = relationship(back_populates="user")
    lesson_progress: Mapped[List["UserLessonProgress"]] = relationship(
        back_populates="user"
    )
    chapter_progress: Mapped[List["UserChapterProgress"]] = relationship(
        back_populates="user"
    )
    course_progress: Mapped[List["UserCourseProgress"]] = relationship(
        back_populates="user"
    )
    created_resources: Mapped[List["Resource"]
                              ] = relationship(back_populates="creator")


# 2. Learning Structure
class Section(Base):
    __tablename__ = "section"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    title: Mapped[str] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(Text)

    courses: Mapped[List["Course"]] = relationship(back_populates="section")


class Course(Base):
    __tablename__ = "course"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    section_id: Mapped[str] = mapped_column(ForeignKey("section.id"))
    title: Mapped[str] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    section: Mapped["Section"] = relationship(back_populates="courses")
    chapters: Mapped[List["Chapter"]] = relationship(back_populates="course")
    progress: Mapped[List["UserCourseProgress"]
                     ] = relationship(back_populates="course")
    certificates: Mapped[List["Certificate"]
                         ] = relationship(back_populates="course")


class Chapter(Base):
    __tablename__ = "chapter"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    course_id: Mapped[str] = mapped_column(ForeignKey("course.id"))
    title: Mapped[str] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    course: Mapped["Course"] = relationship(back_populates="chapters")
    lessons: Mapped[List["Lesson"]] = relationship(back_populates="chapter")
    chapter_tests: Mapped[List["ChapterTest"]
                          ] = relationship(back_populates="chapter")
    progress: Mapped[List["UserChapterProgress"]] = relationship(
        back_populates="chapter"
    )


class Lesson(Base):
    __tablename__ = "lesson"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapter.id"))
    title: Mapped[str] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    chapter: Mapped["Chapter"] = relationship(back_populates="lessons")
    quizzes: Mapped[List["Quiz"]] = relationship(back_populates="lesson")
    progress: Mapped[List["UserLessonProgress"]
                     ] = relationship(back_populates="lesson")


# 3. Assessments
class Quiz(Base):
    __tablename__ = "quiz"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scope: Mapped[QuizScope] = mapped_column(String)
    title: Mapped[Optional[str]] = mapped_column(String)
    passing_score: Mapped[int] = mapped_column(Integer, default=70)
    lesson_id: Mapped[Optional[str]] = mapped_column(ForeignKey("lesson.id"))

    lesson: Mapped[Optional["Lesson"]] = relationship(back_populates="quizzes")
    questions: Mapped[List["Question"]] = relationship(back_populates="quiz")
    attempts: Mapped[List["QuizAttempt"]] = relationship(back_populates="quiz")

    # Many-to-many relationship with ChapterTest through ChapterTestQuiz
    chapter_tests: Mapped[List["ChapterTest"]] = relationship(
        secondary="chapter_test_quiz", back_populates="quizzes"
    )


class ChapterTest(Base):
    __tablename__ = "chapter_test"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapter.id"))
    title: Mapped[str] = mapped_column(String)

    chapter: Mapped["Chapter"] = relationship(back_populates="chapter_tests")
    quizzes: Mapped[List["Quiz"]] = relationship(
        secondary="chapter_test_quiz", back_populates="chapter_tests"
    )


class ChapterTestQuiz(Base):
    __tablename__ = "chapter_test_quiz"

    chapter_test_id: Mapped[str] = mapped_column(
        ForeignKey("chapter_test.id"), primary_key=True
    )
    quiz_id: Mapped[str] = mapped_column(
        ForeignKey("quiz.id"), primary_key=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)


class Question(Base):
    __tablename__ = "question"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    quiz_id: Mapped[str] = mapped_column(ForeignKey("quiz.id"))
    qtype: Mapped[QuestionType] = mapped_column(String)
    prompt: Mapped[str] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    source_ref: Mapped[Optional[str]] = mapped_column(String)

    quiz: Mapped["Quiz"] = relationship(back_populates="questions")
    options: Mapped[List["OptionChoice"]] = relationship(
        back_populates="question")
    answers: Mapped[List["AttemptAnswer"]] = relationship(
        back_populates="question")


class OptionChoice(Base):
    __tablename__ = "option_choice"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    question_id: Mapped[str] = mapped_column(ForeignKey("question.id"))
    label: Mapped[str] = mapped_column(String)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)

    question: Mapped["Question"] = relationship(back_populates="options")
    selected_in_answers: Mapped[List["AttemptAnswer"]] = relationship(
        back_populates="selected_option"
    )


class QuizAttempt(Base):
    __tablename__ = "quiz_attempt"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    quiz_id: Mapped[str] = mapped_column(ForeignKey("quiz.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("app_user.id"))
    started_at: Mapped[datetime] = mapped_column(String, default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(String)
    score_pct: Mapped[Optional[int]] = mapped_column(Integer)
    passed: Mapped[Optional[bool]] = mapped_column(Boolean)

    quiz: Mapped["Quiz"] = relationship(back_populates="attempts")
    user: Mapped["User"] = relationship(back_populates="quiz_attempts")
    answers: Mapped[List["AttemptAnswer"]] = relationship(
        back_populates="attempt")


class AttemptAnswer(Base):
    __tablename__ = "attempt_answer"

    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("quiz_attempt.id"), primary_key=True)
    question_id: Mapped[str] = mapped_column(
        ForeignKey("question.id"), primary_key=True)
    selected_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("option_choice.id"))
    free_text: Mapped[Optional[str]] = mapped_column(Text)
    is_correct: Mapped[Optional[bool]] = mapped_column(Boolean)

    attempt: Mapped["QuizAttempt"] = relationship(back_populates="answers")
    question: Mapped["Question"] = relationship(back_populates="answers")
    selected_option: Mapped[Optional["OptionChoice"]] = relationship(
        back_populates="selected_in_answers"
    )


# 4. User Progress
class UserLessonProgress(Base):
    __tablename__ = "user_lesson_progress"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("app_user.id"), primary_key=True)
    lesson_id: Mapped[str] = mapped_column(
        ForeignKey("lesson.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String, default="not_started")
    last_activity: Mapped[datetime] = mapped_column(String, default=func.now())
    last_score: Mapped[Optional[int]] = mapped_column(Integer)

    user: Mapped["User"] = relationship(back_populates="lesson_progress")
    lesson: Mapped["Lesson"] = relationship(back_populates="progress")


class UserChapterProgress(Base):
    __tablename__ = "user_chapter_progress"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("app_user.id"), primary_key=True)
    chapter_id: Mapped[str] = mapped_column(
        ForeignKey("chapter.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String, default="not_started")
    last_activity: Mapped[datetime] = mapped_column(String, default=func.now())

    user: Mapped["User"] = relationship(back_populates="chapter_progress")
    chapter: Mapped["Chapter"] = relationship(back_populates="progress")


class UserCourseProgress(Base):
    __tablename__ = "user_course_progress"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("app_user.id"), primary_key=True)
    course_id: Mapped[str] = mapped_column(
        ForeignKey("course.id"), primary_key=True)
    percent: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="not_started")
    updated_at: Mapped[datetime] = mapped_column(String, default=func.now())

    user: Mapped["User"] = relationship(back_populates="course_progress")
    course: Mapped["Course"] = relationship(back_populates="progress")


# 5. Supplemental Materials
class Resource(Base):
    __tablename__ = "resource"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    parent_type: Mapped[ResourceParentType] = mapped_column(String)
    parent_id: Mapped[str] = mapped_column(String)  # No FK as it's polymorphic
    title: Mapped[str] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(Text)
    url: Mapped[Optional[str]] = mapped_column(String)
    resource_type: Mapped[str] = mapped_column(String, default="other")
    mime_type: Mapped[Optional[str]] = mapped_column(String)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(String, default=func.now())

    creator: Mapped[Optional["User"]] = relationship(
        back_populates="created_resources")


# 6. Certificates
class Certificate(Base):
    __tablename__ = "certificate"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("app_user.id"))
    course_id: Mapped[str] = mapped_column(ForeignKey("course.id"))
    issued_at: Mapped[datetime] = mapped_column(String, default=func.now())
    code: Mapped[str] = mapped_column(String, unique=True)
    verification_hash: Mapped[str] = mapped_column(String, unique=True)
    grade_pct: Mapped[Optional[int]] = mapped_column(Integer)
    hours: Mapped[Optional[int]] = mapped_column(Integer)
    issuer_name: Mapped[Optional[str]] = mapped_column(String)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(String)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped["User"] = relationship(back_populates="certificates")
    course: Mapped["Course"] = relationship(back_populates="certificates")
