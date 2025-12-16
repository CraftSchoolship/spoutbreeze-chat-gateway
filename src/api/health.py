from fastapi import APIRouter
import logging

from src.core.websocket_manager import connected_count

router = APIRouter(tags=["Health"])
logger = logging.getLogger("ChatGateway")

@router.get("/health")
async def health_check():
    return {"status": "healthy", "connected_clients": connected_count()}

@router.get("/")
async def root():
    return {
        "service": "Chat Gateway Microservice",
        "version": "2.0-simplified",
        "endpoints": {
            "websocket": "/ws/chat/",
            "incoming": "/messages/incoming",
            "health": "/health",
            "db_health": "/health/db",
        },
    }
