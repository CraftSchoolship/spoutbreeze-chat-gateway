from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Set, Optional
import json
import logging
import httpx
import os

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


# === Message Broadcasting ===
async def broadcast_to_clients(message: dict):
    """Broadcast normalized message to all WebSocket clients"""
    disconnected = set()
    
    for ws in websocket_clients:
        try:
            await ws.send_json(message)
        except Exception as e:
            logger.error(f"[Broadcast] Failed to send: {e}")
            disconnected.add(ws)
    
    websocket_clients.difference_update(disconnected)


# === Incoming Messages (from Backend IRC clients) ===
@app.post("/messages/incoming")
async def receive_incoming_message(message: IncomingMessage):
    """Receive and normalize platform messages"""
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
    
    await broadcast_to_clients(normalized.dict())
    
    return {"status": "received"}


# === Outbound Message Routing ===
async def route_outbound_message(message: OutboundMessage):
    """Route outbound messages to appropriate backend endpoint"""
    if message.platform == "twitch":
        url = f"{BACKEND_URL}/api/auth/twitch/send-message"
        headers = {"X-Internal-Auth": SHARED_SECRET}
        
        async with httpx.AsyncClient(timeout=5) as client:
            try:
                response = await client.post(
                    url,
                    json={
                        "user_id": message.user.get("id") if message.user else None,
                        "message": message.text
                    },
                    headers=headers
                )
                response.raise_for_status()
                logger.info(f"[Outbound] Twitch message sent: {message.text}")
            except Exception as e:
                logger.error(f"[Outbound] Failed to send Twitch message: {e}")
    
    elif message.platform == "youtube":
        url = f"{BACKEND_URL}/api/auth/youtube/send-message"
        headers = {"X-Internal-Auth": SHARED_SECRET}
        
        async with httpx.AsyncClient(timeout=5) as client:
            try:
                response = await client.post(
                    url,
                    json={
                        "user_id": message.user.get("id") if message.user else None,
                        "message": message.text
                    },
                    headers=headers
                )
                response.raise_for_status()
                logger.info(f"[Outbound] YouTube message sent: {message.text}")
            except Exception as e:
                logger.error(f"[Outbound] Failed to send YouTube message: {e}")
    
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


@app.get("/")
async def root():
    return {
        "service": "Chat Gateway Microservice",
        "version": "2.0-simplified",
        "endpoints": {
            "websocket": "/ws/chat/",
            "incoming": "/messages/incoming",
            "health": "/health"
        }
    }