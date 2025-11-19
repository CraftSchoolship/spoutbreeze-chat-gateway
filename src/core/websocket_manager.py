from typing import Set, Dict, Any, Optional
from fastapi import WebSocket
import logging

logger = logging.getLogger("ChatGateway")

_websocket_clients: Set[WebSocket] = set()
_connections_meta: Dict[WebSocket, Dict[str, Any]] = {}

def add_client(ws: WebSocket, user_id: Optional[str] = None, meeting_id: Optional[str] = None) -> None:
    _websocket_clients.add(ws)
    _connections_meta[ws] = {"user_id": user_id, "meeting_id": meeting_id}
    logger.info(f"[WS] Client connected. Total: {len(_websocket_clients)}")

def remove_client(ws: WebSocket) -> None:
    if ws in _websocket_clients:
        _websocket_clients.discard(ws)
        _connections_meta.pop(ws, None)
        logger.info(f"[WS] Client disconnected. Total: {len(_websocket_clients)}")

def connected_count() -> int:
    return len(_websocket_clients)

def get_ws_user_id(ws: WebSocket) -> Optional[str]:
    meta = _connections_meta.get(ws)
    return meta.get("user_id") if meta else None

async def broadcast_to_clients(message: dict) -> None:
    disconnected = set()
    for ws in _websocket_clients:
        try:
            await ws.send_json(message)
        except Exception as e:
            logger.error(f"[Broadcast] Failed to send: {e}")
            disconnected.add(ws)
    for ws in disconnected:
        remove_client(ws)