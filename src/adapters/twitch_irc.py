import asyncio
import httpx
import ssl
from datetime import datetime, timedelta
from sqlalchemy import select, text
from typing import Optional, Dict, Any
import contextlib
import uuid

from src.core.config import get_settings
from src.core.logger import get_logger
from src.core.db_session import get_db

logger = get_logger("TwitchAdapter")


class TwitchIRCClient:
    def __init__(self, user_id: str):
        self.settings = get_settings()
        self.user_id = user_id
        self.server = "irc.chat.twitch.tv"
        self.port = 6697
        self.nickname = "divinehope1"  # Can be any name for read-only
        self.channel = "#divinehope1"
        self.reader = None
        self.writer = None
        self.token = None
        self.is_connected: bool = False

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
        """Get token from shared DB using raw SQL"""
        try:
            user_uuid = str(uuid.UUID(self.user_id))

            async for db in get_db():
                # Use raw SQL to avoid importing backend models
                query = text("""
                    SELECT access_token, expires_at 
                    FROM twitch_tokens 
                    WHERE user_id = :user_id 
                    AND is_active = true 
                    AND expires_at > NOW()
                    ORDER BY created_at DESC 
                    LIMIT 1
                """)
                
                result = await db.execute(query, {"user_id": user_uuid})
                row = result.first()
                
                if row:
                    logger.info(f"[TwitchAdapter] Token loaded for user {self.user_id}")
                    return row[0]  # access_token
                else:
                    logger.error(f"[TwitchAdapter] No valid token for user {self.user_id}")
                    raise Exception("No valid token")
            
        except Exception as e:
            logger.error(f"[TwitchAdapter] Token fetch error: {e}")
            raise

    async def refresh_token_if_needed(self) -> bool:
        """Refresh token if expiring soon"""
        try:
            user_uuid = str(uuid.UUID(self.user_id))

            async for db in get_db():
                query = text("""
                    SELECT access_token, refresh_token, expires_at 
                    FROM twitch_tokens 
                    WHERE user_id = :user_id 
                    AND is_active = true
                    ORDER BY created_at DESC 
                    LIMIT 1
                """)
                
                result = await db.execute(query, {"user_id": user_uuid})
                row = result.first()

                if not row:
                    return False

                expires_at = row[2]
                expires_soon = datetime.now() + timedelta(minutes=5)
                
                if expires_at <= expires_soon:
                    refresh_token = row[1]
                    if refresh_token:
                        new_token_data = await self._refresh_access_token(refresh_token)
                        if new_token_data:
                            new_expires_at = datetime.now() + timedelta(seconds=new_token_data.get("expires_in", 3600))
                            
                            update_query = text("""
                                UPDATE twitch_tokens 
                                SET access_token = :access_token,
                                    expires_at = :expires_at,
                                    refresh_token = :refresh_token
                                WHERE user_id = :user_id 
                                AND is_active = true
                            """)
                            
                            await db.execute(update_query, {
                                "access_token": new_token_data["access_token"],
                                "expires_at": new_expires_at,
                                "refresh_token": new_token_data.get("refresh_token", refresh_token),
                                "user_id": user_uuid
                            })
                            await db.commit()
                            logger.info(f"[TwitchAdapter] Token refreshed for user {self.user_id}")
                            return True
                    
                    # Token expired and can't refresh
                    deactivate_query = text("UPDATE twitch_tokens SET is_active = false WHERE user_id = :user_id")
                    await db.execute(deactivate_query, {"user_id": user_uuid})
                    await db.commit()
                    return False
                break
        except Exception as e:
            logger.error(f"[TwitchAdapter] Refresh error: {e}")
        return False

    async def _refresh_access_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """Refresh token via Twitch OAuth"""
        try:
            ssl_context = self._get_public_ssl_context()
            async with httpx.AsyncClient(verify=ssl_context) as client:
                response = await client.post(
                    "https://id.twitch.tv/oauth2/token",
                    data={
                        "client_id": self.settings.TWITCH_CLIENT_ID,
                        "client_secret": self.settings.TWITCH_CLIENT_SECRET,
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                    },
                )
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.error(f"[TwitchAdapter] Token refresh failed: {e}")
        return None

    async def connect(self):
        """Connect to Twitch IRC"""
        while True:
            try:
                await self.refresh_token_if_needed()
                self.token = await self.get_active_token()

                if not self.token:
                    logger.error("[TwitchAdapter] No token, retrying in 30s...")
                    await asyncio.sleep(30)
                    continue

                ssl_context = self._get_public_ssl_context()
                self.reader, self.writer = await asyncio.open_connection(
                    self.server, self.port, ssl=ssl_context
                )

                self.writer.write(f"PASS oauth:{self.token}\r\n".encode())
                self.writer.write(f"NICK {self.nickname}\r\n".encode())
                self.writer.write(f"JOIN {self.channel}\r\n".encode())
                await self.writer.drain()

                self.is_connected = True
                logger.info(f"[TwitchAdapter] Connected to Twitch IRC for user {self.user_id}")
                await self.listen()
            except Exception as e:
                self.is_connected = False
                logger.error(f"[TwitchAdapter] Connection error: {e}")
                await asyncio.sleep(5)

    async def listen(self):
        """Listen for IRC messages"""
        while True:
            try:
                line = await self.reader.readline()
                if not line:
                    self.is_connected = False
                    raise ConnectionResetError("Stream closed")
                msg = line.decode(errors="ignore").strip()

                if msg.startswith("PING"):
                    self.writer.write(b"PONG :tmi.twitch.tv\r\n")
                    await self.writer.drain()
                    continue

                await self._handle_message(msg)
            except Exception as e:
                self.is_connected = False
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

                    # Only send to backend/gateway once:
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            "http://localhost:8800/messages/incoming",
                            json={
                                "platform": "twitch",
                                "user_id": self.user_id,
                                "user_name": username,
                                "content": msg_content,
                                "message_id": message_id
                            }
                        )
            except Exception as e:
                logger.error(f"[TwitchAdapter] Parse error: {e}")

    async def send_message(self, message: str):
        """Send message to Twitch chat"""
        if self.writer:
            full_message = f"PRIVMSG {self.channel} :{message}\r\n"
            self.writer.write(full_message.encode())
            await self.writer.drain()
            logger.info(f"[TwitchAdapter] → {message}")

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
        logger.info(f"[TwitchAdapter] Disconnected user {self.user_id}")