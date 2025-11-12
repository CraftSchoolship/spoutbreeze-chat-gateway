from typing import Dict, Optional
import asyncio
from src.adapters.twitch_irc import TwitchIRCClient
from src.core.logger import get_logger

logger = get_logger("TwitchService")


class TwitchService:
    def __init__(self):
        self._connections: Dict[str, TwitchIRCClient] = {}

    def get_connection_for_user(self, user_id: str) -> Optional[TwitchIRCClient]:
        return self._connections.get(user_id)

    async def start_connection_for_user(self, user_id: str) -> None:
        existing = self._connections.get(user_id)
        if existing and existing.is_connected:
            logger.info(f"[TwitchService] User {user_id} already connected")
            return

        client = TwitchIRCClient(user_id=user_id)
        self._connections[user_id] = client
        asyncio.create_task(client.connect())
        logger.info(f"[TwitchService] Starting connection for user {user_id}")

    async def stop_connection_for_user(self, user_id: str) -> None:
        client = self._connections.get(user_id)
        if client:
            await client.disconnect()
            self._connections.pop(user_id, None)
            logger.info(f"[TwitchService] Stopped connection for user {user_id}")


twitch_service = TwitchService()