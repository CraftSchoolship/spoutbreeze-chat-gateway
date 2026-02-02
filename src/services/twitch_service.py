from typing import Dict, Optional
import asyncio
from src.adapters.twitch_irc import TwitchIRCClient
from src.core.logger import get_logger
from src.core.redis_client import (
    register_active_connection,
    remove_active_connection,
    get_active_connections
)
from src.core.token_fetcher import fetch_twitch_token

logger = get_logger("TwitchService")


class TwitchService:
    def __init__(self):
        self._connections: Dict[str, TwitchIRCClient] = {}

    def get_connection_for_user(self, user_id: str) -> Optional[TwitchIRCClient]:
        return self._connections.get(user_id)

    async def start_connection_for_user(self, user_id: str, access_token: str, meeting_id: str = None) -> None:
        existing = self._connections.get(user_id)
        if existing and existing.is_connected:
            logger.info(f"[TwitchService] User {user_id} already connected")
            return

        client = TwitchIRCClient(user_id=user_id, access_token=access_token)
        self._connections[user_id] = client
        
        # Persist to Redis
        await register_active_connection(user_id, "twitch", meeting_id)
        
        asyncio.create_task(client.connect())
        logger.info(f"[TwitchService] Starting connection for user {user_id}")

    async def stop_connection_for_user(self, user_id: str) -> None:
        client = self._connections.get(user_id)
        if client:
            await client.disconnect()
            self._connections.pop(user_id, None)
            
            # Remove from Redis
            await remove_active_connection(user_id, "twitch")
            logger.info(f"[TwitchService] Stopped connection for user {user_id}")

    async def restore_connections(self) -> None:
        """Restore all Twitch connections from Redis on startup"""
        logger.info("[TwitchService] Restoring connections from Redis...")
        
        try:
            connections = await get_active_connections("twitch")
            
            if not connections:
                logger.info("[TwitchService] No connections to restore")
                return
            
            logger.info(f"[TwitchService] Found {len(connections)} connection(s) to restore")
            
            for user_id, data in connections.items():
                try:
                    meeting_id = data.get("meeting_id", "unknown")
                    logger.info(f"[TwitchService] Restoring connection for user {user_id} (meeting: {meeting_id})")
                    
                    # Fetch fresh token
                    token_data = await fetch_twitch_token(user_id)
                    if token_data and token_data.get("access_token"):
                        await self.start_connection_for_user(user_id, token_data["access_token"], meeting_id)
                    else:
                        logger.error(f"[TwitchService] No valid token for user {user_id}, skipping restore")
                        await remove_active_connection(user_id, "twitch")
                        
                except Exception as e:
                    logger.error(f"[TwitchService] Failed to restore connection for {user_id}: {e}")
        
        except Exception as e:
            logger.error(f"[TwitchService] Failed to restore connections: {e}")


twitch_service = TwitchService()