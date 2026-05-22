"""
Ed25519 cryptographic signing service for published intelligence reports.

This module provides:

* :class:`ReportSigner` — loads an Ed25519 keypair from disk and signs
  the canonical JSON representation of a daily or premium report.
* :data:`report_signer` — module-level singleton, initialized from
  ``settings.SIGNING_PRIVATE_KEY_PATH`` and
  ``settings.SIGNING_PUBLIC_KEY_PATH``.

Key material is read from disk on startup. In production the private
key SHOULD live on an HSM, an age/sops-encrypted volume, or Hashicorp
Vault — this module supports that simply by changing the configured
path. Private key bytes are kept only in memory and are NEVER stored
in the database nor written to logs.

Behaviour when keys are missing:

* ``STATE_GRADE_MODE=true``: signer is marked unavailable and any
  call to :meth:`ReportSigner.sign` raises
  :class:`SigningUnavailableError`. The publication endpoint MUST
  translate that into HTTP 503 so reports cannot be published
  unsigned.
* ``STATE_GRADE_MODE=false``: an ephemeral in-memory keypair is
  generated and a WARNING is logged. The fingerprint changes every
  process restart — useful for tests, never for production.

The canonical payload format is fixed; changing it is a wire-breaking
change because every previously signed report would fail verification.
If the canonical format needs to evolve, introduce a versioned tag in
the signature blob and keep verifying old-format reports with the old
canonicalizer.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.core.config import settings


logger = logging.getLogger(__name__)


class SigningError(Exception):
    """Base class for signing-related errors."""


class SigningUnavailableError(SigningError):
    """Raised when signing is required but no usable key is loaded."""


class ReportSigner:
    """Ed25519 signer for daily and premium reports.

    Key material is loaded from disk on startup and never touches the
    DB nor logs. In production the private key SHOULD live on an HSM
    or in an encrypted volume (age, sops, vault). The path is read
    from ``settings.SIGNING_PRIVATE_KEY_PATH`` and
    ``settings.SIGNING_PUBLIC_KEY_PATH``.

    If keys do not exist on startup and ``STATE_GRADE_MODE=true``, the
    application MUST refuse to publish reports (raise on
    :meth:`sign`).
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        private_key_path: str | None,
        public_key_path: str | None,
    ) -> None:
        self._private_key_path = (
            Path(private_key_path) if private_key_path else None
        )
        self._public_key_path = (
            Path(public_key_path) if public_key_path else None
        )
        self._private_key: Optional[Ed25519PrivateKey] = None
        self._public_key: Optional[Ed25519PublicKey] = None
        self._unavailable: bool = False
        self._ephemeral: bool = False
        self._load_or_fallback()

    # ------------------------------------------------------------------
    # Load / fallback
    # ------------------------------------------------------------------

    def _load_or_fallback(self) -> None:
        """Attempt to load keys; fall back per STATE_GRADE_MODE."""
        try:
            self._load_from_disk()
            return
        except FileNotFoundError as exc:
            reason = f"key files not found: {exc}"
        except Exception as exc:  # noqa: BLE001
            # Malformed file, permission denied, wrong algorithm, etc.
            reason = f"failed to parse key files: {exc.__class__.__name__}"

        if settings.STATE_GRADE_MODE:
            logger.critical(
                "ReportSigner: %s. State-grade mode is ON — publication will be refused.",
                reason,
            )
            self._unavailable = True
            return

        # Dev / test fallback: ephemeral in-memory key. Loud warning.
        logger.warning(
            "ReportSigner: %s. STATE_GRADE_MODE=false — generating "
            "EPHEMERAL in-memory keypair. Reports signed by this "
            "process WILL NOT verify after restart. Do not use in "
            "production.",
            reason,
        )
        priv = Ed25519PrivateKey.generate()
        self._private_key = priv
        self._public_key = priv.public_key()
        self._ephemeral = True

    def _load_from_disk(self) -> None:
        if not self._private_key_path or not self._public_key_path:
            raise FileNotFoundError("signing key paths not configured")
        if not self._private_key_path.is_file():
            raise FileNotFoundError(str(self._private_key_path))
        if not self._public_key_path.is_file():
            raise FileNotFoundError(str(self._public_key_path))

        priv_bytes = self._private_key_path.read_bytes()
        pub_bytes = self._public_key_path.read_bytes()

        priv = serialization.load_pem_private_key(
            priv_bytes, password=None
        )
        if not isinstance(priv, Ed25519PrivateKey):
            raise ValueError("private key is not Ed25519")
        pub = serialization.load_pem_public_key(pub_bytes)
        if not isinstance(pub, Ed25519PublicKey):
            raise ValueError("public key is not Ed25519")

        # Sanity: public key on disk MUST match the private key.
        if (
            priv.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            != pub.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        ):
            raise ValueError(
                "public key on disk does not match private key"
            )

        self._private_key = priv
        self._public_key = pub
        self._unavailable = False
        self._ephemeral = False

    # ------------------------------------------------------------------
    # Public state
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        return not self._unavailable and self._private_key is not None

    @property
    def ephemeral(self) -> bool:
        return self._ephemeral

    @property
    def public_key_pem(self) -> str:
        """PEM PKCS#8 SubjectPublicKeyInfo of the active public key."""
        if self._public_key is None:
            raise SigningUnavailableError("no public key loaded")
        return self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")

    @property
    def fingerprint(self) -> str:
        """First 8 bytes of sha256(raw_public_key), hex-encoded.

        16 hex chars — short enough to print in CLI tools and audit
        metadata, long enough to disambiguate operational keys.
        """
        if self._public_key is None:
            raise SigningUnavailableError("no public key loaded")
        raw = self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return hashlib.sha256(raw).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Canonical payload
    # ------------------------------------------------------------------

    @staticmethod
    def canonical_payload(report: Any) -> bytes:
        """Stable byte representation of a report for signing.

        The payload covers exactly the fields a downstream verifier
        cares about: identity, classification, the text content and
        the temporal markers. Anything else (``published`` flag,
        ``signature`` column, etc.) is intentionally excluded so a
        verifier can recompute the canonical bytes from the rendered
        report view alone.

        Output is deterministic: sorted keys, tight separators,
        ASCII-safe (``ensure_ascii=False`` but UTF-8 encoded).
        Optional fields that do not apply to a given report type are
        omitted from the dict rather than set to ``null`` — adding
        ``null`` later would silently change the canonical bytes for
        already-signed reports.
        """
        body: dict[str, Any] = {}
        # Identity / scope ----------------------------------------------------
        if getattr(report, "id", None) is not None:
            body["id"] = str(report.id)
        if getattr(report, "classification", None) is not None:
            body["classification"] = int(report.classification)
        tlp = getattr(report, "tlp", None)
        if tlp is not None:
            body["tlp"] = str(tlp)
        if getattr(report, "org_id", None) is not None:
            body["org_id"] = str(report.org_id)

        # Content -------------------------------------------------------------
        exec_summary = getattr(report, "executive_summary", None)
        if exec_summary is not None:
            body["executive_summary"] = exec_summary
        content_json = getattr(report, "content_json", None)
        if content_json is not None:
            body["content_json"] = content_json
        content_md = getattr(report, "content_markdown", None)
        if content_md is not None:
            body["content_markdown"] = content_md

        # Temporal markers ----------------------------------------------------
        report_date = getattr(report, "report_date", None)
        if report_date is not None:
            body["report_date"] = _iso(report_date)
        created_at = getattr(report, "created_at", None)
        if created_at is not None:
            body["created_at"] = _iso(created_at)

        return json.dumps(
            body,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    @staticmethod
    def canonical_payload_hash(report: Any) -> str:
        """Hex sha256 of the canonical payload — useful for clients."""
        return hashlib.sha256(
            ReportSigner.canonical_payload(report)
        ).hexdigest()

    # ------------------------------------------------------------------
    # Sign / verify
    # ------------------------------------------------------------------

    def sign(self, report: Any) -> str:
        """Return a base64-encoded blob: ``signature | fingerprint``.

        The format is ``base64( raw_signature_64_bytes || b'|' ||
        utf8_fingerprint )``. The pipe-separator keeps parsing simple
        on the verifier side without forcing a TLV scheme.
        """
        if self._unavailable or self._private_key is None:
            raise SigningUnavailableError(
                "signing service is unavailable: no key loaded"
            )
        payload = self.canonical_payload(report)
        signature = self._private_key.sign(payload)
        fp = self.fingerprint
        blob = signature + b"|" + fp.encode("ascii")
        return base64.b64encode(blob).decode("ascii")

    def verify(self, report: Any, signature_str: str) -> bool:
        """Verify a previously produced signature against the report.

        Returns ``True`` on a valid signature, ``False`` otherwise.
        Never raises on bad input — this method is also called by the
        public verification endpoint where a malformed input must
        translate to ``valid=False`` rather than HTTP 500.
        """
        if self._public_key is None:
            return False
        try:
            sig_blob = base64.b64decode(signature_str.encode("ascii"))
        except Exception:  # noqa: BLE001
            return False
        # raw signature is always 64 bytes for Ed25519.
        if len(sig_blob) < 64 + 1 + 16:
            return False
        signature = sig_blob[:64]
        sep = sig_blob[64:65]
        if sep != b"|":
            return False
        # fingerprint trailer is ignored for the cryptographic check
        # itself — the active public key is the source of truth.
        payload = self.canonical_payload(report)
        try:
            self._public_key.verify(signature, payload)
            return True
        except InvalidSignature:
            return False
        except Exception:  # noqa: BLE001
            return False

    def verify_payload(self, canonical_payload: bytes, signature_str: str) -> bool:
        """Verify a signature against caller-supplied canonical bytes.

        Used by the public verification endpoint when the client has
        already canonicalized the report locally.
        """
        if self._public_key is None:
            return False
        try:
            sig_blob = base64.b64decode(signature_str.encode("ascii"))
        except Exception:  # noqa: BLE001
            return False
        if len(sig_blob) < 64 + 1:
            return False
        signature = sig_blob[:64]
        if sig_blob[64:65] != b"|":
            return False
        try:
            self._public_key.verify(signature, canonical_payload)
            return True
        except InvalidSignature:
            return False
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------
    # Rotation
    # ------------------------------------------------------------------

    def rotate(
        self,
        archive_dir: Path | None = None,
    ) -> Tuple[str, str | None, str]:
        """Generate a new keypair and replace the active one.

        Reports already signed retain their signature; the old public
        key is archived under ``archive_dir`` (default:
        ``<priv_dir>/archive``) so historical reports remain
        verifiable by clients that fetch archived keys explicitly.

        Returns ``(new_fingerprint, archived_old_fingerprint or None,
        public_key_pem)``.
        """
        archived_fp: Optional[str] = None
        if self._public_key is not None and self._public_key_path is not None:
            archived_fp = self.fingerprint
            target_dir = (
                archive_dir
                if archive_dir is not None
                else self._public_key_path.parent / "archive"
            )
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                archive_path = target_dir / f"{archived_fp}.pem"
                archive_path.write_bytes(
                    self._public_key.public_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PublicFormat.SubjectPublicKeyInfo,
                    )
                )
                # Tight perms — best-effort on POSIX, no-op on Windows.
                try:
                    archive_path.chmod(0o600)
                except Exception:  # noqa: BLE001
                    pass
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "ReportSigner.rotate: failed to archive old public "
                    "key (%s). Continuing rotation.",
                    exc.__class__.__name__,
                )

        new_priv = Ed25519PrivateKey.generate()
        new_pub = new_priv.public_key()

        # Persist if we have on-disk paths configured.
        if self._private_key_path is not None and self._public_key_path is not None:
            try:
                self._private_key_path.parent.mkdir(
                    parents=True, exist_ok=True
                )
                self._public_key_path.parent.mkdir(
                    parents=True, exist_ok=True
                )
                self._private_key_path.write_bytes(
                    new_priv.private_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PrivateFormat.PKCS8,
                        encryption_algorithm=serialization.NoEncryption(),
                    )
                )
                self._public_key_path.write_bytes(
                    new_pub.public_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PublicFormat.SubjectPublicKeyInfo,
                    )
                )
                try:
                    self._private_key_path.chmod(0o600)
                except Exception:  # noqa: BLE001
                    pass
                self._ephemeral = False
            except Exception as exc:  # noqa: BLE001
                # If persistence fails we still rotate in-memory so the
                # caller does not end up half-rotated, but warn loudly.
                logger.error(
                    "ReportSigner.rotate: failed to persist new keypair "
                    "(%s). New key is in-memory only.",
                    exc.__class__.__name__,
                )
                self._ephemeral = True

        self._private_key = new_priv
        self._public_key = new_pub
        self._unavailable = False

        return self.fingerprint, archived_fp, self.public_key_pem

    # ------------------------------------------------------------------
    # Key generation helper (CLI / admin)
    # ------------------------------------------------------------------

    @classmethod
    def generate_keypair(cls, out_dir: Path) -> tuple[Path, Path]:
        """Write a fresh Ed25519 keypair under ``out_dir``.

        Returns (private_path, public_path). Files are written with
        0600 perms on POSIX. Intended as a one-shot bootstrap helper —
        operators typically prefer ``openssl genpkey -algorithm
        Ed25519`` (documented in ``.env.example``).
        """
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        priv_path = out_dir / "ed25519_private.pem"
        pub_path = out_dir / "ed25519_public.pem"

        priv = Ed25519PrivateKey.generate()
        priv_path.write_bytes(
            priv.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        pub_path.write_bytes(
            priv.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        try:
            priv_path.chmod(0o600)
        except Exception:  # noqa: BLE001
            pass
        return priv_path, pub_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iso(value: Any) -> str:
    """Render datetimes as ISO 8601, leave strings untouched."""
    if isinstance(value, datetime):
        # Use isoformat() without timezone normalization so the
        # signature matches what the verifier sees in the JSON view.
        return value.isoformat()
    return str(value)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

report_signer = ReportSigner(
    private_key_path=getattr(settings, "SIGNING_PRIVATE_KEY_PATH", None) or None,
    public_key_path=getattr(settings, "SIGNING_PUBLIC_KEY_PATH", None) or None,
)


__all__ = [
    "ReportSigner",
    "SigningError",
    "SigningUnavailableError",
    "report_signer",
]
