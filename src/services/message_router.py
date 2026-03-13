import logging
from src.schemas.chat import OutboundMessage
from src.services.facebook_service import facebook_service
from src.services.twitch_service import twitch_service
from src.services.youtube_service import youtube_service

logger = logging.getLogger("ChatGateway")

async def route_outbound_message(message: OutboundMessage) -> None:
    if message.platform == "twitch":
        try:
            uid = message.user.get("id") if message.user else None
            client = twitch_service.get_connection_for_user(uid)
            if not client:
                logger.error(f"[Outbound] No Twitch connection for user {uid}")
                return
            if not client.is_connected:
                logger.error(f"[Outbound] Twitch client not connected for user {uid}")
                return
            await client.send_message(message.text)
            logger.info(f"[Outbound] Twitch message sent: {message.text}")
        except Exception as e:
            logger.error(f"[Outbound] Failed to send Twitch message: {e}")
    elif message.platform == "youtube":
        try:
            uid = message.user.get("id") if message.user else None
            client = youtube_service.get_connection_for_user(uid)
            if not client or not client.is_connected:
                logger.error(f"[Outbound] No YouTube connection for user {uid}")
                return
            await client.send_message(message.text)
            logger.info(f"[Outbound] YouTube → {message.text}")
        except Exception as e:
            logger.error(f"[Outbound] YouTube send failed: {e}")
    elif message.platform == "facebook":
        try:
            uid = message.user.get("id") if message.user else None
            client = facebook_service.get_connection_for_user(uid)
            if not client or not client.is_connected:
                logger.error(f"[Outbound] No Facebook connection for user {uid}")
                return
            await client.send_message(message.text)
            logger.info(f"[Outbound] Facebook → {message.text}")
        except Exception as e:
            logger.error(f"[Outbound] Facebook send failed: {e}")
    else:
        logger.error(f"[Outbound] Unknown platform: {message.platform}")
