"""
Authentication-related ORM models.

Holds artefacts that complement the ``users`` table:

* :class:`MFARecoveryCode` — single-use recovery codes, hashed with
  bcrypt (only the hash is ever stored). The ``used_at`` timestamp
  marks consumption so the same code cannot be replayed.
* :class:`WebAuthnCredential` — placeholder for FIDO2 / WebAuthn
  credentials. The schema is ready (P3 will fill the verify flow),
  but the runtime endpoints currently return ``501 Not Implemented``.

NOTE: no plaintext code, password or TOTP secret ever lives in this
module. ``mfa_secret`` (on :class:`app.models.user.User`) is encrypted
with AES-GCM by :mod:`app.auth.mfa`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from sqlalchemy.orm import declarative_base
Base = declarative_base()


class MFARecoveryCode(Base):
    """Single-use MFA recovery code (bcrypt hash only)."""

    __tablename__ = "mfa_recovery_codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # bcrypt hash of the plaintext code. Plaintext is shown to the user
    # exactly once at enrollment and never persisted.
    code_hash = Column(String, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", backref="mfa_recovery_codes")


class WebAuthnCredential(Base):
    """FIDO2 / WebAuthn credential record (schema only — verify in P3+)."""

    __tablename__ = "webauthn_credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    credential_id = Column(LargeBinary, nullable=False, unique=True)
    public_key = Column(LargeBinary, nullable=False)
    sign_count = Column(Integer, default=0, nullable=False)
    transports = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)

    user = relationship("User", backref="webauthn_credentials")


__all__ = ["MFARecoveryCode", "WebAuthnCredential"]
