"""
Rate Limiting Middleware - Sliding Window con Redis.
Protege contra DDoS y abuso de API en sistemas militares.
"""
import time
import hashlib
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from redis import Redis
from typing import Optional, Dict, Any, Callable
import logging

logger = logging.getLogger("sesis.security.ratelimit")


class SlidingWindowRateLimiter:
    """
    Rate limiter usando algoritmo Sliding Window con Redis.
    Más preciso que Fixed Window, evita burst al cambio de ventana.
    """

    def __init__(self, redis_client: Redis, prefix: str = "ratelimit:"):
        self.redis = redis_client
        self.prefix = prefix

    def is_allowed(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> tuple[bool, Dict[str, Any]]:
        """
        Verifica si la clave puede hacer request.
        Retorna: (allowed, info_dict)
        """
        now = time.time()
        window_start = now - window_seconds
        redis_key = f"{self.prefix}{key}"

        # Sliding window usando sorted set en Redis
        # Eliminar requests fuera de la ventana
        self.redis.zremrangebyscore(redis_key, "-inf", window_start)

        # Contar requests en ventana actual
        current_count = self.redis.zcard(redis_key)

        if current_count >= max_requests:
            # Obtener tiempo hasta que expire el request más antiguo
            oldest = self.redis.zrange(redis_key, 0, 0, withscores=True)
            retry_after = int(oldest[0][1] - window_start) if oldest else window_seconds
            return False, {
                "allowed": False,
                "limit": max_requests,
                "remaining": 0,
                "retry_after": retry_after
            }

        # Agregar nuevo request con timestamp como score
        self.redis.zadd(redis_key, {f"{now}:{self._unique_id()}": now})
        # Expirar key después de window_seconds (cleanup)
        self.redis.expire(redis_key, window_seconds)

        return True, {
            "allowed": True,
            "limit": max_requests,
            "remaining": max_requests - current_count - 1,
            "retry_after": 0
        }

    def _unique_id(self) -> str:
        """Genera ID único para evitar colisiones en timestamp."""
        import uuid
        return str(uuid.uuid4())[:8]


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware FastAPI para rate limiting por IP o API Key.
    Configuración por endpoint y nivel de clasificación.
    """

    # Límites por defecto (requests, seconds)
    DEFAULT_LIMITS = {
        "default": (100, 60),      # 100 req/min
        "brain": (20, 60),         # 20 req/min para LLM
        "ingest": (500, 60),       # 500 req/min para ingesta
        "classified": (50, 60),    # 50 req/min para SECRET+
    }

    def __init__(self, app, redis_client: Redis):
        super().__init__(app)
        self.limiter = SlidingWindowRateLimiter(redis_client)
        self.redis = redis_client

    async def dispatch(self, request: Request, call_next: Callable):
        # Determinar clave para rate limiting
        client_ip = request.client.host if request.client else "unknown"
        api_key = request.headers.get("X-API-Key", "")
        key_parts = [client_ip]
        if api_key:
            # Hash del API key para privacidad
            key_parts.append(hashlib.sha256(api_key.encode()).hexdigest()[:16])

        # Determinar límite según endpoint
        path = request.url.path
        limit_key = "default"
        if "/brain/" in path:
            limit_key = "brain"
        elif "/ingest" in path:
            limit_key = "ingest"

        max_req, window = self.DEFAULT_LIMITS.get(
            limit_key, self.DEFAULT_LIMITS["default"]
        )

        # Verificar clasificación (si está disponible)
        clearance = getattr(request.state, "clearance", "OPEN")
        if clearance in ["SECRET", "TOP_SECRET"]:
            max_req = self.DEFAULT_LIMITS["classified"][0]

        key = f"{limit_key}:{':'.join(key_parts)}"
        allowed, info = self.limiter.is_allowed(key, max_req, window)

        if not allowed:
            logger.warning(f"Rate limit excedido: {client_ip} en {path}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit excedido. Reintente en {info['retry_after']}s",
                headers={"Retry-After": str(info["retry_after"])}
            )

        response = await call_next(request)
        # Agregar headers informativos
        response.headers["X-RateLimit-Limit"] = str(info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
        return response
