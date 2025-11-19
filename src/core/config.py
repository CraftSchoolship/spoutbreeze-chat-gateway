from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",  # Allow extra fields from .env without error
    )

    # General settings
    APP_NAME: str = "Chat Gateway Microservice"
    APP_VERSION: str = "1.0.0"

    # API settings
    API_PREFIX: str = "/api/v1"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8081

    # Logging
    LOG_LEVEL: str = "INFO"

    # Twitch settings
    TWITCH_CLIENT_ID: str
    TWITCH_CLIENT_SECRET: str
    TWITCH_REDIRECT_URI: str = "http://localhost:8081/twitch/callback"

    # YouTube settings
    YOUTUBE_CLIENT_ID: str
    YOUTUBE_CLIENT_SECRET: str

    # Redis settings
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # Message Queue
    MESSAGE_QUEUE_TYPE: str = "redis"
    MESSAGE_QUEUE_URL: str = "redis://localhost:6379/0"

    # Security
    CHAT_GATEWAY_SHARED_SECRET: str = "dev-secret"

    # Backend url
    BACKEND_URL: str = "http://localhost:8000"

    # Database settings
    DB_URL: str


def get_settings() -> Settings:
    return Settings()
