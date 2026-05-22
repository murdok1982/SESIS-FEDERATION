# -*- coding: utf-8 -*-
import redis.asyncio as redis
from app.core.config import settings

_pool = None


async def get_redis_pool():
    global _pool
    if _pool is None:
        _pool = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _pool
