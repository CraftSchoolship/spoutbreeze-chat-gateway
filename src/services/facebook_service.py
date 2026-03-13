import asyncio
from typing import Dict, Optional

from src.adapters.facebook_polling import FacebookChatClient
from src.core.logger import get_logger
from src.core.redis_client import get_active_connections, register_active_connection, remove_active_connection

logger = get_logger("FacebookService")


class FacebookService:
    def __init__(self):
        self._connections: Dict[str, FacebookChatClient] = {}

    def get_connection_for_user(self, user_id: str) -> Optional[FacebookChatClient]:
        return self._connections.get(user_id)

    async def start_connection_for_user(
        self,
        user_id: str,
        meeting_id: str,
        live_stream_id: str,
        live_video_id: Optional[str] = None,
        target: str = "me",
    ) -> None:
        existing = self._connections.get(user_id)
        if existing and existing.is_connected:
            logger.info(f"[FacebookService] User {user_id} already connected")
            return

        client = FacebookChatClient(
            user_id=user_id,
            meeting_id=meeting_id,
            live_stream_id=live_stream_id,
            live_video_id=live_video_id,
            target=target,
        )
        self._connections[user_id] = client

        await register_active_connection(
            user_id,
            "facebook",
            meeting_id,
            metadata={
                "live_stream_id": live_stream_id,
                "live_video_id": live_video_id or live_stream_id,
                "target": target,
            },
        )

        asyncio.create_task(client.connect())
        logger.info(f"[FacebookService] Starting connection for user {user_id}")

    async def stop_connection_for_user(self, user_id: str) -> None:
        client = self._connections.get(user_id)
        if client:
            await client.disconnect()
            self._connections.pop(user_id, None)

        await remove_active_connection(user_id, "facebook")
        logger.info(f"[FacebookService] Stopped connection for user {user_id}")

    async def restore_connections(self) -> None:
        logger.info("[FacebookService] Restoring connections from Redis...")

        try:
            connections = await get_active_connections("facebook")
            if not connections:
                logger.info("[FacebookService] No connections to restore")
                return

            logger.info(f"[FacebookService] Found {len(connections)} connection(s) to restore")

            for user_id, data in connections.items():
                try:
                    meeting_id = data.get("meeting_id")
                    live_stream_id = data.get("live_stream_id")
                    live_video_id = data.get("live_video_id")
                    target = data.get("target", "me")

                    if not meeting_id or not live_stream_id:
                        logger.warning(
                            f"[FacebookService] Missing restore data for user {user_id} (meeting_id/live_stream_id); skipping"
                        )
                        continue

                    await self.start_connection_for_user(
                        user_id=user_id,
                        meeting_id=meeting_id,
                        live_stream_id=live_stream_id,
                        live_video_id=live_video_id,
                        target=target,
                    )
                except Exception as e:
                    logger.error(f"[FacebookService] Failed to restore connection for {user_id}: {e}")
        except Exception as e:
            logger.error(f"[FacebookService] Failed to restore connections: {e}")


facebook_service = FacebookService()