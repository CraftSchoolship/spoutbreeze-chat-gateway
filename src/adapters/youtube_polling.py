import asyncio
import httpx
from datetime import datetime, timedelta
from sqlalchemy import text
from typing import Optional, Dict, Any, List
import uuid
import hashlib

from src.core.config import get_settings
from src.core.logger import get_logger
from src.core.db_session import get_db

logger = get_logger("YouTubeAdapter")


class YouTubeChatClient:
    def __init__(self, user_id: str):
        self.settings = get_settings()
        self.user_id = user_id
        self.token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None
        self.live_chat_id: Optional[str] = None
        self.next_page_token: Optional[str] = None
        self.polling_interval = 5
        self.is_connected = False
        self._stop_polling = False
        self.authorized_channel_id: Optional[str] = None
        self.authorized_channel_title: Optional[str] = None
        self.last_error: Optional[str] = None
        self._http_client: Optional[httpx.AsyncClient] = None
        # Deduplication
        self._processed_message_ids: set = set()

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create persistent HTTP client"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def get_active_token(self) -> tuple[str, Optional[str], Optional[datetime]]:
        """Get token from shared DB using raw SQL"""
        try:
            user_uuid = str(uuid.UUID(self.user_id))

            async for db in get_db():
                query = text("""
                    SELECT access_token, refresh_token, expires_at 
                    FROM youtube_tokens 
                    WHERE user_id = :user_id 
                    AND is_active = true 
                    AND expires_at > NOW()
                    ORDER BY created_at DESC 
                    LIMIT 1
                """)
                
                result = await db.execute(query, {"user_id": user_uuid})
                row = result.first()
                
                if row:
                    logger.info(f"[YouTubeAdapter] Token loaded for user {self.user_id}")
                    return row[0], row[1], row[2]
                else:
                    logger.error(f"[YouTubeAdapter] No valid token for user {self.user_id}")
                    raise Exception("No valid token")
            
        except Exception as e:
            logger.error(f"[YouTubeAdapter] Token fetch error: {e}")
            raise

    async def refresh_token_if_needed(self) -> bool:
        """Check if token is expired/expiring and refresh if needed"""
        if not self.token_expires_at:
            return False

        # Refresh if token expires within next 5 minutes
        time_until_expiry = (self.token_expires_at - datetime.now()).total_seconds()

        if time_until_expiry > 300:  # More than 5 minutes left
            return False

        if not self.refresh_token:
            logger.warning(f"[YouTubeAdapter] Token expiring but no refresh token for user {self.user_id}")
            return False

        try:
            logger.info(f"[YouTubeAdapter] Refreshing token for user {self.user_id}")
            token_data = await self._refresh_access_token(self.refresh_token)
            
            if token_data:
                self.token = token_data.get("access_token")
                new_expires_in = token_data.get("expires_in", 3600)
                self.token_expires_at = datetime.now() + timedelta(seconds=new_expires_in)
                
                if token_data.get("refresh_token"):
                    self.refresh_token = token_data["refresh_token"]

                # Update database
                await self._save_refreshed_token(self.token, self.refresh_token, self.token_expires_at)
                logger.info(f"[YouTubeAdapter] Token refreshed for user {self.user_id}")
                return True
        except Exception as e:
            logger.error(f"[YouTubeAdapter] Token refresh failed: {e}")
            return False

    async def _refresh_access_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """Refresh token via Google OAuth"""
        try:
            client = await self._get_http_client()
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": self.settings.YOUTUBE_CLIENT_ID,
                    "client_secret": self.settings.YOUTUBE_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"[YouTubeAdapter] Token refresh failed: {e}")
            return None

    async def _save_refreshed_token(
        self,
        access_token: str,
        refresh_token: Optional[str],
        expires_at: datetime,
    ):
        """Save refreshed token back to database"""
        try:
            user_uuid = str(uuid.UUID(self.user_id))

            async for db in get_db():
                update_query = text("""
                    UPDATE youtube_tokens 
                    SET access_token = :access_token,
                        expires_at = :expires_at,
                        refresh_token = :refresh_token,
                        updated_at = NOW()
                    WHERE user_id = :user_id 
                    AND is_active = true
                """)
                
                await db.execute(update_query, {
                    "access_token": access_token,
                    "expires_at": expires_at,
                    "refresh_token": refresh_token,
                    "user_id": user_uuid
                })
                await db.commit()
                logger.debug(f"[YouTubeAdapter] Token updated in DB for user {self.user_id}")
                break
        except Exception as e:
            logger.error(f"[YouTubeAdapter] Failed to save token: {e}")

    async def _make_api_request(
        self,
        method: str,
        url: str,
        params: Optional[Dict] = None,
        json: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Make YouTube API request"""
        await self.refresh_token_if_needed()
        headers = {"Authorization": f"Bearer {self.token}"}

        client = await self._get_http_client()
        
        try:
            if method == "GET":
                response = await client.get(url, params=params, headers=headers)
            elif method == "POST":
                response = await client.post(url, params=params, headers=headers, json=json)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            error_reason = ""
            try:
                error_data = e.response.json()
                error_reason = error_data.get("error", {}).get("errors", [{}])[0].get("reason", "")
            except Exception:
                error_reason = e.response.text

            # Handle quota exceeded
            if error_reason == "quotaExceeded":
                logger.error("[YouTubeAdapter] ⚠️ QUOTA EXCEEDED - Daily limit reached")
                self.is_connected = False
                self._stop_polling = True
                self.last_error = "YouTube API quota exceeded"
                raise Exception("YouTube API quota exceeded")

            # Handle chat ended
            if status_code in (403, 404) or error_reason in ("liveChatEnded", "liveChatNotFound", "forbidden"):
                self.is_connected = False
                self._stop_polling = True
                self.live_chat_id = None
                self.last_error = f"Live chat ended or unavailable ({status_code})"
                logger.warning(f"[YouTubeAdapter] Chat ended: {status_code} - {error_reason}")
                raise Exception(f"Live chat ended: {error_reason}")

            logger.error(f"[YouTubeAdapter] API error: {status_code} - {error_reason}")
            raise

    async def log_channel_identity(self):
        """Get and log authorized channel info"""
        try:
            data = await self._make_api_request(
                "GET",
                "https://www.googleapis.com/youtube/v3/channels",
                params={"part": "id,snippet", "mine": "true"},
            )

            if data.get("items"):
                ch = data["items"][0]
                self.authorized_channel_id = ch["id"]
                self.authorized_channel_title = ch["snippet"]["title"]
                logger.info(f"[YouTubeAdapter] Channel: {self.authorized_channel_title} ({self.authorized_channel_id})")
        except Exception as e:
            logger.warning(f"[YouTubeAdapter] Failed to get channel identity: {e}")

    async def get_live_broadcast_id(self) -> Optional[str]:
        """Find active live chat ID"""
        try:
            data = await self._make_api_request(
                "GET",
                "https://www.googleapis.com/youtube/v3/liveBroadcasts",
                params={"part": "id,snippet,status", "mine": "true", "maxResults": 5},
            )

            if data.get("items"):
                for item in data["items"]:
                    live_chat_id = item.get("snippet", {}).get("liveChatId")
                    if live_chat_id:
                        logger.info(f"[YouTubeAdapter] Found liveChatId: {live_chat_id}")
                        return live_chat_id
        except Exception as e:
            logger.warning(f"[YouTubeAdapter] Failed to get live broadcast: {e}")

        return None

    async def fetch_chat_messages(self) -> List[Dict[str, Any]]:
        """Fetch new messages from live chat"""
        if not self.live_chat_id:
            return []

        params = {
            "liveChatId": self.live_chat_id,
            "part": "snippet,authorDetails",
            "maxResults": 200,
        }
        if self.next_page_token:
            params["pageToken"] = self.next_page_token

        try:
            data = await self._make_api_request(
                "GET",
                "https://www.googleapis.com/youtube/v3/liveChat/messages",
                params=params,
            )

            self.next_page_token = data.get("nextPageToken")
            self.polling_interval = data.get("pollingIntervalMillis", 5000) / 1000
            return data.get("items", [])

        except Exception as e:
            logger.error(f"[YouTubeAdapter] Fetch failed: {e}")
            return []

    async def send_message(self, text: str):
        """Send message to live chat"""
        if not self.live_chat_id:
            raise Exception("No active live chat")

        body = {
            "snippet": {
                "liveChatId": self.live_chat_id,
                "type": "textMessageEvent",
                "textMessageDetails": {"messageText": text},
            }
        }

        try:
            await self._make_api_request(
                "POST",
                "https://www.googleapis.com/youtube/v3/liveChat/messages",
                params={"part": "snippet"},
                json=body,
            )
            logger.info(f"[YouTubeAdapter] → Sent: {text}")
        except Exception as e:
            logger.error(f"[YouTubeAdapter] Send failed: {e}")
            raise

    async def connect(self):
        """Connect and start polling"""
        try:
            self.token, self.refresh_token, self.token_expires_at = await self.get_active_token()
            await self.refresh_token_if_needed()
            await self.log_channel_identity()

            live_id = await self.get_live_broadcast_id()
            if not live_id:
                self.last_error = "No active live stream found"
                logger.error("[YouTubeAdapter] No live stream")
                return

            self.live_chat_id = live_id
            await self.fetch_chat_messages()

            if not self.live_chat_id:
                return

            self.is_connected = True
            self._stop_polling = False
            logger.info(f"[YouTubeAdapter] Starting poll for {self.live_chat_id}")
            await self._poll_messages()

        except Exception as e:
            self.is_connected = False
            self.last_error = str(e)
            logger.error(f"[YouTubeAdapter] Connect error: {e}")

    async def connect_with_known_chat_id(self, live_chat_id: str):
        """Force attach to known chat ID"""
        try:
            self.token, self.refresh_token, self.token_expires_at = await self.get_active_token()
            await self.refresh_token_if_needed()
            await self.log_channel_identity()

            self.live_chat_id = live_chat_id
            self.is_connected = True
            self._stop_polling = False
            logger.info(f"[YouTubeAdapter] Polling (forced) {self.live_chat_id}")
            await self._poll_messages()
        except Exception as e:
            self.is_connected = False
            self.last_error = str(e)
            logger.error(f"[YouTubeAdapter] Forced attach error: {e}")

    async def _poll_messages(self):
        """Main polling loop"""
        consecutive_errors = 0
        while not self._stop_polling:
            try:
                items = await self.fetch_chat_messages()
                consecutive_errors = 0

                for msg in items:
                    snippet = msg.get("snippet", {})
                    author = msg.get("authorDetails", {})
                    text = (snippet.get("textMessageDetails") or {}).get("messageText") or ""
                    message_id = msg.get("id")

                    if not text or not message_id:
                        continue

                    # Skip own messages
                    author_channel_id = author.get("channelId")
                    if author_channel_id and self.authorized_channel_id and author_channel_id == self.authorized_channel_id:
                        continue

                    # Deduplication
                    if message_id in self._processed_message_ids:
                        logger.debug(f"[YouTubeAdapter] Duplicate filtered: {message_id}")
                        continue

                    self._processed_message_ids.add(message_id)

                    username = author.get("displayName", "Unknown")
                    logger.info(f"[YouTubeAdapter] {username}: {text}")

                    # Send to gateway
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        try:
                            await client.post(
                                "http://localhost:8081/messages/incoming",
                                json={
                                    "platform": "youtube",
                                    "user_id": self.user_id,
                                    "user_name": username,
                                    "content": text,
                                    "message_id": message_id
                                }
                            )
                        except Exception as e:
                            logger.error(f"[YouTubeAdapter] Failed to send to gateway: {e}")

                    # Cleanup old message IDs
                    if len(self._processed_message_ids) > 1000:
                        self._processed_message_ids.clear()

                await asyncio.sleep(self.polling_interval)

            except Exception as e:
                if "quota" in str(e).lower():
                    logger.error("[YouTubeAdapter] Stopping due to quota")
                    break
                consecutive_errors += 1
                backoff = min(5 * (2**consecutive_errors), 60)
                logger.error(f"[YouTubeAdapter] Poll error: {e}, retrying in {backoff}s")
                await asyncio.sleep(backoff)

    async def disconnect(self):
        """Disconnect and cleanup"""
        self._stop_polling = True
        self.is_connected = False
        self.live_chat_id = None
        self.next_page_token = None

        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

        logger.info(f"[YouTubeAdapter] Disconnected for user {self.user_id}")