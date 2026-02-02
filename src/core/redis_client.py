import redis.asyncio as redis
from typing import Optional, Dict
import logging
import json
import time  # Add this import
from src.core.config import get_settings

logger = logging.getLogger("ChatGateway")
_settings = get_settings()
_redis: Optional[redis.Redis] = None

def _key_meeting_to_user(meeting_id: str) -> str:
    return f"chat:meeting:{meeting_id}:user_id"

def _key_active_connections(platform: str) -> str:
    """Key for storing active platform connections"""
    return f"chat:active_connections:{platform}"

async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(
            _settings.REDIS_URL, 
            decode_responses=False
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
        user_id = pickle.loads(raw)
        logger.info(f"[Redis] Unpickled user_id={user_id}")
        return str(user_id)
    except Exception as e:
        logger.error(f"[Redis] Failed to unpickle: {e}")
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

# ==================== Connection Registry ====================

async def register_active_connection(user_id: str, platform: str, meeting_id: str = None) -> None:
    """Register active platform connection in Redis"""
    r = await get_redis()
    key = _key_active_connections(platform)
    
    connection_data = {
        "meeting_id": meeting_id or "unknown",
        "timestamp": str(int(time.time()))  # FIXED: Use standard time.time()
    }
    
    await r.hset(key, user_id, json.dumps(connection_data))
    logger.info(f"[Redis] Registered {platform} connection for user {user_id}")

async def get_active_connections(platform: str) -> Dict[str, dict]:
    """Get all active connections for a platform"""
    r = await get_redis()
    key = _key_active_connections(platform)
    
    raw_data = await r.hgetall(key)
    if not raw_data:
        return {}
    
    connections = {}
    for user_id_bytes, data_bytes in raw_data.items():
        try:
            user_id = user_id_bytes.decode('utf-8')
            data = json.loads(data_bytes.decode('utf-8'))
            connections[user_id] = data
        except Exception as e:
            logger.error(f"[Redis] Failed to parse connection data: {e}")
    
    return connections

async def remove_active_connection(user_id: str, platform: str) -> None:
    """Remove active connection from Redis"""
    r = await get_redis()
    key = _key_active_connections(platform)
    await r.hdel(key, user_id)
    logger.info(f"[Redis] Removed {platform} connection for user {user_id}")

async def clear_all_connections(platform: str = None) -> None:
    """Clear all connections (for testing/cleanup)"""
    r = await get_redis()
    if platform:
        key = _key_active_connections(platform)
        await r.delete(key)
        logger.info(f"[Redis] Cleared all {platform} connections")
    else:
        for p in ["youtube", "twitch"]:
            key = _key_active_connections(p)
            await r.delete(key)
        logger.info(f"[Redis] Cleared all platform connections")