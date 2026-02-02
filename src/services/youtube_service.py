from typing import Dict, Optional
import asyncio
from src.adapters.youtube_polling import YouTubeChatClient
from src.core.logger import get_logger
from src.core.redis_client import (
    register_active_connection,
    remove_active_connection,
    get_active_connections
)

logger = get_logger("YouTubeService")


class YouTubeService:
    def __init__(self):
        self._connections: Dict[str, YouTubeChatClient] = {}

    def get_connection_for_user(self, user_id: str) -> Optional[YouTubeChatClient]:
        return self._connections.get(user_id)

    async def start_connection_for_user(self, user_id: str, meeting_id: str = None) -> None:
        existing = self._connections.get(user_id)
        if existing and existing.is_connected:
            logger.info(f"[YouTubeService] User {user_id} already connected")
            return

        client = YouTubeChatClient(user_id=user_id)
        self._connections[user_id] = client
        
        # Persist to Redis
        await register_active_connection(user_id, "youtube", meeting_id)
        
        asyncio.create_task(client.connect())
        logger.info(f"[YouTubeService] Starting connection for user {user_id}")

    async def start_with_chat_id(self, user_id: str, live_chat_id: str, meeting_id: str = None) -> None:
        client = self._connections.get(user_id)
        if not client:
            client = YouTubeChatClient(user_id=user_id)
            self._connections[user_id] = client
        
        # Persist to Redis
        await register_active_connection(user_id, "youtube", meeting_id)
        
        asyncio.create_task(client.connect_with_known_chat_id(live_chat_id))
        logger.info(f"[YouTubeService] Starting forced connection with chat ID: {live_chat_id}")

    async def stop_connection_for_user(self, user_id: str) -> None:
        client = self._connections.get(user_id)
        if client:
            await client.disconnect()
            self._connections.pop(user_id, None)
            
            # Remove from Redis
            await remove_active_connection(user_id, "youtube")
            logger.info(f"[YouTubeService] Stopped connection for user {user_id}")

    async def restore_connections(self) -> None:
        """Restore all YouTube connections from Redis on startup"""
        logger.info("[YouTubeService] Restoring connections from Redis...")
        
        try:
            connections = await get_active_connections("youtube")
            
            if not connections:
                logger.info("[YouTubeService] No connections to restore")
                return
            
            logger.info(f"[YouTubeService] Found {len(connections)} connection(s) to restore")
            
            for user_id, data in connections.items():
                try:
                    meeting_id = data.get("meeting_id", "unknown")
                    logger.info(f"[YouTubeService] Restoring connection for user {user_id} (meeting: {meeting_id})")
                    await self.start_connection_for_user(user_id, meeting_id)
                except Exception as e:
                    logger.error(f"[YouTubeService] Failed to restore connection for {user_id}: {e}")
        
        except Exception as e:
            logger.error(f"[YouTubeService] Failed to restore connections: {e}")


youtube_service = YouTubeService()