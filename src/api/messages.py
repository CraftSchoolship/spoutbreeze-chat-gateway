from fastapi import APIRouter
import logging

from src.schemas.chat import IncomingMessage, NormalizedMessage
from src.core.websocket_manager import broadcast_to_clients

router = APIRouter(tags=["Messages"])
logger = logging.getLogger("ChatGateway")

@router.post("/messages/incoming")
async def receive_incoming_message(message: IncomingMessage):
    normalized = NormalizedMessage(
        platform=message.platform,
        type="message",
        user={"id": message.user_id, "name": message.user_name},
        text=message.content,
        message_id=message.message_id,
    )
    logger.info(f"[Incoming] {message.platform} | {message.user_name}: {message.content}")
    await broadcast_to_clients(normalized.dict())
    return {"status": "received"}