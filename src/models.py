from src.config.database import Base

from sqlalchemy import Column, UUID, String, Integer, Float
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, ENUM, TEXT, BOOLEAN, ARRAY, DATE
from sqlalchemy import text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy import func
from geoalchemy2 import Geometry
from enum import Enum
import uuid


time_diff_interval = text("INTERVAL '5 hours 30 minutes'")
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
    # GENERATED = "generated"
    PENDING = "pending"
    WORK_IN_PROGRESS = "wip"
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
    mode = Column(String(10))
    full_text = Column(TEXT, comment="The full article content for manual mode.", nullable=True)
    full_text_hash = Column(String(64), nullable=True, index=True)
    tone = Column(String(50))
    style = Column(String(50))
    language = Column(String(50))
    word_length = Column(String(20))
    word_length_range = Column(String(50))
    created_at = Column(TIMESTAMP, server_default=func.now() + time_diff_interval)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now() + time_diff_interval)
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
    # Keeping question_type for backward compatibility but making it nullable
    question_type = Column("question_type", ENUM("what", "who", "where", "why", "when", "how", "sources", name="question_type"), nullable=True)
    question_text = Column(TEXT, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now()+time_diff_interval)
    is_active = Column(BOOLEAN, default=True)

    user_story = relationship("UserStories", back_populates="questions")

class UserStoriesAnswers(Base):
    __tablename__ = "user_stories_answers"

    id = Column(UUID, primary_key=True, index=True, server_default=text("uuid_generate_v4()"))
    user_story_id = Column(UUID(as_uuid=True), ForeignKey('user_stories.id'), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey('user_stories_questions.id'), nullable=False)
    answer_text = Column(TEXT, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now()+time_diff_interval)
    updated_at = Column(TIMESTAMP, server_default=func.now(), server_onupdate=func.now()+time_diff_interval)

    user_story = relationship("UserStories", back_populates="answers")

    __table_args__ = (
        UniqueConstraint('user_story_id', 'question_id', name='unique_user_story_question'),
    )

class NewsCategory(str, Enum):
    LOCAL_NEWS = "local-news"
    INDIA = "india"
    WORLD = "world"
    POLITICS = "politics"
    SPORTS = "sports"
    ENTERTAINMENT = "entertainment"
    CRIME = "crime"
    BUSINESS = "business"
    CIVIC_ISSUES = "civic-issues"
    TECHNOLOGY = "technology"
    ENVIRONMENT = "environment"
    CULTURE = "culture"
    GENERAL = "general"

news_category_enum = ENUM(*[category.value for category in NewsCategory], name="news_category")

class GeneratedUserStories(Base):
    __tablename__ = "generated_user_stories"

    id = Column(UUID, primary_key=True, index=True, server_default=text("uuid_generate_v4()"))
    user_story_id = Column(UUID(as_uuid=True), ForeignKey('user_stories.id'), nullable=False)
    author_id = Column(UUID(as_uuid=True), ForeignKey('authors.id'), nullable=False)
    title = Column(TEXT)
    title_hash = Column(String(64), nullable=True, index=True, unique=True)
    english_title = Column(TEXT)
    slug = Column(TEXT, unique=True, index=True)
    snippet = Column(TEXT)
    full_text = Column(TEXT)
    full_text_hash = Column(String(64), unique=True, index=True)
    category = Column("category", ARRAY(news_category_enum), default=[NewsCategory.GENERAL])
    tags = Column("tags", ARRAY(String), default=list)
    images_keys = Column("images_keys", ARRAY(String), default=list)
    created_at = Column(TIMESTAMP, server_default=func.now()+time_diff_interval)
    published_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP, onupdate=func.now()+time_diff_interval)
    editor_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)

    __table_args__ = (
        UniqueConstraint('author_id', 'title_hash', name='uq_author_titlehash'),
    )

    user_story = relationship("UserStories", back_populates="generated_stories", lazy='selectin')
    author = relationship("Authors", back_populates="generated_user_stories", lazy='selectin')
    editor = relationship("Users", foreign_keys=[editor_id], lazy='selectin')

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
    phone = Column(String(50), unique=True)
    username = Column(String(255), unique=True, index=True, nullable=True)
    password = Column(String(255), nullable=False)
    role = Column(
        user_roles_enum,
        nullable=False,
        index=True,
    )
    profile_image_key = Column(String(200))
    active = Column(BOOLEAN, default=True)
    added_on = Column(TIMESTAMP, nullable=False, server_default=func.now())
    added_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    approved_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    approved_at = Column(TIMESTAMP, nullable=True)
    author_profile = relationship("Authors", back_populates="user", lazy="selectin", uselist=False, cascade="delete")


class Authors(Base):
    __tablename__ = "authors"

    id = Column(
        UUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    bio = Column(TEXT, nullable=True)
    # date_of_birth = Column(DATE, nullable=True)
    # highest_education = Column(String(50), nullable=True)
    # highest_education_other_specify = Column(String(100), nullable=True)
    # work_status = Column(String(50), nullable=True)
    # work_status_other_specify = Column(String(100), nullable=True)
    # city_id = Column(UUID(as_uuid=True), ForeignKey('cities.id'), nullable=True)
    # updated_at = Column(TIMESTAMP, server_onupdate=func.now())
    # onboarding_completed = Column(BOOLEAN, default=False)
    
    user = relationship("Users", back_populates="author_profile", lazy="selectin")
    user_stories = relationship("UserStories", back_populates="author", lazy="selectin")
    generated_user_stories = relationship(
        "GeneratedUserStories", back_populates="author", lazy="selectin"
    )

# class UserLinks(Base):
#     __tablename__ = "user_links"

#     id = Column(UUID(as_uuid=True), primary_key=True, index=True, server_default=text("uuid_generate_v4()"))
#     user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
#     link_type = Column(String(50))
#     platform = Column(String(50))
#     url = Column(String(500))
#     description = Column(String(200))

# class Cities(Base):
#     __tablename__ = "cities"
    
#     id = Column(UUID(as_uuid=True), primary_key=True, index=True, server_default=text("uuid_generate_v4()"))
#     name = Column(String(100), nullable=False)
#     active = Column(BOOLEAN, default=True)


# class EditorCities(Base):
#     __tablename__ = "editor_cities"
    
#     id = Column(UUID(as_uuid=True), primary_key=True, index=True, server_default=text("uuid_generate_v4()"))
#     editor_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
#     city_id = Column(UUID(as_uuid=True), ForeignKey('cities.id'), nullable=False)
    
#     __tableargs__ = (
#         UniqueConstraint('editor_id', 'city_id', name='unique_editor_city'),
#     )
    
    
# class Categories(Base):
#     __tablename__ = "categories"
    
#     id = Column(UUID(as_uuid=True), primary_key=True, index=True, server_default=text("uuid_generate_v4()"))
#     name = Column(String(100), nullable=False)
#     value = Column(String(100), nullable=False)
#     active = Column(BOOLEAN, default=True)
    
# class EditorCategories(Base):
#     __tablename__ = "editor_categories"
    
#     id = Column(UUID(as_uuid=True), primary_key=True, index=True, server_default=text("uuid_generate_v4()"))
#     editor_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
#     category_id = Column(UUID(as_uuid=True), ForeignKey('categories.id'), nullable=False)
    
#     __tableargs__ = (
#         UniqueConstraint('editor_id', 'category_id', name='unique_editor_category'),
#     )
    

##==Top Advisor Tables==##

from sqlalchemy.dialects.postgresql import JSONB

class ChatSessions(Base):
    __tablename__ = "chat_sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, index=True, server_default=text("uuid_generate_v4()"))
    session_id = Column(String(255), unique=True, comment="Unique session id generated by the frontend")
    thread_id = Column(String(255), unique=True, index=True, comment="Unique thread id generated by openai threads api")
    assistant_id = Column(String(255), comment="openai assistant id")
    goal = Column(String(128))
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_onupdate=func.now())

    name = Column(String(255))
    phone = Column(String(20))
    collected_data = Column(JSONB, default={})
    lead_captured = Column(BOOLEAN, default=False)
# Police Whatsapp Chatbot Tables

class PoliceStations(Base):
    __tablename__ = "police_stations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, index=True, server_default=text("uuid_generate_v4()"))
    name = Column(String(200))
    address = Column(TEXT)
    boundary = Column(Geometry(geometry_type='POLYGON', srid=4326))
    lat = Column(Float)
    lon = Column(Float)
    pi_name = Column(String(100))
    pi_phone = Column(String(20))
    zone = Column(String(100))

