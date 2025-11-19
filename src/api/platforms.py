from fastapi import APIRouter, Header, HTTPException
import logging

from src.core.config import get_settings
from src.core.token_fetcher import fetch_twitch_token, fetch_youtube_token
from src.services.twitch_service import twitch_service
from src.services.youtube_service import youtube_service

router = APIRouter(tags=["Platforms"])
logger = logging.getLogger("ChatGateway")
settings = get_settings()

def _ensure_internal(x_internal_auth: str | None):
    if x_internal_auth != settings.CHAT_GATEWAY_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

@router.post("/platforms/register")
async def register_platform(
    platform: str,
    user_id: str,
    x_internal_auth: str = Header(None, alias="X-Internal-Auth"),
):
    _ensure_internal(x_internal_auth)
    logger.info(f"[Register] {platform} registered for user {user_id}")
    return {"status": "registered", "platform": platform, "user_id": user_id}

@router.post("/platforms/twitch/connect")
async def connect_twitch(user_id: str, x_internal_auth: str = Header(None, alias="X-Internal-Auth")):
    _ensure_internal(x_internal_auth)
    
    # Fetch token from backend
    token_data = await fetch_twitch_token(user_id)
    if not token_data:
        raise HTTPException(status_code=404, detail="No Twitch token found for user")
    
    # Start connection with token
    await twitch_service.start_connection_for_user(user_id, token_data["access_token"])
    logger.info(f"[Platforms] Twitch connected for user {user_id}")
    return {"status": "connecting", "platform": "twitch", "user_id": user_id}

@router.post("/platforms/twitch/disconnect")
async def disconnect_twitch(user_id: str, x_internal_auth: str = Header(None, alias="X-Internal-Auth")):
    _ensure_internal(x_internal_auth)
    await twitch_service.stop_connection_for_user(user_id)
    logger.info(f"[Platforms] Twitch disconnected for user {user_id}")
    return {"status": "disconnected", "platform": "twitch", "user_id": user_id}

@router.post("/platforms/youtube/connect")
async def connect_youtube(user_id: str, x_internal_auth: str = Header(None, alias="X-Internal-Auth")):
    _ensure_internal(x_internal_auth)
    
    # Fetch token from backend
    token_data = await fetch_youtube_token(user_id)
    if not token_data:
        raise HTTPException(status_code=404, detail="No YouTube token found for user")
    
    # Start connection with token
    await youtube_service.start_connection_for_user(user_id, token_data["access_token"])
    logger.info(f"[Platforms] YouTube connected for user {user_id}")
    return {"status": "connecting", "platform": "youtube", "user_id": user_id}

@router.post("/platforms/youtube/disconnect")
async def disconnect_youtube(user_id: str, x_internal_auth: str = Header(None, alias="X-Internal-Auth")):
    _ensure_internal(x_internal_auth)
    await youtube_service.stop_connection_for_user(user_id)
    logger.info(f"[Platforms] YouTube disconnected for user {user_id}")
    return {"status": "disconnected", "platform": "youtube", "user_id": user_id}

@router.post("/platforms/youtube/connect-with-chat-id")
async def connect_youtube_with_chat_id(
    user_id: str,
    live_chat_id: str,
    x_internal_auth: str = Header(None, alias="X-Internal-Auth")):
    _ensure_internal(x_internal_auth)
    
    # Fetch token from backend
    token_data = await fetch_youtube_token(user_id)
    if not token_data:
        raise HTTPException(status_code=404, detail="No YouTube token found for user")
    
    await youtube_service.start_with_chat_id(user_id, live_chat_id, token_data["access_token"])
    logger.info(f"[Platforms] YouTube connected with chat_id for user {user_id}")
    return {"status": "connecting", "platform": "youtube", "user_id": user_id, "chat_id": live_chat_id}