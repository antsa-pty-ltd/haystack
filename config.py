import os
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # OpenAI Configuration
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    
    # Redis Configuration
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    # Database Configuration
    database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/dbname")
    
    # NestJS API Configuration
    nestjs_api_url: str = os.getenv("NESTJS_API_URL", "http://localhost:8080")
    
    # Service Configuration
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    max_requests_per_user: int = int(os.getenv("MAX_REQUESTS_PER_USER", "10"))
    session_timeout_minutes: int = int(os.getenv("SESSION_TIMEOUT_MINUTES", "240"))  # 4 hours instead of 30 minutes
    
    # Tool display configuration
    show_tool_banner: bool = os.getenv("SHOW_TOOL_BANNER", "true").lower() in ("1", "true", "yes", "y")
    show_raw_tool_json: bool = os.getenv("SHOW_RAW_TOOL_JSON", "false").lower() in ("1", "true", "yes", "y")
    
    # Legacy setting - now used for documentation only
    max_concurrent_requests: int = int(os.getenv("MAX_CONCURRENT_REQUESTS", "10000"))  # Theoretical max
    
    # FastAPI Configuration
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8001"))
    
    class Config:
        env_file = ".env"

settings = Settings()