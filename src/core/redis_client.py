import redis.asyncio as redis
from typing import Any, Optional, Dict
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
    """Read the user_id mapped to a meeting.

    The backend writes this key via its JSON cache encoder (see
    ``app/config/redis_config.py``), so the value is a JSON-encoded
    string like ``b'"<uuid>"'``. We decode JSON first; if that fails we
    treat the value as a plain UTF-8 string (covers any legacy
    plain-text entries). The old ``pickle.loads`` path was removed —
    deserializing pickle from a shared Redis is a CVE-class risk and
    was also the root cause of the JSON quotes leaking through into
    outbound routing keys.
    """
    r = await get_redis()
    key = _key_meeting_to_user(meeting_id)
    raw = await r.get(key)
    logger.info(f"[Redis] GET {key} -> raw={raw}")
    if raw is None:
        return None

    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
    try:
        decoded = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        # Pre-JSON-encoder entries (or anything written outside the
        # backend's cache helper) — return the raw string.
        logger.info(f"[Redis] Non-JSON value at {key}, using raw string")
        return text

    if isinstance(decoded, str):
        return decoded
    # Backend's tagged-object encoder wraps non-primitive values as
    # ``{"__t": ..., "__v": ...}``. For UUIDs that's ``{"__t": "uuid",
    # "__v": "<uuid>"}``; if anyone ever writes a UUID instead of a
    # string here, pull the value out so we still get a flat user_id.
    if isinstance(decoded, dict):
        value = decoded.get("__v")
        if isinstance(value, str):
            return value
    logger.warning(f"[Redis] Unexpected JSON shape at {key}: {decoded!r}")
    return None

async def set_user_id_by_meeting(meeting_id: str, user_id: str, ttl: int = 86400) -> bool:
    """Write the user_id mapping in the same JSON shape the backend uses.

    The backend is the primary writer of this key; this helper exists for
    completeness so a value round-trips through ``get_user_id_by_meeting``
    regardless of which service wrote it.
    """
    r = await get_redis()
    key = _key_meeting_to_user(meeting_id)
    await r.setex(key, ttl, json.dumps(user_id).encode("utf-8"))
    logger.info(f"[Redis] SET {key} = {user_id} (TTL {ttl}s)")
    return True

async def delete_user_id_by_meeting(meeting_id: str) -> None:
    r = await get_redis()
    key = _key_meeting_to_user(meeting_id)
    await r.delete(key)
    logger.info(f"[Redis] DEL {key}")

# ==================== Connection Registry ====================

async def register_active_connection(
    user_id: str,
    platform: str,
    meeting_id: str = None,
    metadata: Dict[str, Any] | None = None,
) -> None:
    """Register active platform connection in Redis"""
    r = await get_redis()
    key = _key_active_connections(platform)

    connection_data = {
        "meeting_id": meeting_id or "unknown",
        "timestamp": str(int(time.time()))
    }

    if metadata:
        connection_data.update(metadata)

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
        for p in ["youtube", "twitch", "facebook"]:
            key = _key_active_connections(p)
            await r.delete(key)
        logger.info(f"[Redis] Cleared all platform connections")