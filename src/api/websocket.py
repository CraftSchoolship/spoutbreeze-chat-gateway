from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import logging

from src.schemas.chat import OutboundMessage
from src.core.websocket_manager import add_client, remove_client, get_ws_user_id
from src.core.redis_client import get_user_id_by_meeting
from src.services.message_router import route_outbound_message

router = APIRouter()
logger = logging.getLogger("ChatGateway")

@router.websocket("/ws/chat/")
async def websocket_chat_endpoint(websocket: WebSocket):
    logger.info(f"[WS] New connection attempt from {websocket.client}")
    await websocket.accept()
    logger.info("[WS] WebSocket accepted")
    
    meeting_id = websocket.query_params.get("meeting_id")
    logger.info(f"[WS] Meeting ID from query params: {meeting_id}")
    
    user_id = None
    if meeting_id:
        try:
            user_id = await get_user_id_by_meeting(meeting_id)
            logger.info(f"[WS] Resolved user_id={user_id} for meeting={meeting_id}")
        except Exception as e:
            logger.error(f"[WS] Redis lookup failed for meeting {meeting_id}: {e}")
    else:
        logger.warning("[WS] No meeting_id provided in query params")
    
    add_client(websocket, user_id=user_id, meeting_id=meeting_id)

    try:
        while True:
            data = await websocket.receive_json()
            logger.info(f"[WS] Received data: {data}")
            
            if data.get("type") == "outbound_message":
                try:
                    # Fill user.id from WS context if missing
                    if not data.get("user") or not data["user"].get("id"):
                        resolved = get_ws_user_id(websocket)
                        if resolved:
                            data["user"] = {"id": resolved}
                            logger.info(f"[WS] Auto-filled user.id={resolved}")
                    
                    outbound = OutboundMessage(**data)
                    logger.info(f"[WS] Routing outbound: platform={outbound.platform}, text={outbound.text}")
                    await route_outbound_message(outbound)
                except Exception as e:
                    logger.error(f"[WS] Error routing outbound: {e}", exc_info=True)
    except WebSocketDisconnect:
        logger.info("[WS] Client disconnected normally")
        remove_client(websocket)
    except Exception as e:
        logger.error(f"[WS] Unexpected error: {e}", exc_info=True)
        remove_client(websocket)