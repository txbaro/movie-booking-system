import hashlib
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from uuid import uuid4

from app.core.config import settings
from app.core.redis_client import redis_client
from app.services.discovery import VIETNAM_TIMEZONE


QUOTA_SCRIPT = """
local user_count = redis.call('INCR', KEYS[1])
if user_count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
if user_count > tonumber(ARGV[2]) then return {user_count, -1} end
local ip_count = redis.call('INCR', KEYS[2])
if ip_count == 1 then redis.call('EXPIRE', KEYS[2], ARGV[1]) end
return {user_count, ip_count}
"""

RELEASE_LOCK_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


@dataclass(frozen=True)
class QuotaResult:
    allowed: bool
    remaining: int
    reset_seconds: int


def _quota_window() -> tuple[str, int]:
    now = datetime.now(VIETNAM_TIMEZONE)
    tomorrow = now.date() + timedelta(days=1)
    reset_at = datetime.combine(tomorrow, time.min, tzinfo=VIETNAM_TIMEZONE)
    return now.date().isoformat(), max(1, int((reset_at - now).total_seconds()))


async def consume_ai_quota(user_id: int, client_ip: str) -> QuotaResult:
    """Atomically count daily semantic/LLM requests for both user and IP."""
    day, reset_seconds = _quota_window()
    ip_hash = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()[:24]
    user_key = f"ai_quota:user:{day}:{user_id}"
    ip_key = f"ai_quota:ip:{day}:{ip_hash}"
    user_count, ip_count = await redis_client.eval(
        QUOTA_SCRIPT,
        2,
        user_key,
        ip_key,
        reset_seconds,
        settings.AI_REQUESTS_PER_USER_PER_DAY,
    )
    user_remaining = settings.AI_REQUESTS_PER_USER_PER_DAY - int(user_count)
    ip_remaining = (
        settings.AI_REQUESTS_PER_IP_PER_DAY - int(ip_count)
        if int(ip_count) >= 0
        else 0
    )
    return QuotaResult(
        allowed=int(ip_count) >= 0 and user_remaining >= 0 and ip_remaining >= 0,
        remaining=max(0, min(user_remaining, ip_remaining)),
        reset_seconds=reset_seconds,
    )


@asynccontextmanager
async def distributed_lock(name: str, ttl_seconds: int | None = None):
    """Yield True only to the process that owns this short-lived Redis lock."""
    token = uuid4().hex
    key = f"distributed_lock:{name}"
    acquired = bool(
        await redis_client.set(
            key,
            token,
            nx=True,
            ex=ttl_seconds or settings.COLLECTOR_LOCK_TTL_SECONDS,
        )
    )
    try:
        yield acquired
    finally:
        if acquired:
            await redis_client.eval(RELEASE_LOCK_SCRIPT, 1, key, token)
