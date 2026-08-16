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
    ANTHROPIC_API_KEY: str = ""
    TMDB_API_KEY: str = ""
    REDIS_URL: str = "redis://localhost:6379/0"

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_USE_TLS: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# Singleton — import cái này ở nơi khác thay vì tạo Settings() nhiều lần
settings = Settings()
