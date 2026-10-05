import os
from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", extra="allow")

    APP_NAME: str = "SALESTORM High-Scale Flash-Sale API Engine"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    # Port & Host
    PORT: int = int(os.getenv("PORT", "8080"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql://salestorm_user:salestorm_password@localhost:5432/salestorm_db"
    )
    SQL_ECHO: bool = False
    
    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Flash Sale Parameters
    FLASH_SALE_PRODUCT_ID: str = os.getenv("FLASH_SALE_PRODUCT_ID", "550e8400-e29b-41d4-a716-446655440000")
    INITIAL_STOCK: int = int(os.getenv("INITIAL_STOCK", "100"))
    RESERVATION_LEASE_SECONDS: int = int(os.getenv("RESERVATION_LEASE_SECONDS", "300"))  # 5 Minutes
    
    # Idempotency
    IDEMPOTENCY_TTL_SECONDS: int = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", "86400"))  # 24 Hours

settings = Settings()
