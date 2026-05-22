# -*- coding: utf-8 -*-
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security_scheme = HTTPBearer(auto_error=False)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    token = credentials.credentials
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    return payload


class ABACEngine:
    """Attribute-Based Access Control — multi-level security enforcement."""

    LEVEL_HIERARCHY = {"public": 0, "restricted": 1, "confidential": 2, "secret": 3, "top_secret": 4}

    def __init__(self):
        self.policies = {}

    def register_policy(self, resource: str, required_level: str):
        self.policies[resource] = required_level

    def check_access(self, request: Request, resource: str) -> bool:
        principal = getattr(request.state, "principal", None)
        if principal is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required: JWT token missing or invalid",
            )
        user_level = principal.get("clearance", "public").lower()
        required = self.policies.get(resource, "public").lower()
        user_lvl = self.LEVEL_HIERARCHY.get(user_level, 0)
        req_lvl = self.LEVEL_HIERARCHY.get(required, 0)
        if user_lvl < req_lvl:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient clearance: need {required}, have {user_level}",
            )
        return True


abac = ABACEngine()

def require_clearance(min_level: str):
    """
    Devuelve una dependencia FastAPI que exige un nivel minimo de clearance.
    El JWT debe haberse decodificado previamente y haber poblado
    `request.state.principal` con el payload del token.
    """
    async def dep(request: Request) -> dict:
        principal = getattr(request.state, "principal", None)
        if principal is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required: JWT token missing, invalid, or expired",
            )
        subj = CLEARANCE_ORDER.get(principal.get("clearance", "OPEN"), 0)
        need = CLEARANCE_ORDER.get(min_level, 0)
        if subj < need:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"clearance < {min_level}",
            )
        return principal
    return dep


class JWTService:
    """Servicio JWT con refresh tokens y validación MFA."""

    def __init__(self, secret_key: str, algorithm: str = "HS256",
                 access_expire_min: int = 15, refresh_expire_days: int = 7):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_expire = timedelta(minutes=access_expire_min)
        self.refresh_expire = timedelta(days=refresh_expire_days)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_access_token(
        self,
        subject: str,
        roles: list[str] = None,
        clearance: str = "OPEN",
        mfa_verified: bool = False
    ) -> str:
        """Crea access token (max 15 min según directrices)."""
        expire = datetime.utcnow() + self.access_expire
        payload = {
            "sub": subject,
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access",
            "mfa": mfa_verified,
            "roles": roles or [],
            "clearance": clearance,
            "aud": "sesis-c2",
            "iss": "sesis-auth-server"
        }
        return jwt.encode(payload, self.secret_key, self.algorithm)

    def create_refresh_token(self, subject: str, redis_client: redis.Redis) -> str:
        """Crea refresh token (max 7 días) y lo almacena hasheado en Redis."""
        import uuid as _uuid
        expire = datetime.utcnow() + self.refresh_expire
        jti = _uuid.uuid4().hex
        payload = {
            "sub": subject,
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "refresh",
            "aud": "sesis-c2",
            "iss": "sesis-auth-server",
            "jti": jti,
        }
        token = jwt.encode(payload, self.secret_key, self.algorithm)
        # Almacenar SHA-256 del token (no el token íntegro) — CRITICAL HIGH.
        redis_key = f"refresh:{subject}"
        redis_client.setex(redis_key, self.refresh_expire, self._hash_token(token))
        return token

    def decode_token(self, token: str) -> TokenPayload:
        """Decodifica y valida un JWT token verificando claims estrictos."""
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                audience="sesis-c2",
                issuer="sesis-auth-server"
            )
            return TokenPayload(**payload)
        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token inválido: {str(e)}"
            )

    def verify_refresh_token(self, token: str, redis_client: redis.Redis) -> TokenPayload:
        """
        Verifica refresh token contra Redis (revocación) y rota: revoca el actual
        añadiendo su jti al blacklist con TTL = remaining lifetime.
        """
        payload = self.decode_token(token)
        if payload.type != "refresh":
            raise HTTPException(status_code=400, detail="No es un refresh token")

        # Comprobar blacklist (jti revocado).
        if payload.jti and redis_client.exists(f"revoked:{payload.jti}"):
            raise HTTPException(status_code=401, detail="Refresh token revocado")

        redis_key = f"refresh:{payload.sub}"
        stored = redis_client.get(redis_key)
        if not stored:
            raise HTTPException(status_code=401, detail="Refresh token revocado o inválido")
        stored_str = stored.decode() if isinstance(stored, (bytes, bytearray)) else stored
        if stored_str != self._hash_token(token):
            raise HTTPException(status_code=401, detail="Refresh token revocado o inválido")

        # Revocación rotativa: marcar jti del token consumido como revocado por el resto de su vida.
        if payload.jti:
            remaining = max(1, payload.exp - int(time.time()))
            redis_client.setex(f"revoked:{payload.jti}", remaining, "1")
        # Limpiar la entrada de refresh actual para forzar reemisión.
        redis_client.delete(redis_key)

        return payload

    def rotate_tokens(
        self,
        token: str,
        redis_client: redis.Redis,
        roles: Optional[list[str]] = None,
        clearance: str = "OPEN",
        mfa_verified: bool = False,
    ) -> Tuple[str, str]:
        """
        Verifica el refresh token, lo revoca y emite un nuevo par (access, refresh).
        """
        payload = self.verify_refresh_token(token, redis_client)
        new_access = self.create_access_token(
            subject=payload.sub,
            roles=roles or payload.roles,
            clearance=clearance or payload.clearance,
            mfa_verified=mfa_verified or payload.mfa,
        )
        new_refresh = self.create_refresh_token(payload.sub, redis_client)
        return new_access, new_refresh

    def revoke_refresh_token(self, subject: str, redis_client: redis.Redis) -> None:
        """Revoca refresh token (logout)."""
        redis_client.delete(f"refresh:{subject}")
