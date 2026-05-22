from sqlalchemy import Column, String, Boolean, DateTime, Enum, Integer
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum
from datetime import datetime
from sqlalchemy.orm import declarative_base
Base = declarative_base()

from app.core.classification import ClassificationLevel, TLPMarker


class RoleEnum(str, enum.Enum):
    user = "user"
    institutional = "institutional"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(RoleEnum), default=RoleEnum.user, nullable=False)
    is_active = Column(Boolean, default=True)
    two_factor_enabled = Column(Boolean, default=False)
    # MFA TOTP shared secret (encrypted at rest in P2). Nullable until
    # the user enrolls.
    mfa_secret = Column(String, nullable=True)
    # Hierarchical clearance level. Stored as integer to match the
    # Postgres RLS policies which compare against
    # ``current_setting('app.user_clearance')``.
    clearance_level = Column(
        Integer,
        nullable=False,
        default=ClassificationLevel.PUBLIC.value,
        server_default=ClassificationLevel.PUBLIC.value,
    )
    # Tenant / organization scope. NULL = global user (admin etc).
    org_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
