from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from src.core.config import get_settings
from src.api.websocket import router as websocket_router
from src.api.messages import router as messages_router
from src.api.platforms import router as platforms_router
from src.api.health import router as health_router
from src.services.youtube_service import youtube_service
from src.services.twitch_service import twitch_service

settings = get_settings()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ChatGateway")

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(websocket_router)
app.include_router(messages_router)
app.include_router(platforms_router)
app.include_router(health_router)


@app.on_event("startup")
async def startup():
    logger.info(f"[Gateway] Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"[Gateway] WebSocket endpoint: ws://localhost:{settings.API_PORT}/ws/chat/")
    logger.info(f"[Gateway] Redis: {settings.REDIS_URL}")
    
    # Restore platform connections from Redis
    logger.info("[Gateway] Restoring platform connections...")
    await youtube_service.restore_connections()
    await twitch_service.restore_connections()
    logger.info("[Gateway] Connection restoration complete")


@app.on_event("shutdown")
async def shutdown():
    logger.info("[Gateway] Shutting down gracefully...")