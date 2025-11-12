from typing import Dict, Optional
import asyncio
from src.adapters.youtube_polling import YouTubeChatClient
from src.core.logger import get_logger

logger = get_logger("YouTubeService")


class YouTubeService:
    def __init__(self):
        self._connections: Dict[str, YouTubeChatClient] = {}

    def get_connection_for_user(self, user_id: str) -> Optional[YouTubeChatClient]:
        return self._connections.get(user_id)

    async def start_connection_for_user(self, user_id: str) -> None:
        existing = self._connections.get(user_id)
        if existing and existing.is_connected:
            logger.info(f"[YouTubeService] User {user_id} already connected")
            return

        client = YouTubeChatClient(user_id=user_id)
        self._connections[user_id] = client
        asyncio.create_task(client.connect())
        logger.info(f"[YouTubeService] Starting connection for user {user_id}")

    async def start_with_chat_id(self, user_id: str, live_chat_id: str) -> None:
        client = self._connections.get(user_id)
        if not client:
            client = YouTubeChatClient(user_id=user_id)
            self._connections[user_id] = client
        asyncio.create_task(client.connect_with_known_chat_id(live_chat_id))
        logger.info(f"[YouTubeService] Starting forced connection with chat ID: {live_chat_id}")

    async def stop_connection_for_user(self, user_id: str) -> None:
        client = self._connections.get(user_id)
        if client:
            await client.disconnect()
            self._connections.pop(user_id, None)
            logger.info(f"[YouTubeService] Stopped connection for user {user_id}")


youtube_service = YouTubeService()