import httpx
import logging
from typing import Optional, Dict, Any
from src.core.config import get_settings

logger = logging.getLogger("ChatGateway")
_settings = get_settings()

async def fetch_twitch_token(user_id: str) -> Optional[Dict[str, Any]]:
    """Fetch Twitch token from backend database via internal API"""
    url = f"{_settings.BACKEND_URL}/api/internal/twitch-token/{user_id}"
    headers = {"X-Internal-Auth": _settings.CHAT_GATEWAY_SHARED_SECRET}
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 404:
                logger.warning(f"[TokenFetch] No Twitch token for user {user_id}")
                return None
            response.raise_for_status()
            data = response.json()
            logger.info(f"[TokenFetch] Successfully fetched Twitch token for user {user_id}")
            return data
    except Exception as e:
        logger.error(f"[TokenFetch] Failed to fetch Twitch token: {e}")
        return None

async def fetch_youtube_token(user_id: str) -> Optional[Dict[str, Any]]:
    """Fetch YouTube token from backend database via internal API"""
    url = f"{_settings.BACKEND_URL}/api/internal/youtube-token/{user_id}"
    headers = {"X-Internal-Auth": _settings.CHAT_GATEWAY_SHARED_SECRET}
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 404:
                logger.warning(f"[TokenFetch] No YouTube token for user {user_id}")
                return None
            response.raise_for_status()
            data = response.json()
            logger.info(f"[TokenFetch] Successfully fetched YouTube token for user {user_id}")
            return data
    except Exception as e:
        logger.error(f"[TokenFetch] Failed to fetch YouTube token: {e}")
        return None