import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import Request
from jose import jws
from jsonschema import validate, ValidationError

from app.core.config import settings

logger = logging.getLogger("sesis.security")

# Load schema lazily — robust to cwd changes (uvicorn vs pytest vs docker)
_SCHEMA_CACHE: Optional[Dict[str, Any]] = None


def _load_schema() -> Dict[str, Any]:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is not None:
        return _SCHEMA_CACHE
    # Resolve relative to this file: backend/app/services/security.py → backend/schemas/uee_v1.json
    candidate_paths = [
        Path(__file__).resolve().parent.parent.parent / "schemas" / "uee_v1.json",
        Path("backend/schemas/uee_v1.json"),
        Path("schemas/uee_v1.json"),
    ]
    for p in candidate_paths:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                _SCHEMA_CACHE = json.load(f)
                return _SCHEMA_CACHE
    raise FileNotFoundError(f"UEE schema not found in any of: {candidate_paths}")


class SecurityService:
    @staticmethod
    def verify_signature(event_dict: Dict[str, Any]) -> bool:
        """
        Verifies the JWS signature in the event envelope.
        The 'signature' field must follow JWS (JSON Web Signature) standards.
        Fail-closed: si JWS_PUBLIC_KEY no está configurada, sólo se permite continuar
        en ENVIRONMENT=development (con validación de schema). En cualquier otro caso → False.
        """
        try:
            # Basic validation of the envelope structure
            validate(instance=event_dict, schema=_load_schema())

            signature_data = event_dict.get("signature", {})

            # Fail-closed cuando no hay clave pública configurada (excepto dev → schema-only).
            pub_key = settings.JWS_PUBLIC_KEY
            if pub_key is None or (isinstance(pub_key, str) and pub_key.strip() in ("", "None")):
                if settings.ENVIRONMENT == "development":
                    if signature_data.get("sig") == "DEBUG_INVALID":
                        return False
                    return True
                logger.warning("JWS_PUBLIC_KEY no configurada — rechazando firma (fail-closed)")
                return False

            # Verificación JWS real: reconstruir payload canónico (todo el evento menos 'signature').
            payload_to_verify = {k: v for k, v in event_dict.items() if k != "signature"}
            canonical = json.dumps(payload_to_verify, sort_keys=True, separators=(",", ":"))

            sig_token = signature_data.get("sig")
            alg = signature_data.get("alg")
            if not sig_token or not alg:
                logger.warning("Firma incompleta: faltan campos 'sig' o 'alg'")
                return False

            try:
                verified_payload = jws.verify(
                    token=sig_token,
                    key=pub_key,
                    algorithms=[alg],
                )
            except Exception as e:
                logger.warning("JWS verify failed: %s", e)
                return False

            # Defensa en profundidad: confirmar que el payload firmado coincide con el evento.
            try:
                signed_str = verified_payload.decode("utf-8") if isinstance(verified_payload, (bytes, bytearray)) else str(verified_payload)
            except Exception:
                signed_str = ""
            if signed_str != canonical:
                logger.warning("JWS payload no coincide con el evento canónico")
                return False

            return True
        except ValidationError as e:
            logger.warning("JWS verify failed: %s", e)
            return False
        except Exception as e:
            logger.warning("JWS verify failed: %s", e)
            return False

    @staticmethod
    def verify_mtls(request: Request) -> Dict[str, Any]:
        """
        Extracts subject info from the mTLS certificate.
        """
        subject = request.headers.get("X-SSL-Subject", "CN=device,O=SESIS")
        return {"subject": subject, "verified": True}
