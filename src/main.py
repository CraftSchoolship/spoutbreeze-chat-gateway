from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Set, Optional
from src.core.db_session import SessionLocal
from sqlalchemy import text
import json
import logging
import httpx
import os
from src.services.twitch_service import twitch_service
from src.services.youtube_service import youtube_service


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ChatGateway")

app = FastAPI(title="Chat Gateway Microservice")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple in-memory WebSocket client manager
websocket_clients: Set[WebSocket] = set()

# Configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
SHARED_SECRET = os.getenv("CHAT_GATEWAY_SHARED_SECRET", "dev-secret")


# === Models ===
class NormalizedMessage(BaseModel):
    platform: str
    type: str = "message"
    user: dict
    text: str
    timestamp: Optional[str] = None
    message_id: Optional[str] = None


class IncomingMessage(BaseModel):
    platform: str
    user_id: Optional[str] = None
    user_name: str
    content: str
    message_id: Optional[str] = None


class OutboundMessage(BaseModel):
    type: str = "outbound_message"
    platform: str
    text: str
    user: Optional[dict] = None


# === WebSocket Endpoint ===
@app.websocket("/ws/chat/")
async def websocket_chat_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for BBB plugin"""
    await websocket.accept()
    websocket_clients.add(websocket)
    logger.info(f"[WS] Client connected. Total: {len(websocket_clients)}")
    
    try:
        while True:
            data = await websocket.receive_json()
            
            # Handle outbound message (BBB → Platform)
            if data.get("type") == "outbound_message":
                try:
                    outbound = OutboundMessage(**data)
                    await route_outbound_message(outbound)
                except Exception as e:
                    logger.error(f"[WS] Error routing outbound: {e}")
    
    except WebSocketDisconnect:
        websocket_clients.discard(websocket)
        logger.info(f"[WS] Client disconnected. Total: {len(websocket_clients)}")
    except Exception as e:
        logger.error(f"[WS] Error: {e}")
        websocket_clients.discard(websocket)


# === Incoming Messages (from Twitch IRC clients) ===
@app.post("/messages/incoming")
async def receive_incoming_message(message: IncomingMessage):
    """Receive and normalize platform messages"""
    # ONLY broadcast to WebSocket clients (BBB)
    # Don't call this endpoint twice
    
    normalized = NormalizedMessage(
        platform=message.platform,
        type="message",
        user={
            "id": message.user_id,
            "name": message.user_name
        },
        text=message.content,
        message_id=message.message_id
    )
    
    logger.info(f"[Incoming] {message.platform} | {message.user_name}: {message.content}")
    
    # Broadcast ONLY to WebSocket clients (BBB plugin)
    await broadcast_to_clients(normalized.dict())
    
    return {"status": "received"}


# === Message Broadcasting ===
async def broadcast_to_clients(message: dict):
    """Broadcast normalized message to all WebSocket clients (BBB only)"""
    disconnected = set()
    
    for ws in websocket_clients:
        try:
            await ws.send_json(message)
            logger.debug(f"[Broadcast] Sent to 1 client")
        except Exception as e:
            logger.error(f"[Broadcast] Failed to send: {e}")
            disconnected.add(ws)
    
    websocket_clients.difference_update(disconnected)


# === Outbound Message Routing ===
async def route_outbound_message(message: OutboundMessage):
    """Route outbound messages directly to platform adapters"""
    if message.platform == "twitch":
        try:
            # Get the Twitch client for this user
            client = twitch_service.get_connection_for_user(message.user.get("id"))
            
            if not client:
                logger.error(f"[Outbound] No Twitch connection for user {message.user.get('id')}")
                return
            
            if not client.is_connected:
                logger.error(f"[Outbound] Twitch client not connected for user {message.user.get('id')}")
                return
            
            # Send message directly via the adapter
            await client.send_message(message.text)
            logger.info(f"[Outbound] Twitch message sent: {message.text}")
            
        except Exception as e:
            logger.error(f"[Outbound] Failed to send Twitch message: {e}")
    
    elif message.platform == "youtube":
        try:
            client = youtube_service.get_connection_for_user(message.user.get("id"))
            if not client or not client.is_connected:
                logger.error(f"[Outbound] No YouTube connection for user {message.user.get('id')}")
                return
            
            await client.send_message(message.text)
            logger.info(f"[Outbound] YouTube → {message.text}")
        except Exception as e:
            logger.error(f"[Outbound] YouTube send failed: {e}")
    
    else:
        logger.error(f"[Outbound] Unknown platform: {message.platform}")


# === Platform Registration (called by backend) ===
@app.post("/platforms/register")
async def register_platform(
    platform: str,
    user_id: str,
    x_internal_auth: str = Header(None, alias="X-Internal-Auth")
):
    """Register that a platform adapter is active for a user"""
    if x_internal_auth != SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # In a simple implementation, we don't need to track this
    # The backend manages connections, gateway just routes messages
    logger.info(f"[Register] {platform} registered for user {user_id}")
    
    return {"status": "registered", "platform": platform, "user_id": user_id}


# === Health Check ===
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "connected_clients": len(websocket_clients)
    }

# === DB Health Check ===
@app.get("/health/db")
async def check_db_connection():
    """
    Check the database connection.

    Returns:
        dict: Status of the database connection.
    """
    async with SessionLocal() as db:
        try:
            await db.execute(text("SELECT 1"))
            return {"status": "healthy"}
        except Exception as e:
            logger.error(f"[DB Check] Connection failed: {e}")
            return {"status": "unhealthy", "error": str(e)}

@app.get("/")
async def root():
    return {
        "service": "Chat Gateway Microservice",
        "version": "2.0-simplified",
        "endpoints": {
            "websocket": "/ws/chat/",
            "incoming": "/messages/incoming",
            "health": "/health",
            "db_health": "/health/db"
        }
    }

# === Startup ===
@app.on_event("startup")
async def startup():
    logger.info("[Gateway] Startup: loading active user connections...")
    # Load users from DB and start connections
    # (optional: you can lazy-load on-demand instead)

# === Connect/Disconnect endpoints ===
@app.post("/platforms/twitch/connect")
async def connect_twitch(
    user_id: str,
    x_internal_auth: str = Header(None, alias="X-Internal-Auth")
):
    """Start Twitch connection for a user"""
    if x_internal_auth != SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    await twitch_service.start_connection_for_user(user_id)
    return {"status": "connecting", "platform": "twitch", "user_id": user_id}


@app.post("/platforms/twitch/disconnect")
async def disconnect_twitch(
    user_id: str,
    x_internal_auth: str = Header(None, alias="X-Internal-Auth")
):
    """Stop Twitch connection for a user"""
    if x_internal_auth != SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    await twitch_service.stop_connection_for_user(user_id)
    return {"status": "disconnected", "platform": "twitch", "user_id": user_id}


# === YouTube endpoints ===
@app.post("/platforms/youtube/connect")
async def connect_youtube(
    user_id: str,
    x_internal_auth: str = Header(None, alias="X-Internal-Auth")
):
    """Start YouTube connection for a user"""
    if x_internal_auth != SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    await youtube_service.start_connection_for_user(user_id)
    return {"status": "connecting", "platform": "youtube", "user_id": user_id}


@app.post("/platforms/youtube/disconnect")
async def disconnect_youtube(
    user_id: str,
    x_internal_auth: str = Header(None, alias="X-Internal-Auth")
):
    """Stop YouTube connection for a user"""
    if x_internal_auth != SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    await youtube_service.stop_connection_for_user(user_id)
    return {"status": "disconnected", "platform": "youtube", "user_id": user_id}


@app.post("/platforms/youtube/connect-with-chat-id")
async def connect_youtube_with_chat_id(
    user_id: str,
    live_chat_id: str,
    x_internal_auth: str = Header(None, alias="X-Internal-Auth")
):
    """Force attach YouTube to a specific chat ID"""
    if x_internal_auth != SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    await youtube_service.start_with_chat_id(user_id, live_chat_id)
    return {"status": "connecting", "platform": "youtube", "user_id": user_id, "chat_id": live_chat_id}