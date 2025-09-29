from src.config.database import Base

from sqlalchemy import Column, UUID, String, Integer
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, ENUM, TEXT, BOOLEAN
from sqlalchemy import text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy import func
from enum import Enum
import uuid

class Locations(Base):
    __tablename__ = "locations"

    id = Column(UUID(as_uuid=True), primary_key=True, index=True, server_default=text("uuid_generate_v4()"))
    city = Column(String(50))
    state = Column(String(50))
    country = Column(String(50))
    country_code = Column(String(8))
    level = Column("level", ENUM("CITY", "STATE", "COUNTRY", "INTERNATIONAL", name="location_level"), nullable=False)
    last_fetched_timestamp = Column(TIMESTAMP, index=True, nullable=True)
    refresh_interval_mins = Column(Integer)
    max_days_back = Column(Integer, default=3)

    stories = relationship("StoriesRaw", back_populates="location")

class StoriesRaw(Base):
    __tablename__ = "stories_raw"

    id = Column(UUID, primary_key=True, index=True, server_default=text("uuid_generate_v4()"))
    title = Column(TEXT)
    snippet = Column(TEXT) # description
    thumbnail = Column(String(300))
    link = Column(String(500))
    published_timestamp = Column(TIMESTAMP)
    source = Column(String(100))
    location_id = Column(UUID(as_uuid=True), ForeignKey('locations.id'), nullable=False)

    location = relationship("Locations", back_populates="stories")

# class GeneratedStories(Base):
#     __tablename__ = "generated_stories"

#     id = Column(UUID, primary_key=True, index=True, server_default=text("uuid_generate_v4()"))
#     title = Column(TEXT)
#     snippet = Column(TEXT)
#     generated_at = Column(TIMESTAMP)
#     original_story_id = Column(UUID(as_uuid=True), ForeignKey('stories_raw.id'), nullable=False)

from enum import Enum

class UserStoryStatus(str, Enum):
    COLLECTING = "collecting"
    # DRAFTING = "drafting"
    GENERATED = "generated"
    SUBMITTED = "submitted"

# THis is for editor article status
class UserStoryPublishStatus(str, Enum):
    # DRAFT = "draft"
    # GENERATED = "generated"\
    PENDING = "pending"
    PUBLISHED = "published"
    REJECTED = "rejected"

user_stories_status_enum = ENUM(*[status.value for status in UserStoryStatus], name="user_story_status")
user_stories_publish_status_enum = ENUM(*[status.value for status in UserStoryPublishStatus], name="user_story_publish_status")

class UserStories(Base):
    __tablename__ = "user_stories"

    id = Column(UUID, primary_key=True, index=True, server_default=text("uuid_generate_v4()"))
    author_id = Column(UUID(as_uuid=True), ForeignKey('authors.id'))
    title = Column(String(255), nullable=True)
    title_hash = Column(String(64), unique=True, index=True, nullable=True)
    context = Column(TEXT)
    context_hash = Column(String(64), unique=True, index=True)
    mode = Column(String(20))
    full_text = Column(TEXT, comment="The full article content for manual mode.", nullable=True)
    full_text_hash = Column(String(64), nullable=True, index=True)
    tone = Column(String(50))
    style = Column(String(50))
    language = Column(String(50))
    word_length = Column(String(20))
    word_length_range = Column(String(50))
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    status = Column("status",user_stories_status_enum, default=UserStoryStatus.COLLECTING)
    # status = Column(String(20), default=UserStoryStatus.COLLECTING)
    publish_status = Column("publish_status", user_stories_publish_status_enum, default=UserStoryPublishStatus.PENDING)
    rejection_reason = Column(TEXT, default=None)
    # publish_status = Column(String(20), default=UserStoryPublishStatus.PENDING)

    author = relationship("Authors", back_populates="user_stories")
    questions = relationship("UserStoriesQuestions", back_populates="user_story", lazy="selectin")
    answers = relationship("UserStoriesAnswers", back_populates="user_story", lazy="selectin")
    generated_stories = relationship("GeneratedUserStories", back_populates="user_story", lazy="selectin")

class UserStoriesQuestions(Base):
    __tablename__ = "user_stories_questions"

    id = Column(UUID, primary_key=True, index=True, server_default=text("uuid_generate_v4()"))
    user_story_id = Column(UUID(as_uuid=True), ForeignKey('user_stories.id'), nullable=False)
    question_key = Column(String(50))
    question_type = Column("question_type", ENUM("what", "who", "where", "why", "when", "how", "sources", name="question_type"))
    question_text = Column(TEXT, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    is_active = Column(BOOLEAN, default=True)

    user_story = relationship("UserStories", back_populates="questions")

class UserStoriesAnswers(Base):
    __tablename__ = "user_stories_answers"

    id = Column(UUID, primary_key=True, index=True, server_default=text("uuid_generate_v4()"))
    user_story_id = Column(UUID(as_uuid=True), ForeignKey('user_stories.id'), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey('user_stories_questions.id'), nullable=False)
    answer_text = Column(TEXT, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), server_onupdate=func.now())

    user_story = relationship("UserStories", back_populates="answers")

    __table_args__ = (
        UniqueConstraint('user_story_id', 'question_id', name='unique_user_story_question'),
    )

class GeneratedUserStories(Base):
    __tablename__ = "generated_user_stories"

    id = Column(UUID, primary_key=True, index=True, server_default=text("uuid_generate_v4()"))
    user_story_id = Column(UUID(as_uuid=True), ForeignKey('user_stories.id'))
    author_id = Column(UUID(as_uuid=True), ForeignKey('authors.id'), nullable=False)
    title = Column(TEXT)
    snippet = Column(TEXT)
    full_text = Column(TEXT)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, onupdate=func.now())
    editor_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)

    user_story = relationship("UserStories", back_populates="generated_stories")
    author = relationship("Authors", back_populates="generated_user_stories")
    editor = relationship("Users", foreign_keys=[editor_id])

class UserRoles(str, Enum):
    ADMIN = "admin"
    CREATOR = "creator"
    EDITOR = "editor"

user_roles_enum = ENUM(*[role.value for role in UserRoles], name="user_roles")

class Users(Base):
    __tablename__ = "users"

    id = Column(
        UUID, primary_key=True, index=True, server_default=text("uuid_generate_v4()")
    )
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100))
    email = Column(String(255), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    role = Column(
        user_roles_enum,
        nullable=False,
        index=True,
    )
    author_profile = relationship("Authors", back_populates="user", uselist=False)


class Authors(Base):
    __tablename__ = "authors"

    id = Column(
        UUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    bio = Column(TEXT, nullable=True)
    updated_at = Column(TIMESTAMP, server_onupdate=func.now())
    user = relationship("Users", back_populates="author_profile")
    user_stories = relationship("UserStories", back_populates="author", lazy="selectin")
    generated_user_stories = relationship(
        "GeneratedUserStories", back_populates="author", lazy="selectin"
    )
    