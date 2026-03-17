import pytest
from sqlalchemy import event
import importlib

# Patch PostgreSQL-specific types BEFORE importing any app code.
# SQLite doesn't support TSVECTOR, JSONB, or native UUID, so we remap them.
import sqlalchemy.dialects.postgresql as pg_dialect
from sqlalchemy import types as sa_types, Text


class _SQLiteUUID(sa_types.TypeDecorator):
    """UUID stored as CHAR(32) in SQLite."""
    impl = sa_types.CHAR
    cache_ok = True

    def __init__(self, *args, **kwargs):
        kwargs.pop("as_uuid", None)
        super().__init__(length=32)

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(sa_types.CHAR(32))
        return dialect.type_descriptor(sa_types.CHAR(32))  # always use CHAR for tests

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        import uuid as _uuid
        if isinstance(value, _uuid.UUID):
            return value.hex
        return str(value).replace("-", "")

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        import uuid as _uuid
        if not isinstance(value, _uuid.UUID):
            return _uuid.UUID(value)
        return value


class _SQLiteJSONB(sa_types.TypeDecorator):
    """JSONB stored as JSON text in SQLite."""
    impl = sa_types.JSON
    cache_ok = True


class _SQLiteTSVECTOR(sa_types.TypeDecorator):
    """TSVECTOR mapped to Text (unused) in SQLite."""
    impl = Text
    cache_ok = True


# Monkey-patch the dialect types
pg_dialect.UUID = _SQLiteUUID
pg_dialect.JSONB = _SQLiteJSONB
pg_dialect.TSVECTOR = _SQLiteTSVECTOR

# Reload models so they pick up the patched types, then reload
# everything that depends on models.
import app.models
importlib.reload(app.models)

import app.routers.documents
importlib.reload(app.routers.documents)

import app.routers.search
importlib.reload(app.routers.search)

import app.main
importlib.reload(app.main)

from app.models import Base
from app.main import app
from app.database import get_db

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

TEST_DB_URL = "sqlite+aiosqlite://"  # in-memory

engine = create_async_engine(TEST_DB_URL, echo=False)
TestSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSession() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
async def setup_db():
    """Create and tear down database tables for each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
