import httpx
import logging
from typing import Optional, Dict, Any
from src.core.config import get_settings

logger = logging.getLogger("TwitchProfileService")
settings = get_settings()


async def fetch_twitch_user_profile(access_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch Twitch user profile using the Helix API
    
    Args:
        access_token: The user's Twitch access token
        
    Returns:
        Dictionary containing user profile data including:
        - id: Twitch user ID
        - login: Username (lowercase, used for IRC nickname and channel)
        - display_name: Display name
        - profile_image_url: Profile image URL
        - etc.
    """
    url = "https://api.twitch.tv/helix/users"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Client-ID": settings.TWITCH_CLIENT_ID,
    }
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            if data.get("data") and len(data["data"]) > 0:
                user_data = data["data"][0]
                logger.info(f"[TwitchProfile] Fetched profile for user: {user_data.get('login')}")
                return user_data
            else:
                logger.warning("[TwitchProfile] No user data returned from Twitch API")
                return None
                
    except httpx.HTTPStatusError as e:
        logger.error(f"[TwitchProfile] HTTP error fetching profile: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"[TwitchProfile] Failed to fetch Twitch profile: {e}")
        return None


async def get_twitch_channel_info(user_id: str, access_token: str) -> Optional[Dict[str, str]]:
    """
    Get Twitch channel information for IRC connection
    
    Args:
        user_id: The application user ID (for logging)
        access_token: The user's Twitch access token
        
    Returns:
        Dictionary with 'nickname' and 'channel' for IRC connection
    """
    profile = await fetch_twitch_user_profile(access_token)
    
    if not profile:
        logger.error(f"[TwitchProfile] Could not fetch profile for user {user_id}")
        return None
    
    login = profile.get("login")
    if not login:
        logger.error(f"[TwitchProfile] No login found in profile for user {user_id}")
        return None
    
    return {
        "nickname": login,
        "channel": f"#{login}",
        "display_name": profile.get("display_name", login),
        "twitch_id": profile.get("id"),
    }
