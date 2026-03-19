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

    # Model Configuration
    generation_model: str = os.getenv("GENERATION_MODEL", "gpt-5.2")
    generation_temperature: float = float(os.getenv("GENERATION_TEMPERATURE", "0.3"))
    generation_seed: int = int(os.getenv("GENERATION_SEED", "42"))
    chat_model: str = os.getenv("CHAT_MODEL", "gpt-5.2")
    chat_temperature: float = float(os.getenv("CHAT_TEMPERATURE", "0.7"))
    lightweight_model: str = os.getenv("LIGHTWEIGHT_MODEL", "gpt-4o-mini")
    policy_check_temperature: float = float(os.getenv("POLICY_CHECK_TEMPERATURE", "0.1"))

    # Token Budget Configuration
    token_budget: int = int(os.getenv("TOKEN_BUDGET", "150000"))
    tokens_per_segment: int = int(os.getenv("TOKENS_PER_SEGMENT", "75"))

    # Debug Endpoints
    enable_debug_endpoints: bool = os.getenv("ENABLE_DEBUG_ENDPOINTS", "false").lower() in ("1", "true", "yes", "y")
    debug_token: str = os.getenv("DEBUG_TOKEN", "")

    class Config:
        env_file = ".env"

settings = Settings()