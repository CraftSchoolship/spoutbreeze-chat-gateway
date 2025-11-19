import redis.asyncio as redis
from typing import Optional
import logging
from src.core.config import get_settings

logger = logging.getLogger("ChatGateway")
_settings = get_settings()
_redis: Optional[redis.Redis] = None

def _key_meeting_to_user(meeting_id: str) -> str:
    return f"chat:meeting:{meeting_id}:user_id"

async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(
            _settings.REDIS_URL, 
            decode_responses=False  # Change to False to match backend pickle format
        )
    return _redis

async def get_user_id_by_meeting(meeting_id: str) -> Optional[str]:
    import pickle
    r = await get_redis()
    key = _key_meeting_to_user(meeting_id)
    raw = await r.get(key)
    logger.info(f"[Redis] GET {key} -> raw={raw}")
    if raw is None:
        return None
    try:
        # Backend stores with pickle, so unpickle it
        user_id = pickle.loads(raw)
        logger.info(f"[Redis] Unpickled user_id={user_id}")
        return str(user_id)
    except Exception as e:
        logger.error(f"[Redis] Failed to unpickle: {e}")
        # Fallback: try decode as string
        return raw.decode('utf-8') if isinstance(raw, bytes) else str(raw)

async def set_user_id_by_meeting(meeting_id: str, user_id: str, ttl: int = 86400) -> bool:
    import pickle
    r = await get_redis()
    key = _key_meeting_to_user(meeting_id)
    await r.setex(key, ttl, pickle.dumps(user_id))
    logger.info(f"[Redis] SET {key} = {user_id} (TTL {ttl}s)")
    return True

async def delete_user_id_by_meeting(meeting_id: str) -> None:
    r = await get_redis()
    key = _key_meeting_to_user(meeting_id)
    await r.delete(key)
    logger.info(f"[Redis] DEL {key}")