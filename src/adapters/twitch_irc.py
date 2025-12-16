import asyncio
import ssl
from datetime import datetime, timedelta
# from sqlalchemy import select, text
from typing import Optional, Dict, Any
import contextlib
import uuid

from src.core.config import get_settings
from src.core.logger import get_logger
# from src.core.db_session import get_db
from src.core.token_fetcher import fetch_twitch_token
from src.schemas.chat import IncomingMessage
from src.api.messages import receive_incoming_message
from src.services.twitch_profile_service import get_twitch_channel_info

logger = get_logger("TwitchAdapter")


class TwitchIRCClient:
    def __init__(self, user_id: str, access_token: str):
        self.settings = get_settings()
        self.user_id = user_id
        self.access_token = access_token
        self.server = "irc.chat.twitch.tv"
        self.port = 6697
        self.nickname = None  # Will be fetched from Twitch API
        self.channel = None  # Will be fetched from Twitch API
        self.reader = None
        self.writer = None
        self.token = None
        self.is_connected: bool = False
        self.is_ready: bool = False

    def _get_public_ssl_context(self):
        """Create SSL context for Twitch"""
        ssl_context = ssl.create_default_context()
        cert_paths = [
            "/etc/ssl/certs/ca-certificates.crt",
            "/etc/pki/tls/certs/ca-bundle.crt",
            "/etc/ssl/cert.pem",
        ]
        for cert_path in cert_paths:
            try:
                ssl_context.load_verify_locations(cert_path)
                return ssl_context
            except FileNotFoundError:
                continue
        try:
            import certifi
            ssl_context.load_verify_locations(certifi.where())
            return ssl_context
        except ImportError:
            pass
        return ssl.create_default_context()

    async def get_active_token(self) -> str:
        """Get token via internal API (token_fetcher)"""
        try:
            token_data = await fetch_twitch_token(self.user_id)
            
            if token_data and token_data.get("access_token"):
                logger.info(f"[TwitchAdapter] Token loaded for user {self.user_id}")
                return token_data["access_token"]
            else:
                logger.error(f"[TwitchAdapter] No valid token for user {self.user_id}")
                raise Exception("No valid token")
            
        except Exception as e:
            logger.error(f"[TwitchAdapter] Token fetch error: {e}")
            raise

    # COMMENTED OUT: Old raw SQL implementation
    # async def get_active_token_raw_sql(self) -> str:
    #     """Get token from shared DB using raw SQL"""
    #     try:
    #         user_uuid = str(uuid.UUID(self.user_id))
    #
    #         async for db in get_db():
    #             query = text("""
    #                 SELECT access_token, expires_at 
    #                 FROM twitch_tokens 
    #                 WHERE user_id = :user_id 
    #                 AND is_active = true 
    #                 AND expires_at > NOW()
    #                 ORDER BY created_at DESC 
    #                 LIMIT 1
    #             """)
    #             
    #             result = await db.execute(query, {"user_id": user_uuid})
    #             row = result.first()
    #             
    #             if row:
    #                 logger.info(f"[TwitchAdapter] Token loaded for user {self.user_id}")
    #                 return row[0]
    #             else:
    #                 logger.error(f"[TwitchAdapter] No valid token for user {self.user_id}")
    #                 raise Exception("No valid token")
    #         
    #     except Exception as e:
    #         logger.error(f"[TwitchAdapter] Token fetch error: {e}")
    #         raise

    async def fetch_channel_info(self):
        """Fetch nickname and channel from Twitch API"""
        try:
            channel_info = await get_twitch_channel_info(self.user_id, self.access_token)
            if channel_info:
                self.nickname = channel_info["nickname"]
                self.channel = channel_info["channel"]
                logger.info(f"[TwitchAdapter] Fetched channel info - nickname: {self.nickname}, channel: {self.channel}")
                return True
            else:
                logger.error(f"[TwitchAdapter] Failed to fetch channel info for user {self.user_id}")
                return False
        except Exception as e:
            logger.error(f"[TwitchAdapter] Error fetching channel info: {e}")
            return False

    async def connect(self):
        """Connect to Twitch IRC"""
        while True:
            try:
                if not self.access_token:
                    logger.error("[TwitchAdapter] No token, retrying in 30s...")
                    await asyncio.sleep(30)
                    continue

                # Fetch channel info before connecting
                if not self.nickname or not self.channel:
                    success = await self.fetch_channel_info()
                    if not success:
                        logger.error("[TwitchAdapter] Cannot connect without channel info, retrying in 30s...")
                        await asyncio.sleep(30)
                        continue

                ssl_context = self._get_public_ssl_context()
                self.reader, self.writer = await asyncio.open_connection(
                    self.server, self.port, ssl=ssl_context
                )

                # Request capabilities for better IRC features
                self.writer.write(b"CAP REQ :twitch.tv/membership twitch.tv/tags twitch.tv/commands\r\n")
                self.writer.write(f"PASS oauth:{self.access_token}\r\n".encode())
                self.writer.write(f"NICK {self.nickname}\r\n".encode())
                await self.writer.drain()
                
                # Wait for server greeting
                await asyncio.sleep(1)
                
                self.writer.write(f"JOIN {self.channel}\r\n".encode())
                await self.writer.drain()

                self.is_connected = True
                logger.info(f"[TwitchAdapter] Connected to Twitch IRC for user {self.user_id} as {self.nickname}")
                
                # Wait for JOIN confirmation before marking as ready
                await asyncio.sleep(2)
                self.is_ready = True
                logger.info(f"[TwitchAdapter] Ready to send messages in {self.channel}")
                
                await self.listen()
            except Exception as e:
                self.is_connected = False
                self.is_ready = False
                logger.error(f"[TwitchAdapter] Connection error: {e}")
                await asyncio.sleep(5)

    async def listen(self):
        """Listen for IRC messages"""
        while True:
            try:
                line = await self.reader.readline()
                if not line:
                    self.is_connected = False
                    self.is_ready = False
                    raise ConnectionResetError("Stream closed")
                msg = line.decode(errors="ignore").strip()

                if msg.startswith("PING"):
                    self.writer.write(b"PONG :tmi.twitch.tv\r\n")
                    await self.writer.drain()
                    continue

                # Check for successful JOIN
                if f"JOIN {self.channel}" in msg and self.nickname in msg:
                    self.is_ready = True
                    logger.info(f"[TwitchAdapter] Successfully joined {self.channel}")

                await self._handle_message(msg)
            except Exception as e:
                self.is_connected = False
                self.is_ready = False
                logger.error(f"[TwitchAdapter] Listen error: {e}")
                raise

    async def _handle_message(self, message: str) -> None:
        """Parse and broadcast IRC message"""
        if "PRIVMSG" in message:
            try:
                message_id = None
                if message.startswith("@"):
                    tags_end = message.find(" ")
                    if tags_end > 0:
                        tags_section = message[:tags_end]
                        tags = dict(
                            tag.split("=", 1)
                            for tag in tags_section[1:].split(";")
                            if "=" in tag
                        )
                        message_id = tags.get("id")

                parts = message.split(":", 2)
                if len(parts) >= 3:
                    username = parts[1].split("!")[0]
                    msg_content = parts[2].strip()

                    logger.info(f"[TwitchAdapter] {username}: {msg_content}")

                    incoming_msg = IncomingMessage(
                        platform="twitch",
                        user_id=self.user_id,
                        user_name=username,
                        content=msg_content,
                        message_id=message_id
                    )
                    await receive_incoming_message(incoming_msg)
            except Exception as e:
                logger.error(f"[TwitchAdapter] Parse error: {e}")

    async def send_message(self, message: str):
        """Send message to Twitch chat"""
        if not self.is_ready:
            logger.warning(f"[TwitchAdapter] Cannot send - not ready yet (connected={self.is_connected}, ready={self.is_ready})")
            return
            
        if not self.writer:
            logger.error(f"[TwitchAdapter] Cannot send - no writer")
            return

        try:
            full_message = f"PRIVMSG {self.channel} :{message}\r\n"
            self.writer.write(full_message.encode())
            await self.writer.drain()
            logger.info(f"[TwitchAdapter] ✅ Sent to {self.channel}: {message}")
        except Exception as e:
            logger.error(f"[TwitchAdapter] Send error: {e}")

    async def disconnect(self):
        """Gracefully disconnect"""
        try:
            if self.writer:
                self.writer.write(f"PART {self.channel}\r\n".encode())
                await self.writer.drain()
                self.writer.close()
                with contextlib.suppress(Exception):
                    await self.writer.wait_closed()
        finally:
            self.reader = None
            self.writer = None
            self.is_connected = False
            self.is_ready = False
        logger.info(f"[TwitchAdapter] Disconnected user {self.user_id}")