from fastapi import APIRouter
from sqlalchemy import text
import logging

from src.core.db_session import SessionLocal
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

@router.get("/health/db")
async def check_db_connection():
    async with SessionLocal() as db:
        try:
            await db.execute(text("SELECT 1"))
            return {"status": "healthy"}
        except Exception as e:
            logger.error(f"[DB Check] Connection failed: {e}")
            return {"status": "unhealthy", "error": str(e)}