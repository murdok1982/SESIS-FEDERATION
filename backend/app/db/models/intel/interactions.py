from sqlalchemy import Boolean, Column, String, ForeignKey, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime
from sqlalchemy.orm import declarative_base
Base = declarative_base()

class ChatSession(Base):
    """
    Ties a user interaction STRICTLY to a specific report ID to enact RAG limits.
    """
    __tablename__ = "chat_sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    report_bind_id = Column(UUID(as_uuid=True), nullable=False) 
    created_at = Column(DateTime, default=datetime.utcnow)

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"))
    role = Column(String, nullable=False) # 'user', 'assistant'
    content = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class ScenarioRun(Base):
    __tablename__ = "scenario_runs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    report_id = Column(UUID(as_uuid=True), nullable=False)
    input_variables = Column(JSON, nullable=False) # e.g. {"driver": "economic collapse"}
    output_markdown = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class ContributorSubmission(Base):
    __tablename__ = "contributor_submissions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alias = Column(String, nullable=True) # Voluntary structured intake
    phone = Column(String, nullable=True) # Exclusively if explicit consent was given
    country = Column(String, nullable=False)
    category = Column(String, nullable=False)
    description = Column(String, nullable=False)
    actors = Column(String, nullable=True)
    confidence = Column(String, nullable=True)
    consent_recorded = Column(Boolean, default=False)
    status = Column(String, default="pending_review")
    created_at = Column(DateTime, default=datetime.utcnow)
