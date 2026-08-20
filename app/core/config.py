"""
Đọc cấu hình từ file .env.
Dùng pydantic-settings để tự động validate và parse biến môi trường.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    TMDB_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-2"
    GEMINI_API_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"
    REDIS_URL: str = "redis://localhost:6379/0"
    AI_REQUESTS_PER_USER_PER_DAY: int = 20
    AI_REQUESTS_PER_IP_PER_DAY: int = 100
    AI_PROMPT_CACHE_TTL_SECONDS: int = 86400
    COLLECTOR_LOCK_TTL_SECONDS: int = 3600
    ENABLE_INTERNAL_BOOKING: bool = False

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_USE_TLS: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# Singleton — import cái này ở nơi khác thay vì tạo Settings() nhiều lần
settings = Settings()
