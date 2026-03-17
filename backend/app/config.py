import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/redline"

    model_config = {"env_prefix": "REDLINE_"}


# Railway sets DATABASE_URL; override if present
_railway_url = os.environ.get("DATABASE_URL")
if _railway_url:
    settings = Settings(database_url=_railway_url.replace("postgresql://", "postgresql+asyncpg://"))
else:
    settings = Settings()
