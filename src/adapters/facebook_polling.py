import asyncio
from typing import Any, Dict, List, Optional

import httpx

from src.api.messages import receive_incoming_message
from src.core.logger import get_logger
from src.core.token_fetcher import fetch_facebook_stream_token
from src.schemas.chat import IncomingMessage

logger = get_logger("FacebookAdapter")

GRAPH_BASE_URL = "https://graph.facebook.com/v25.0"


class FacebookChatClient:
    def __init__(
        self,
        user_id: str,
        meeting_id: str,
        live_stream_id: str,
        live_video_id: Optional[str] = None,
        target: str = "me",
    ):
        self.user_id = user_id
        self.meeting_id = meeting_id
        self.live_stream_id = live_stream_id
        self.live_video_id = live_video_id or live_stream_id
        self.target = target

        self.access_token: Optional[str] = None
        self.video_id: Optional[str] = None
        self._resolved_video_id: Optional[str] = None
        self.after_cursor: Optional[str] = None
        self.polling_interval = 5
        self.is_connected = False
        self._stop_polling = False
        self._http_client: Optional[httpx.AsyncClient] = None
        self._processed_message_ids: set[str] = set()
        self._outbound_comment_ids: set[str] = set()

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def _load_token(self) -> None:
        token_data = await fetch_facebook_stream_token(self.meeting_id, self.target)
        if not token_data or not token_data.get("access_token"):
            raise Exception("No Facebook access token available")
        self.access_token = token_data["access_token"]

    async def _make_graph_get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.access_token:
            await self._load_token()

        request_params = {**params, "access_token": self.access_token}
        client = await self._get_http_client()

        response = await client.get(f"{GRAPH_BASE_URL}/{path}", params=request_params)
        if response.status_code == 401:
            await self._load_token()
            request_params["access_token"] = self.access_token
            response = await client.get(f"{GRAPH_BASE_URL}/{path}", params=request_params)

        response.raise_for_status()
        return response.json()

    async def _make_graph_post(self, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.access_token:
            await self._load_token()

        body = {**data, "access_token": self.access_token}
        client = await self._get_http_client()

        response = await client.post(f"{GRAPH_BASE_URL}/{path}", data=body)
        if response.status_code == 401:
            await self._load_token()
            body["access_token"] = self.access_token
            response = await client.post(f"{GRAPH_BASE_URL}/{path}", data=body)

        response.raise_for_status()
        return response.json()

    async def fetch_comments(self) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "fields": "created_time,from,message,id",
        }
        if self.after_cursor:
            params["after"] = self.after_cursor

        try:
            try:
                data = await self._make_graph_get(f"{self.live_stream_id}/comment", params)
            except Exception:
                data = await self._make_graph_get(f"{self.live_stream_id}/comments", params)
            paging = data.get("paging", {})
            cursors = paging.get("cursors", {})
            self.after_cursor = cursors.get("after")
            return data.get("data", [])
        except Exception as e:
            logger.error(f"[FacebookAdapter] Fetch comments failed: {e}")
            return []

    async def _resolve_video_id(self) -> str:
        if self._resolved_video_id:
            return self._resolved_video_id

        data = await self._make_graph_get(
            f"{self.live_video_id}",
            {"fields": "video"},
        )
        video = data.get("video") or {}
        resolved_video_id = video.get("id")
        if not resolved_video_id:
            raise Exception("Could not resolve video.id from live_video_id")
        self.video_id = resolved_video_id
        self._resolved_video_id = resolved_video_id
        return resolved_video_id

    async def send_message(self, text: str) -> None:
        video_id = await self._resolve_video_id()
        result = await self._make_graph_post(
            f"{video_id}/comments",
            {"message": text},
        )

        created_comment_id = result.get("id")
        if created_comment_id:
            self._outbound_comment_ids.add(created_comment_id)

        logger.info(f"[FacebookAdapter] → Sent: {text}")

    async def connect(self) -> None:
        await self._load_token()
        self.is_connected = True
        self._stop_polling = False
        logger.info(
            f"[FacebookAdapter] Starting polling for user={self.user_id}, meeting={self.meeting_id}, stream={self.live_stream_id}"
        )
        await self._poll_messages()

    async def disconnect(self) -> None:
        self._stop_polling = True
        self.is_connected = False
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
        logger.info(f"[FacebookAdapter] Disconnected user {self.user_id}")

    async def _poll_messages(self) -> None:
        consecutive_errors = 0
        while not self._stop_polling:
            try:
                comments = await self.fetch_comments()
                for comment in comments:
                    comment_id = comment.get("id")

                    if comment_id and comment_id in self._outbound_comment_ids:
                        self._processed_message_ids.add(comment_id)
                        self._outbound_comment_ids.discard(comment_id)
                        continue

                    if comment_id and comment_id in self._processed_message_ids:
                        continue

                    from_info = comment.get("from") or {}
                    sender_name = from_info.get("name") or "facebook user"
                    sender_id = from_info.get("id")
                    message_text = comment.get("message") or ""

                    if not message_text:
                        continue

                    inbound = IncomingMessage(
                        platform="facebook",
                        user_id=sender_id,
                        user_name=sender_name,
                        content=message_text,
                        message_id=comment_id,
                    )
                    await receive_incoming_message(inbound)

                    if comment_id:
                        self._processed_message_ids.add(comment_id)

                consecutive_errors = 0
                await asyncio.sleep(self.polling_interval)
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"[FacebookAdapter] Polling error ({consecutive_errors}): {e}")
                if consecutive_errors >= 5:
                    logger.error("[FacebookAdapter] Too many consecutive errors, disconnecting")
                    self.is_connected = False
                    self._stop_polling = True
                    break
                await asyncio.sleep(min(5 * consecutive_errors, 30))