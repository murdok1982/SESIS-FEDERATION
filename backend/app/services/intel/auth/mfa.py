"""
TOTP MFA helpers.

Provides:
    * Random base32 secret generation (32 bytes of entropy).
    * Provisioning URI for ``otpauth://totp/...``.
    * Six-digit code verification with a one-step window
      (compensates for small clock drift between server and device).
    * AES-256-GCM encryption / decryption of the secret at rest.
      The encryption key comes from ``settings.MFA_ENCRYPTION_KEY``
      (32 bytes hex). The ciphertext is stored as
      ``base64(nonce || ciphertext_with_tag)`` so it can live in a
      ``String`` column without escaping issues.

NOTE: codes, plain secrets and recovery codes MUST NEVER hit any
log line. Only metadata is auditable.
"""

from __future__ import annotations

import base64
import logging
import os
import secrets
from typing import List, Optional

import pyotp
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Recovery code helpers (plain text — to be bcrypt-hashed before storing)
# ---------------------------------------------------------------------------

# Alphabet excludes ambiguous characters (0/O, 1/I/l) for easy transcription.
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_recovery_codes(count: int | None = None, length: int = 10) -> List[str]:
    """Return *count* unambiguous, single-use recovery codes.

    Codes are formatted as two five-character groups separated by a
    dash (e.g. ``XJ4K2-PQ7N9``) and use a cryptographically strong RNG.
    The caller is responsible for hashing them with bcrypt before
    persisting and for displaying the plaintext to the user exactly
    once.
    """
    if count is None:
        count = settings.MFA_RECOVERY_CODES_COUNT
    out: List[str] = []
    for _ in range(count):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(length))
        out.append(f"{raw[: length // 2]}-{raw[length // 2 :]}")
    return out


# ---------------------------------------------------------------------------
# TOTP service
# ---------------------------------------------------------------------------


class TOTPService:
    """Stateless TOTP helper bound to the configured AES-GCM key."""

    DEFAULT_DIGITS = 6
    DEFAULT_INTERVAL = 30  # seconds
    DEFAULT_VERIFY_WINDOW = 1  # +/- one interval -> tolerates ~30s drift

    def __init__(
        self,
        issuer: Optional[str] = None,
        encryption_key_hex: Optional[str] = None,
    ) -> None:
        self.issuer = issuer or settings.MFA_ISSUER
        # Encryption key may be empty in non-state-grade dev mode. We
        # only enforce its presence when encrypt/decrypt is actually
        # called, so unit tests can import this module without env.
        self._encryption_key_hex = (
            encryption_key_hex
            if encryption_key_hex is not None
            else settings.MFA_ENCRYPTION_KEY
        )

    # ------------------------------------------------------------------
    # Secret generation & verification
    # ------------------------------------------------------------------

    @staticmethod
    def generate_secret() -> str:
        """Return a base32 TOTP secret (32 bytes of entropy)."""
        return pyotp.random_base32(length=52)

    def provisioning_uri(self, email: str, secret: str) -> str:
        """Build the ``otpauth://`` URI consumed by authenticator apps."""
        return pyotp.TOTP(
            secret,
            digits=self.DEFAULT_DIGITS,
            interval=self.DEFAULT_INTERVAL,
        ).provisioning_uri(name=email, issuer_name=self.issuer)

    def verify_code(
        self,
        secret: str,
        code: str,
        *,
        valid_window: int = DEFAULT_VERIFY_WINDOW,
    ) -> bool:
        """Verify a 6-digit TOTP code with a small tolerance window.

        Returns ``False`` for any malformed input rather than raising,
        so the caller can use a uniform 401 response and rate limit
        the endpoint without leaking failure shapes.
        """
        if not secret or not code:
            return False
        code = code.strip().replace(" ", "")
        if not code.isdigit() or len(code) != self.DEFAULT_DIGITS:
            return False
        try:
            return pyotp.TOTP(
                secret,
                digits=self.DEFAULT_DIGITS,
                interval=self.DEFAULT_INTERVAL,
            ).verify(code, valid_window=valid_window)
        except Exception:  # pragma: no cover - defensive
            logger.warning("mfa.verify.malformed_secret_or_code")
            return False

    # ------------------------------------------------------------------
    # AES-GCM encryption at rest
    # ------------------------------------------------------------------

    def _key(self) -> bytes:
        if not self._encryption_key_hex:
            raise RuntimeError(
                "MFA_ENCRYPTION_KEY not configured — cannot encrypt MFA secrets. "
                "Set MFA_ENCRYPTION_KEY in the environment (openssl rand -hex 32)."
            )
        try:
            key = bytes.fromhex(self._encryption_key_hex)
        except ValueError as exc:
            raise RuntimeError(
                "MFA_ENCRYPTION_KEY must be hex-encoded."
            ) from exc
        if len(key) != 32:
            raise RuntimeError(
                "MFA_ENCRYPTION_KEY must decode to 32 bytes (256-bit AES key)."
            )
        return key

    def encrypt_secret(self, secret: str) -> str:
        """Encrypt the base32 secret with AES-256-GCM.

        Output format: ``base64(nonce[12] || ciphertext || tag[16])``.
        """
        if not secret:
            raise ValueError("Cannot encrypt empty secret")
        aesgcm = AESGCM(self._key())
        nonce = os.urandom(12)
        ct = aesgcm.encrypt(nonce, secret.encode("utf-8"), associated_data=None)
        return base64.b64encode(nonce + ct).decode("ascii")

    def decrypt_secret(self, encrypted: str) -> str:
        """Reverse :meth:`encrypt_secret`. Raises ``RuntimeError`` on tampering."""
        if not encrypted:
            raise ValueError("Cannot decrypt empty payload")
        try:
            raw = base64.b64decode(encrypted.encode("ascii"))
        except Exception as exc:  # pragma: no cover - input validation
            raise RuntimeError("Corrupted MFA secret payload") from exc
        if len(raw) < 12 + 16:
            raise RuntimeError("MFA secret payload truncated")
        nonce, ct = raw[:12], raw[12:]
        aesgcm = AESGCM(self._key())
        try:
            plain = aesgcm.decrypt(nonce, ct, associated_data=None)
        except Exception as exc:
            # Includes InvalidTag — the audit chain should record this
            # as a tamper attempt at the call site.
            raise RuntimeError("MFA secret authentication failed") from exc
        return plain.decode("utf-8")


# Singleton bound to the live settings. Tests may instantiate a fresh
# TOTPService with custom keys / issuer.
totp_service = TOTPService()


__all__ = ["TOTPService", "totp_service", "generate_recovery_codes"]
