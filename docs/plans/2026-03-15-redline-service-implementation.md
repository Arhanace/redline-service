# Redline Service Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a document redlining service with side-by-side editing, full-text search, change history, and bulk operations.

**Architecture:** FastAPI backend with async SQLAlchemy + PostgreSQL for persistence and full-text search. React + Vite frontend with diff-match-patch for computing changes and a side-by-side diff editor. Docker Compose for local dev, Railway for production hosting.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy (async), PostgreSQL, Alembic, pytest, React 18, Vite, TailwindCSS, diff-match-patch, Docker Compose

---

## Task 1: Project Scaffolding + Docker Compose

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/Dockerfile`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `backend/tests/__init__.py`
- Create: `docker-compose.yml`
- Create: `.gitignore`

**Step 1: Initialize git repo**

```bash
cd /Users/arhansalunke/redline-service
git init
```

**Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
.env
node_modules/
dist/
.venv/
*.egg-info/
```

**Step 3: Create `backend/pyproject.toml`**

```toml
[project]
name = "redline-service"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi[standard]>=0.115.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.30.0",
    "alembic>=1.14.0",
    "pydantic-settings>=2.0.0",
    "uvicorn>=0.30.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.27.0",
    "aiosqlite>=0.20.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Step 4: Create `backend/app/config.py`**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/redline"
    test_database_url: str = "sqlite+aiosqlite:///./test.db"

    model_config = {"env_prefix": "REDLINE_"}


settings = Settings()
```

**Step 5: Create `backend/app/main.py`** (minimal FastAPI app)

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Redline Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

**Step 6: Create `backend/Dockerfile`**

```dockerfile
FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

**Step 7: Create `docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: redline
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      REDLINE_DATABASE_URL: postgresql+asyncpg://postgres:postgres@db:5432/redline
    depends_on:
      - db
    volumes:
      - ./backend:/app

volumes:
  pgdata:
```

**Step 8: Create empty `__init__.py` files**

```bash
touch backend/app/__init__.py backend/tests/__init__.py
```

**Step 9: Verify backend starts**

```bash
cd /Users/arhansalunke/redline-service
docker compose up --build -d
# Wait for services, then:
curl http://localhost:8000/api/health
# Expected: {"status":"ok"}
docker compose down
```

**Step 10: Commit**

```bash
git add -A
git commit -m "feat: project scaffolding with FastAPI, Docker Compose, Postgres"
```

---

## Task 2: Database Models + Migrations

**Files:**
- Create: `backend/app/database.py`
- Create: `backend/app/models.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`

**Step 1: Create `backend/app/database.py`**

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session() as session:
        yield session
```

**Step 2: Create `backend/app/models.py`**

```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False, default="")
    search_vector = Column(TSVECTOR)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    changes = relationship("ChangeHistory", back_populates="document", order_by="ChangeHistory.created_at.desc()")

    __table_args__ = (
        Index("ix_documents_search_vector", "search_vector", postgresql_using="gin"),
    )


class ChangeHistory(Base):
    __tablename__ = "change_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    changes = Column(JSONB, nullable=False)
    previous_content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    document = relationship("Document", back_populates="changes")

    __table_args__ = (
        Index("ix_change_history_doc_created", "document_id", "created_at"),
    )
```

**Step 3: Set up Alembic**

Create `backend/alembic.ini`:
```ini
[alembic]
script_location = alembic
sqlalchemy.url = postgresql+asyncpg://postgres:postgres@localhost:5432/redline

[loggers]
keys = root

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[handler_console]
class = StreamHandler
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

Create `backend/alembic/script.py.mako`:
```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

Create `backend/alembic/env.py`:
```python
import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

**Step 4: Generate initial migration**

```bash
cd /Users/arhansalunke/redline-service/backend
pip install -e ".[dev]"
alembic revision --autogenerate -m "initial tables"
```

**Step 5: Manually add the tsvector trigger to the migration**

In the generated migration file, add after the table creation in `upgrade()`:

```python
# Add tsvector auto-update trigger
op.execute("""
    CREATE OR REPLACE FUNCTION documents_search_vector_update() RETURNS trigger AS $$
    BEGIN
        NEW.search_vector := to_tsvector('english', COALESCE(NEW.title, '') || ' ' || COALESCE(NEW.content, ''));
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER documents_search_vector_trigger
        BEFORE INSERT OR UPDATE OF title, content ON documents
        FOR EACH ROW
        EXECUTE FUNCTION documents_search_vector_update();
""")
```

And in `downgrade()`:
```python
op.execute("DROP TRIGGER IF EXISTS documents_search_vector_trigger ON documents;")
op.execute("DROP FUNCTION IF EXISTS documents_search_vector_update;")
```

**Step 6: Run migration against Docker Postgres**

```bash
docker compose up db -d
cd /Users/arhansalunke/redline-service/backend
alembic upgrade head
```

**Step 7: Commit**

```bash
git add -A
git commit -m "feat: database models, migrations, tsvector trigger"
```

---

## Task 3: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas.py`

**Step 1: Create `backend/app/schemas.py`**

```python
from __future__ import annotations
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


# --- Request schemas ---

class ChangeTarget(BaseModel):
    text: str
    occurrence: int | str | None = None  # None=first, 0/"all"=all, N=nth


class Change(BaseModel):
    operation: str = "replace"
    target: ChangeTarget
    replacement: str


class PatchDocumentRequest(BaseModel):
    changes: list[Change] = Field(..., min_length=1)


class CreateDocumentRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    content: str = ""


# --- Response schemas ---

class DocumentResponse(BaseModel):
    id: UUID
    title: str
    content: str
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PatchDocumentResponse(DocumentResponse):
    changes_applied: int


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int


class SearchResult(BaseModel):
    document_id: UUID
    title: str
    snippets: list[str]
    rank: float


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total: int
    limit: int
    offset: int


class ChangeHistoryEntry(BaseModel):
    id: UUID
    document_id: UUID
    changes: list[dict]
    created_at: datetime

    model_config = {"from_attributes": True}


class ChangeHistoryResponse(BaseModel):
    history: list[ChangeHistoryEntry]
    total: int


class ErrorResponse(BaseModel):
    error: str
    code: int
```

**Step 2: Commit**

```bash
git add backend/app/schemas.py
git commit -m "feat: pydantic request/response schemas"
```

---

## Task 4: Change Engine (TDD)

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/change_engine.py`
- Create: `backend/tests/test_change_engine.py`

**Step 1: Write failing tests for change engine**

Create `backend/tests/test_change_engine.py`:

```python
import pytest
from app.services.change_engine import apply_changes, ChangeError


def _change(text: str, replacement: str, occurrence=None):
    return {"target": {"text": text, "occurrence": occurrence}, "replacement": replacement}


class TestSingleReplace:
    def test_replace_first_occurrence(self):
        content = "the cat sat on the cat mat"
        result = apply_changes(content, [_change("cat", "dog")])
        assert result.content == "the dog sat on the cat mat"
        assert result.changes_applied == 1

    def test_replace_second_occurrence(self):
        content = "the cat sat on the cat mat"
        result = apply_changes(content, [_change("cat", "dog", occurrence=2)])
        assert result.content == "the cat sat on the dog mat"

    def test_replace_all_occurrences(self):
        content = "the cat sat on the cat mat"
        result = apply_changes(content, [_change("cat", "dog", occurrence="all")])
        assert result.content == "the dog sat on the dog mat"
        assert result.changes_applied == 1

    def test_replace_all_with_zero(self):
        content = "the cat sat on the cat mat"
        result = apply_changes(content, [_change("cat", "dog", occurrence=0)])
        assert result.content == "the dog sat on the dog mat"

    def test_target_not_found_raises(self):
        with pytest.raises(ChangeError, match="not found"):
            apply_changes("hello world", [_change("xyz", "abc")])

    def test_occurrence_out_of_range_raises(self):
        with pytest.raises(ChangeError, match="only 2 occurrences"):
            apply_changes("cat cat", [_change("cat", "dog", occurrence=5)])


class TestBulkReplace:
    def test_multiple_changes_applied_sequentially(self):
        content = "hello world foo bar"
        changes = [
            _change("hello", "hi"),
            _change("foo", "baz"),
        ]
        result = apply_changes(content, changes)
        assert result.content == "hi world baz bar"
        assert result.changes_applied == 2

    def test_replacement_text_is_target_of_next_change(self):
        content = "aaa bbb"
        changes = [
            _change("aaa", "bbb"),
            _change("bbb", "ccc", occurrence="all"),
        ]
        result = apply_changes(content, changes)
        assert result.content == "ccc ccc"

    def test_empty_replacement(self):
        content = "remove this word"
        result = apply_changes(content, [_change("this ", "")])
        assert result.content == "remove word"


class TestLargeFile:
    def test_10mb_document_100_changes(self):
        import time
        # Build a 10MB document
        word = "lorem ipsum dolor sit amet "
        repeats = (10 * 1024 * 1024) // len(word)
        content = word * repeats

        # Create 100 distinct changes
        changes = [_change(f"lorem", f"LOREM", occurrence=i + 1) for i in range(100)]

        start = time.perf_counter()
        result = apply_changes(content, changes)
        elapsed = time.perf_counter() - start

        assert result.changes_applied == 100
        assert elapsed < 5.0, f"Took {elapsed:.2f}s, expected < 5s"
```

**Step 2: Run tests to verify they fail**

```bash
cd /Users/arhansalunke/redline-service/backend
python -m pytest tests/test_change_engine.py -v
# Expected: ModuleNotFoundError or ImportError
```

**Step 3: Implement change engine**

Create `backend/app/services/__init__.py` (empty file).

Create `backend/app/services/change_engine.py`:

```python
from dataclasses import dataclass, field


class ChangeError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


@dataclass
class ChangeResult:
    content: str
    changes_applied: int
    summaries: list[str] = field(default_factory=list)


def _find_nth(text: str, target: str, n: int) -> int:
    """Find the nth occurrence of target in text (1-based). Returns -1 if not found."""
    start = 0
    for _ in range(n):
        pos = text.find(target, start)
        if pos == -1:
            return -1
        start = pos + 1
    return pos


def _count_occurrences(text: str, target: str) -> int:
    count = 0
    start = 0
    while True:
        pos = text.find(target, start)
        if pos == -1:
            return count
        count += 1
        start = pos + 1


def apply_changes(content: str, changes: list[dict]) -> ChangeResult:
    applied = 0
    summaries = []

    for change in changes:
        target_text = change["target"]["text"]
        replacement = change["replacement"]
        occurrence = change["target"].get("occurrence")

        # Replace all occurrences
        if occurrence == "all" or occurrence == 0:
            if target_text not in content:
                raise ChangeError(f"Target text '{target_text[:50]}' not found in document")
            content = content.replace(target_text, replacement)
            applied += 1
            summaries.append(f"Replaced all '{target_text[:30]}' with '{replacement[:30]}'")
            continue

        # Replace specific occurrence (default: first)
        n = occurrence if occurrence is not None else 1
        total = _count_occurrences(content, target_text)

        if total == 0:
            raise ChangeError(f"Target text '{target_text[:50]}' not found in document")
        if n > total:
            raise ChangeError(
                f"Target text '{target_text[:50]}' has only {total} occurrences, "
                f"but occurrence {n} was requested"
            )

        pos = _find_nth(content, target_text, n)
        content = content[:pos] + replacement + content[pos + len(target_text):]
        applied += 1
        summaries.append(f"Replaced occurrence {n} of '{target_text[:30]}' with '{replacement[:30]}'")

    return ChangeResult(content=content, changes_applied=applied, summaries=summaries)
```

**Step 4: Run tests to verify they pass**

```bash
cd /Users/arhansalunke/redline-service/backend
python -m pytest tests/test_change_engine.py -v
# Expected: all PASS
```

**Step 5: Commit**

```bash
git add backend/app/services/ backend/tests/test_change_engine.py
git commit -m "feat: change engine with bulk ops, occurrence targeting, large file support"
```

---

## Task 5: Document CRUD Router

**Files:**
- Create: `backend/app/routers/__init__.py`
- Create: `backend/app/routers/documents.py`
- Modify: `backend/app/main.py` (register router)

**Step 1: Create `backend/app/routers/documents.py`**

```python
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.database import get_db
from app.models import Document, ChangeHistory
from app.schemas import (
    CreateDocumentRequest, DocumentResponse, DocumentListResponse,
    PatchDocumentRequest, PatchDocumentResponse,
    ChangeHistoryEntry, ChangeHistoryResponse, ErrorResponse,
)
from app.services.change_engine import apply_changes, ChangeError

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("", response_model=DocumentResponse, status_code=201)
async def create_document(req: CreateDocumentRequest, db: AsyncSession = Depends(get_db)):
    doc = Document(title=req.title, content=req.content)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


@router.get("", response_model=DocumentListResponse)
async def list_documents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).order_by(Document.updated_at.desc()))
    docs = result.scalars().all()
    return DocumentListResponse(documents=docs, total=len(docs))


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: UUID, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail={"error": "Document not found", "code": 404})
    return doc


@router.patch("/{doc_id}", response_model=PatchDocumentResponse)
async def patch_document(doc_id: UUID, req: PatchDocumentRequest, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail={"error": "Document not found", "code": 404})

    changes_dicts = [c.model_dump() for c in req.changes]

    try:
        result = apply_changes(doc.content, changes_dicts)
    except ChangeError as e:
        raise HTTPException(status_code=400, detail={"error": e.message, "code": 400})

    # Save history
    history = ChangeHistory(
        document_id=doc.id,
        changes=changes_dicts,
        previous_content=doc.content,
    )
    db.add(history)

    # Update document
    doc.content = result.content
    doc.version += 1
    doc.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(doc)

    return PatchDocumentResponse(
        id=doc.id,
        title=doc.title,
        content=doc.content,
        version=doc.version,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        changes_applied=result.changes_applied,
    )


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: UUID, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail={"error": "Document not found", "code": 404})
    await db.delete(doc)
    await db.commit()


@router.get("/{doc_id}/history", response_model=ChangeHistoryResponse)
async def get_history(doc_id: UUID, limit: int = 20, offset: int = 0, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail={"error": "Document not found", "code": 404})

    count_result = await db.execute(
        select(func.count()).where(ChangeHistory.document_id == doc_id)
    )
    total = count_result.scalar()

    result = await db.execute(
        select(ChangeHistory)
        .where(ChangeHistory.document_id == doc_id)
        .order_by(ChangeHistory.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    history = result.scalars().all()

    return ChangeHistoryResponse(history=history, total=total)
```

**Step 2: Register router in `backend/app/main.py`**

Replace contents:

```python
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="Redline Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "code": 500},
    )


@app.get("/api/health")
async def health():
    return {"status": "ok"}


from app.routers.documents import router as documents_router  # noqa: E402
from app.routers.search import router as search_router  # noqa: E402

app.include_router(documents_router)
app.include_router(search_router)
```

**Step 3: Commit** (after search router is created in next task)

---

## Task 6: Search Router

**Files:**
- Create: `backend/app/routers/search.py`
- Create: `backend/app/services/search_service.py`

**Step 1: Create `backend/app/services/search_service.py`**

```python
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def search_documents(
    db: AsyncSession,
    query: str,
    limit: int = 10,
    offset: int = 0,
    document_id: UUID | None = None,
) -> tuple[list[dict], int]:
    """Full-text search using Postgres tsvector. Returns (results, total_count)."""

    where_clause = ""
    params = {"query": query, "limit": limit, "offset": offset}

    if document_id:
        where_clause = "AND d.id = :doc_id"
        params["doc_id"] = str(document_id)

    # Count query
    count_sql = text(f"""
        SELECT COUNT(*)
        FROM documents d
        WHERE d.search_vector @@ plainto_tsquery('english', :query)
        {where_clause}
    """)
    count_result = await db.execute(count_sql, params)
    total = count_result.scalar()

    # Search query with ranking and snippets
    search_sql = text(f"""
        SELECT
            d.id,
            d.title,
            ts_headline('english', d.content, plainto_tsquery('english', :query),
                'StartSel=<mark>, StopSel=</mark>, MaxWords=35, MinWords=15, MaxFragments=3'
            ) as snippet,
            ts_rank(d.search_vector, plainto_tsquery('english', :query)) as rank
        FROM documents d
        WHERE d.search_vector @@ plainto_tsquery('english', :query)
        {where_clause}
        ORDER BY rank DESC
        LIMIT :limit OFFSET :offset
    """)
    result = await db.execute(search_sql, params)
    rows = result.fetchall()

    results = [
        {
            "document_id": row.id,
            "title": row.title,
            "snippets": [row.snippet] if row.snippet else [],
            "rank": float(row.rank),
        }
        for row in rows
    ]

    return results, total
```

**Step 2: Create `backend/app/routers/search.py`**

```python
from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Document
from app.schemas import SearchResponse
from app.services.search_service import search_documents

router = APIRouter(prefix="/api/documents", tags=["search"])


@router.get("/search", response_model=SearchResponse)
async def search_all_documents(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    results, total = await search_documents(db, q, limit, offset)
    return SearchResponse(results=results, total=total, limit=limit, offset=offset)


@router.get("/{doc_id}/search", response_model=SearchResponse)
async def search_single_document(
    doc_id: UUID,
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail={"error": "Document not found", "code": 404})

    results, total = await search_documents(db, q, limit, offset, document_id=doc_id)
    return SearchResponse(results=results, total=total, limit=limit, offset=offset)
```

**Step 3: Commit**

```bash
git add backend/app/routers/ backend/app/services/search_service.py backend/app/main.py
git commit -m "feat: document CRUD, search, and history endpoints"
```

---

## Task 7: API Integration Tests

**Files:**
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_documents_api.py`
- Create: `backend/tests/test_search.py`

**Step 1: Create `backend/tests/conftest.py`**

```python
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.models import Base
from app.main import app
from app.database import get_db

TEST_DB_URL = "sqlite+aiosqlite:///./test.db"

engine = create_async_engine(TEST_DB_URL, echo=False)
TestSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSession() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
async def setup_db():
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
```

Note: SQLite doesn't support tsvector, so search tests need to run against real Postgres (via Docker). We'll mark search tests as needing Postgres and skip in unit test runs.

**Step 2: Create `backend/tests/test_documents_api.py`**

```python
import pytest


class TestCreateDocument:
    async def test_create_returns_201(self, client):
        resp = await client.post("/api/documents", json={"title": "Test Doc", "content": "Hello world"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Test Doc"
        assert data["content"] == "Hello world"
        assert data["version"] == 1
        assert "id" in data

    async def test_create_missing_title_returns_422(self, client):
        resp = await client.post("/api/documents", json={"content": "no title"})
        assert resp.status_code == 422


class TestListDocuments:
    async def test_list_empty(self, client):
        resp = await client.get("/api/documents")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    async def test_list_returns_created_docs(self, client):
        await client.post("/api/documents", json={"title": "Doc 1", "content": "a"})
        await client.post("/api/documents", json={"title": "Doc 2", "content": "b"})
        resp = await client.get("/api/documents")
        assert resp.json()["total"] == 2


class TestGetDocument:
    async def test_get_existing(self, client):
        create = await client.post("/api/documents", json={"title": "Test", "content": "body"})
        doc_id = create.json()["id"]
        resp = await client.get(f"/api/documents/{doc_id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Test"

    async def test_get_nonexistent_returns_404(self, client):
        resp = await client.get("/api/documents/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404


class TestPatchDocument:
    async def test_single_replace(self, client):
        create = await client.post("/api/documents", json={"title": "T", "content": "hello world"})
        doc_id = create.json()["id"]
        resp = await client.patch(f"/api/documents/{doc_id}", json={
            "changes": [{"operation": "replace", "target": {"text": "hello"}, "replacement": "hi"}]
        })
        assert resp.status_code == 200
        assert resp.json()["content"] == "hi world"
        assert resp.json()["version"] == 2
        assert resp.json()["changes_applied"] == 1

    async def test_bulk_replace(self, client):
        create = await client.post("/api/documents", json={"title": "T", "content": "foo bar baz"})
        doc_id = create.json()["id"]
        resp = await client.patch(f"/api/documents/{doc_id}", json={
            "changes": [
                {"operation": "replace", "target": {"text": "foo"}, "replacement": "FOO"},
                {"operation": "replace", "target": {"text": "baz"}, "replacement": "BAZ"},
            ]
        })
        assert resp.json()["content"] == "FOO bar BAZ"
        assert resp.json()["changes_applied"] == 2

    async def test_replace_nonexistent_text_returns_400(self, client):
        create = await client.post("/api/documents", json={"title": "T", "content": "hello"})
        doc_id = create.json()["id"]
        resp = await client.patch(f"/api/documents/{doc_id}", json={
            "changes": [{"operation": "replace", "target": {"text": "xyz"}, "replacement": "abc"}]
        })
        assert resp.status_code == 400


class TestDeleteDocument:
    async def test_delete_existing(self, client):
        create = await client.post("/api/documents", json={"title": "T", "content": "c"})
        doc_id = create.json()["id"]
        resp = await client.delete(f"/api/documents/{doc_id}")
        assert resp.status_code == 204
        get_resp = await client.get(f"/api/documents/{doc_id}")
        assert get_resp.status_code == 404


class TestHistory:
    async def test_history_after_patch(self, client):
        create = await client.post("/api/documents", json={"title": "T", "content": "hello world"})
        doc_id = create.json()["id"]
        await client.patch(f"/api/documents/{doc_id}", json={
            "changes": [{"operation": "replace", "target": {"text": "hello"}, "replacement": "hi"}]
        })
        resp = await client.get(f"/api/documents/{doc_id}/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["history"][0]["changes"][0]["target"]["text"] == "hello"
```

**Step 3: Run tests**

```bash
cd /Users/arhansalunke/redline-service/backend
python -m pytest tests/test_documents_api.py tests/test_change_engine.py -v
# Expected: all PASS
```

**Step 4: Commit**

```bash
git add backend/tests/
git commit -m "test: unit and integration tests for change engine and document API"
```

---

## Task 8: Seed Data Script

**Files:**
- Create: `backend/app/seed.py`
- Modify: `backend/app/main.py` (add startup event)

**Step 1: Create `backend/app/seed.py`**

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Document

SEED_DOCUMENTS = [
    {
        "title": "Software License Agreement",
        "content": """SOFTWARE LICENSE AGREEMENT

This Software License Agreement ("Agreement") is entered into as of January 1, 2026, by and between TechCorp Inc., a Delaware corporation ("Licensor"), and the end user ("Licensee").

1. GRANT OF LICENSE
Licensor hereby grants to Licensee a non-exclusive, non-transferable, limited license to use the software product described herein ("Software") solely for Licensee's internal business purposes, subject to the terms and conditions of this Agreement.

2. RESTRICTIONS
Licensee shall not: (a) copy or duplicate the Software; (b) decompile, disassemble, or reverse engineer the Software; (c) sell, assign, or sublicense the Software to any third party; (d) modify or create derivative works based on the Software.

3. TERM AND TERMINATION
This Agreement is effective until terminated. Licensor may terminate this Agreement immediately upon written notice if Licensee breaches any provision of this Agreement. Upon termination, Licensee shall destroy all copies of the Software.

4. WARRANTY DISCLAIMER
THE SOFTWARE IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NONINFRINGEMENT.

5. LIMITATION OF LIABILITY
IN NO EVENT SHALL LICENSOR BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES ARISING OUT OF OR IN CONNECTION WITH THIS AGREEMENT.

6. GOVERNING LAW
This Agreement shall be governed by and construed in accordance with the laws of the State of Delaware, without regard to its conflict of laws principles.""",
    },
    {
        "title": "Terms of Service",
        "content": """TERMS OF SERVICE

Last Updated: March 15, 2026

Welcome to Redline Service. By accessing or using our service, you agree to be bound by these Terms of Service ("Terms").

1. ACCEPTANCE OF TERMS
By creating an account or using the Service, you acknowledge that you have read, understood, and agree to be bound by these Terms. If you do not agree, you may not use the Service.

2. DESCRIPTION OF SERVICE
Redline Service provides a document editing and collaboration platform that allows users to make tracked changes, search across documents, and maintain version history. The Service is provided on an "as available" basis.

3. USER ACCOUNTS
You are responsible for maintaining the confidentiality of your account credentials. You agree to notify us immediately of any unauthorized use of your account. We reserve the right to suspend or terminate accounts that violate these Terms.

4. ACCEPTABLE USE
You agree not to: (a) upload malicious content; (b) attempt to gain unauthorized access to our systems; (c) use the Service for any illegal purpose; (d) interfere with the proper functioning of the Service.

5. INTELLECTUAL PROPERTY
All content you create using the Service remains your property. However, you grant us a limited license to store, process, and display your content as necessary to provide the Service.

6. PRIVACY
Your use of the Service is also governed by our Privacy Policy, which is incorporated into these Terms by reference.

7. MODIFICATIONS
We reserve the right to modify these Terms at any time. Continued use of the Service after modifications constitutes acceptance of the updated Terms.""",
    },
    {
        "title": "Project Kickoff Memo",
        "content": """INTERNAL MEMO

TO: Engineering Team
FROM: Project Lead
DATE: March 15, 2026
RE: Q2 Platform Migration Kickoff

Team,

I'm writing to formally kick off our Q2 platform migration project. This memo outlines the key objectives, timeline, and responsibilities.

BACKGROUND
Our current infrastructure has served us well for the past three years, but we've reached a point where scaling challenges and maintenance costs require us to modernize. The migration will move us from our monolithic architecture to a microservices-based platform.

KEY OBJECTIVES
1. Decompose the monolith into 5 core microservices
2. Migrate from MySQL to PostgreSQL for improved performance
3. Implement containerized deployments using Docker and Kubernetes
4. Achieve zero-downtime deployments
5. Reduce infrastructure costs by 30%

TIMELINE
- Phase 1 (April): Service decomposition and API design
- Phase 2 (May): Core service implementation and testing
- Phase 3 (June): Data migration and integration testing
- Phase 4 (July): Staged rollout and monitoring

TEAM ASSIGNMENTS
Backend: Alice, Bob, and Charlie will lead service decomposition
Frontend: Diana and Eve will handle API integration
DevOps: Frank will manage infrastructure and CI/CD pipeline
QA: Grace will coordinate testing across all phases

Please review this memo and come prepared to discuss at our kickoff meeting on Monday.

Best regards,
Project Lead""",
    },
]


async def seed_documents(db: AsyncSession):
    """Seed the database with sample documents if empty."""
    result = await db.execute(select(Document).limit(1))
    if result.scalar():
        return  # Already seeded

    for doc_data in SEED_DOCUMENTS:
        doc = Document(**doc_data)
        db.add(doc)

    await db.commit()
```

**Step 2: Add startup event to `backend/app/main.py`**

Add after the router includes:

```python
from contextlib import asynccontextmanager
from app.database import async_session
from app.seed import seed_documents


@asynccontextmanager
async def lifespan(app_instance):
    async with async_session() as db:
        await seed_documents(db)
    yield

# Replace the app creation to use lifespan:
# app = FastAPI(title="Redline Service", version="0.1.0", lifespan=lifespan)
```

(Move the lifespan to before `app = FastAPI(...)` and pass it to the constructor.)

**Step 3: Commit**

```bash
git add backend/app/seed.py backend/app/main.py
git commit -m "feat: seed data with 3 sample documents"
```

---

## Task 9: Frontend Setup

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/vite.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/src/main.jsx`
- Create: `frontend/src/App.jsx`
- Create: `frontend/src/index.css`
- Create: `frontend/src/api/client.js`
- Create: `frontend/Dockerfile`

**Step 1: Scaffold React + Vite + Tailwind**

```bash
cd /Users/arhansalunke/redline-service
npm create vite@latest frontend -- --template react
cd frontend
npm install
npm install -D tailwindcss @tailwindcss/vite
npm install diff-match-patch react-diff-viewer-continued
```

**Step 2: Configure Vite proxy**

Create/update `frontend/vite.config.js`:

```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

**Step 3: Set up Tailwind**

Update `frontend/src/index.css`:

```css
@import "tailwindcss";
```

**Step 4: Create API client**

Create `frontend/src/api/client.js`:

```js
const BASE = '/api';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: 'Request failed', code: res.status }));
    throw new Error(err.error || err.detail || 'Request failed');
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  listDocuments: () => request('/documents'),
  getDocument: (id) => request(`/documents/${id}`),
  createDocument: (data) => request('/documents', { method: 'POST', body: JSON.stringify(data) }),
  patchDocument: (id, changes) => request(`/documents/${id}`, { method: 'PATCH', body: JSON.stringify({ changes }) }),
  deleteDocument: (id) => request(`/documents/${id}`, { method: 'DELETE' }),
  searchDocuments: (q, limit = 10, offset = 0) => request(`/documents/search?q=${encodeURIComponent(q)}&limit=${limit}&offset=${offset}`),
  getHistory: (id) => request(`/documents/${id}/history`),
};
```

**Step 5: Create frontend Dockerfile**

```dockerfile
FROM node:22-alpine

WORKDIR /app

COPY package*.json .
RUN npm install

COPY . .

CMD ["npm", "run", "dev"]
```

**Step 6: Update `docker-compose.yml`** to add frontend service:

```yaml
  frontend:
    build: ./frontend
    ports:
      - "5173:5173"
    environment:
      - VITE_API_URL=http://backend:8000
    depends_on:
      - backend
    volumes:
      - ./frontend:/app
      - /app/node_modules
```

**Step 7: Commit**

```bash
git add frontend/ docker-compose.yml
git commit -m "feat: frontend scaffolding with React, Vite, Tailwind, API client"
```

---

## Task 10: Frontend Components

**Files:**
- Create: `frontend/src/App.jsx`
- Create: `frontend/src/components/DocumentList.jsx`
- Create: `frontend/src/components/SearchBar.jsx`
- Create: `frontend/src/components/DiffEditor.jsx`
- Create: `frontend/src/components/ChangeHistory.jsx`

**Step 1: Create `frontend/src/components/DocumentList.jsx`**

```jsx
import { useState } from 'react';
import { api } from '../api/client';

export default function DocumentList({ documents, selected, onSelect, onRefresh }) {
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState('');

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!title.trim()) return;
    await api.createDocument({ title: title.trim(), content: '' });
    setTitle('');
    setShowCreate(false);
    onRefresh();
  };

  return (
    <div className="flex flex-col h-full">
      <div className="p-3 border-b border-gray-200 dark:border-gray-700">
        <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">Documents</h2>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="w-full text-sm bg-blue-600 hover:bg-blue-700 text-white rounded px-3 py-1.5 transition-colors"
        >
          + New Document
        </button>
        {showCreate && (
          <form onSubmit={handleCreate} className="mt-2 flex gap-1">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Title..."
              className="flex-1 text-sm border border-gray-300 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-800 dark:text-white"
              autoFocus
            />
            <button type="submit" className="text-sm bg-green-600 text-white rounded px-2 py-1">Go</button>
          </form>
        )}
      </div>
      <div className="flex-1 overflow-y-auto">
        {documents.map((doc) => (
          <button
            key={doc.id}
            onClick={() => onSelect(doc.id)}
            className={`w-full text-left px-3 py-2.5 border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors ${
              selected === doc.id ? 'bg-blue-50 dark:bg-blue-900/30 border-l-2 border-l-blue-600' : ''
            }`}
          >
            <div className="text-sm font-medium truncate dark:text-white">{doc.title}</div>
            <div className="text-xs text-gray-400 mt-0.5">v{doc.version} &middot; {new Date(doc.updated_at).toLocaleDateString()}</div>
          </button>
        ))}
        {documents.length === 0 && (
          <div className="p-4 text-sm text-gray-400 text-center">No documents yet</div>
        )}
      </div>
    </div>
  );
}
```

**Step 2: Create `frontend/src/components/SearchBar.jsx`**

```jsx
import { useState } from 'react';
import { api } from '../api/client';

export default function SearchBar({ onSelectDocument }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    try {
      const data = await api.searchDocuments(query.trim());
      setResults(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="border-b border-gray-200 dark:border-gray-700">
      <form onSubmit={handleSearch} className="p-3">
        <div className="flex gap-1">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search documents..."
            className="flex-1 text-sm border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 bg-white dark:bg-gray-800 dark:text-white"
          />
          <button
            type="submit"
            disabled={loading}
            className="text-sm bg-gray-600 hover:bg-gray-700 text-white rounded px-3 py-1.5 disabled:opacity-50"
          >
            {loading ? '...' : 'Search'}
          </button>
        </div>
      </form>
      {results && (
        <div className="px-3 pb-3">
          <div className="text-xs text-gray-400 mb-1">{results.total} result{results.total !== 1 ? 's' : ''}</div>
          {results.results.map((r) => (
            <button
              key={r.document_id}
              onClick={() => {
                onSelectDocument(r.document_id);
                setResults(null);
                setQuery('');
              }}
              className="w-full text-left p-2 rounded hover:bg-gray-50 dark:hover:bg-gray-700 mb-1 border border-gray-100 dark:border-gray-700"
            >
              <div className="text-sm font-medium dark:text-white">{r.title}</div>
              <div
                className="text-xs text-gray-500 mt-1 line-clamp-2"
                dangerouslySetInnerHTML={{ __html: r.snippets.join(' ... ') }}
              />
            </button>
          ))}
          {results.results.length === 0 && (
            <div className="text-xs text-gray-400">No matches found</div>
          )}
        </div>
      )}
    </div>
  );
}
```

**Step 3: Create `frontend/src/components/DiffEditor.jsx`**

```jsx
import { useState, useEffect, useMemo } from 'react';
import DiffViewer from 'react-diff-viewer-continued';
import DiffMatchPatch from 'diff-match-patch';
import { api } from '../api/client';

const dmp = new DiffMatchPatch();

function diffsToChanges(oldText, newText) {
  const diffs = dmp.diff_main(oldText, newText);
  dmp.diff_cleanupSemantic(diffs);

  const changes = [];
  let pos = 0;

  for (const [op, text] of diffs) {
    if (op === 0) {
      pos += text.length;
    } else if (op === -1) {
      // Look ahead for insertion (replacement)
      const nextDiff = diffs[diffs.indexOf([op, text]) + 1];
      // We'll use a simpler approach: find removed text and its replacement
      changes.push({
        operation: 'replace',
        target: { text },
        replacement: '',
        _pos: pos,
      });
      pos += text.length;
    } else if (op === 1) {
      // Insertion — check if previous change at same position can be merged
      const lastChange = changes[changes.length - 1];
      if (lastChange && lastChange._pos + lastChange.target.text.length === pos && lastChange.replacement === '') {
        lastChange.replacement = text;
      } else {
        // Pure insertion — we model as replacing empty string (need context)
        // For the API, we'll send position-aware changes
        changes.push({
          operation: 'replace',
          target: { text: '' },
          replacement: text,
          _pos: pos,
        });
      }
    }
  }

  // Clean: remove _pos, filter out no-ops
  return changes
    .filter(c => c.target.text !== '' || c.replacement !== '')
    .map(({ _pos, ...c }) => c);
}

// Better approach: compute line-level changes for the API
function computeChanges(oldText, newText) {
  if (oldText === newText) return [];

  const diffs = dmp.diff_main(oldText, newText);
  dmp.diff_cleanupSemantic(diffs);

  const changes = [];
  let i = 0;

  while (i < diffs.length) {
    const [op, text] = diffs[i];
    if (op === -1) {
      // Deletion or replacement
      let replacement = '';
      if (i + 1 < diffs.length && diffs[i + 1][0] === 1) {
        replacement = diffs[i + 1][1];
        i++;
      }
      changes.push({
        operation: 'replace',
        target: { text, occurrence: 1 },
        replacement,
      });
    } else if (op === 1 && changes.length === 0) {
      // Pure insertion at start — not easily handled by find/replace
      // We'll skip pure insertions for now; user can type them in
    }
    i++;
  }

  return changes;
}

export default function DiffEditor({ document, onUpdate }) {
  const [editedContent, setEditedContent] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (document) {
      setEditedContent(document.content);
      setError(null);
    }
  }, [document?.id, document?.version]);

  const hasChanges = document && editedContent !== document.content;

  const handleSubmit = async () => {
    if (!hasChanges) return;
    setSubmitting(true);
    setError(null);

    const changes = computeChanges(document.content, editedContent);
    if (changes.length === 0) {
      setError('No replaceable changes detected. Try modifying existing text.');
      setSubmitting(false);
      return;
    }

    try {
      const updated = await api.patchDocument(document.id, changes);
      onUpdate(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  if (!document) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        <div className="text-center">
          <div className="text-4xl mb-2">📄</div>
          <div>Select a document to start editing</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
        <div>
          <h1 className="text-lg font-semibold dark:text-white">{document.title}</h1>
          <span className="text-xs text-gray-400">Version {document.version}</span>
        </div>
        <div className="flex items-center gap-2">
          {error && <span className="text-xs text-red-500">{error}</span>}
          {hasChanges && (
            <button
              onClick={() => setEditedContent(document.content)}
              className="text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 px-2 py-1"
            >
              Discard
            </button>
          )}
          <button
            onClick={handleSubmit}
            disabled={!hasChanges || submitting}
            className="text-sm bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white rounded px-4 py-1.5 transition-colors"
          >
            {submitting ? 'Saving...' : 'Submit Changes'}
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-auto">
        <div className="grid grid-cols-2 h-full">
          <div className="border-r border-gray-200 dark:border-gray-700 flex flex-col">
            <div className="px-3 py-1.5 bg-red-50 dark:bg-red-900/20 text-xs font-medium text-red-600 dark:text-red-400 border-b border-gray-200 dark:border-gray-700">
              Original (v{document.version})
            </div>
            <div className="flex-1 overflow-auto p-4">
              <pre className="text-sm whitespace-pre-wrap font-mono text-gray-700 dark:text-gray-300 leading-relaxed">{document.content}</pre>
            </div>
          </div>
          <div className="flex flex-col">
            <div className="px-3 py-1.5 bg-green-50 dark:bg-green-900/20 text-xs font-medium text-green-600 dark:text-green-400 border-b border-gray-200 dark:border-gray-700">
              Edited
            </div>
            <textarea
              value={editedContent}
              onChange={(e) => setEditedContent(e.target.value)}
              className="flex-1 p-4 text-sm font-mono resize-none border-0 outline-none bg-transparent dark:text-white leading-relaxed"
              spellCheck={false}
            />
          </div>
        </div>
      </div>
      {hasChanges && (
        <div className="border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 max-h-64 overflow-auto">
          <div className="px-3 py-1.5 text-xs font-medium text-gray-500 border-b border-gray-100 dark:border-gray-700">
            Diff Preview
          </div>
          <DiffViewer
            oldValue={document.content}
            newValue={editedContent}
            splitView={false}
            useDarkTheme={window.matchMedia('(prefers-color-scheme: dark)').matches}
            hideLineNumbers
            styles={{
              contentText: { fontSize: '12px', lineHeight: '1.6' },
            }}
          />
        </div>
      )}
    </div>
  );
}
```

**Step 4: Create `frontend/src/components/ChangeHistory.jsx`**

```jsx
import { useState, useEffect } from 'react';
import { api } from '../api/client';

export default function ChangeHistory({ documentId }) {
  const [history, setHistory] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!documentId) {
      setHistory([]);
      return;
    }
    setLoading(true);
    api.getHistory(documentId)
      .then((data) => {
        setHistory(data.history);
        setTotal(data.total);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [documentId]);

  if (!documentId) return null;

  const summarize = (changes) => {
    return changes.map((c) => {
      const target = c.target?.text || '';
      const replacement = c.replacement || '';
      const tShort = target.length > 25 ? target.slice(0, 25) + '...' : target;
      const rShort = replacement.length > 25 ? replacement.slice(0, 25) + '...' : replacement;
      if (!replacement) return `Removed "${tShort}"`;
      if (!target) return `Inserted "${rShort}"`;
      return `"${tShort}" → "${rShort}"`;
    });
  };

  return (
    <div className="h-full flex flex-col">
      <div className="px-3 py-2 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
        <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
          Change History ({total})
        </h3>
      </div>
      <div className="flex-1 overflow-y-auto">
        {loading && <div className="p-3 text-xs text-gray-400">Loading...</div>}
        {!loading && history.length === 0 && (
          <div className="p-3 text-xs text-gray-400 text-center">No changes yet</div>
        )}
        {history.map((entry) => (
          <div key={entry.id} className="px-3 py-2 border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800">
            <div className="text-xs text-gray-400 mb-1">
              {new Date(entry.created_at).toLocaleString()}
            </div>
            {summarize(entry.changes).map((s, i) => (
              <div key={i} className="text-xs text-gray-600 dark:text-gray-300 font-mono">{s}</div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
```

**Step 5: Create `frontend/src/App.jsx`**

```jsx
import { useState, useEffect, useCallback } from 'react';
import DocumentList from './components/DocumentList';
import SearchBar from './components/SearchBar';
import DiffEditor from './components/DiffEditor';
import ChangeHistory from './components/ChangeHistory';
import { api } from './api/client';

export default function App() {
  const [documents, setDocuments] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [historyKey, setHistoryKey] = useState(0);

  const loadDocuments = useCallback(async () => {
    try {
      const data = await api.listDocuments();
      setDocuments(data.documents);
    } catch (err) {
      console.error('Failed to load documents:', err);
    }
  }, []);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  useEffect(() => {
    if (!selectedId) {
      setSelectedDoc(null);
      return;
    }
    api.getDocument(selectedId)
      .then(setSelectedDoc)
      .catch(console.error);
  }, [selectedId]);

  const handleUpdate = (updatedDoc) => {
    setSelectedDoc(updatedDoc);
    setHistoryKey((k) => k + 1);
    loadDocuments();
  };

  return (
    <div className="h-screen flex bg-white dark:bg-gray-900">
      {/* Sidebar */}
      <div className="w-72 border-r border-gray-200 dark:border-gray-700 flex flex-col bg-gray-50 dark:bg-gray-800 shrink-0">
        <SearchBar onSelectDocument={setSelectedId} />
        <DocumentList
          documents={documents}
          selected={selectedId}
          onSelect={setSelectedId}
          onRefresh={loadDocuments}
        />
      </div>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex-1 min-h-0">
          <DiffEditor document={selectedDoc} onUpdate={handleUpdate} />
        </div>
        {selectedId && (
          <div className="h-48 border-t border-gray-200 dark:border-gray-700 shrink-0">
            <ChangeHistory key={historyKey} documentId={selectedId} />
          </div>
        )}
      </div>
    </div>
  );
}
```

**Step 6: Update `frontend/src/main.jsx`**

```jsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

**Step 7: Verify frontend builds**

```bash
cd /Users/arhansalunke/redline-service/frontend
npm run build
# Expected: build succeeds
```

**Step 8: Commit**

```bash
git add frontend/
git commit -m "feat: frontend with side-by-side editor, search, change history"
```

---

## Task 11: Sample Requests + README

**Files:**
- Create: `sample-requests/requests.sh`
- Create: `README.md`

**Step 1: Create `sample-requests/requests.sh`**

```bash
#!/bin/bash
# Redline Service — Sample API Requests
# Assumes the service is running at http://localhost:8000

BASE="http://localhost:8000/api"

echo "=== Create Document ==="
DOC=$(curl -s -X POST "$BASE/documents" \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Contract", "content": "This agreement is between Party A and Party B. Party A shall deliver the goods to Party B within 30 days."}')
echo "$DOC" | python3 -m json.tool
DOC_ID=$(echo "$DOC" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo -e "\n=== List Documents ==="
curl -s "$BASE/documents" | python3 -m json.tool

echo -e "\n=== Get Document ==="
curl -s "$BASE/documents/$DOC_ID" | python3 -m json.tool

echo -e "\n=== Patch Document (single change) ==="
curl -s -X PATCH "$BASE/documents/$DOC_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "changes": [
      {"operation": "replace", "target": {"text": "30 days"}, "replacement": "15 business days"}
    ]
  }' | python3 -m json.tool

echo -e "\n=== Patch Document (bulk changes) ==="
curl -s -X PATCH "$BASE/documents/$DOC_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "changes": [
      {"operation": "replace", "target": {"text": "Party A"}, "replacement": "Seller"},
      {"operation": "replace", "target": {"text": "Party B"}, "replacement": "Buyer"}
    ]
  }' | python3 -m json.tool

echo -e "\n=== Search Documents ==="
curl -s "$BASE/documents/search?q=agreement&limit=5" | python3 -m json.tool

echo -e "\n=== Get Change History ==="
curl -s "$BASE/documents/$DOC_ID/history" | python3 -m json.tool

echo -e "\n=== Search Within Document ==="
curl -s "$BASE/documents/$DOC_ID/search?q=Seller" | python3 -m json.tool
```

**Step 2: Create `README.md`**

```markdown
# Redline Service

A document redlining service with side-by-side editing, full-text search, bulk operations, and change history tracking.

## Quick Start

```bash
docker compose up --build
```

- **Frontend:** http://localhost:5173
- **API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs

Three sample documents are loaded on startup.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.13, FastAPI, SQLAlchemy (async) |
| Database | PostgreSQL 16 with full-text search (tsvector) |
| Frontend | React 18, Vite, TailwindCSS |
| Diff Engine | diff-match-patch, react-diff-viewer |
| Testing | pytest, httpx, pytest-asyncio |
| Infrastructure | Docker Compose, Railway |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/documents` | Create a document |
| `GET` | `/api/documents` | List all documents |
| `GET` | `/api/documents/{id}` | Get a single document |
| `PATCH` | `/api/documents/{id}` | Apply text changes (supports bulk) |
| `DELETE` | `/api/documents/{id}` | Delete a document |
| `GET` | `/api/documents/search?q=term` | Full-text search across all documents |
| `GET` | `/api/documents/{id}/search?q=term` | Search within a single document |
| `GET` | `/api/documents/{id}/history` | Get change history for a document |

### Example: Apply Changes

```bash
curl -X PATCH http://localhost:8000/api/documents/{id} \
  -H "Content-Type: application/json" \
  -d '{
    "changes": [
      {
        "operation": "replace",
        "target": { "text": "old text", "occurrence": 1 },
        "replacement": "new text"
      },
      {
        "operation": "replace",
        "target": { "text": "another phrase", "occurrence": "all" },
        "replacement": "updated phrase"
      }
    ]
  }'
```

### Change Targeting

- **First occurrence (default):** `"occurrence": 1` or omit
- **Specific occurrence:** `"occurrence": 3` (3rd match)
- **All occurrences:** `"occurrence": "all"` or `"occurrence": 0`

### Error Responses

All errors follow a consistent format:
```json
{ "error": "Target text 'xyz' not found in document", "code": 400 }
```

## Architecture

```
React (Vite:5173) → FastAPI (:8000) → PostgreSQL (:5432)
                         ├── Change Engine (str.find, O(n))
                         └── Search Service (tsvector + GIN index)
```

### Change Engine

The change engine processes replacements sequentially using `str.find()` with offset tracking — O(n) per change, no regex. This handles 10MB+ documents with 100 changes in under 5 seconds.

For bulk operations, changes are applied in order. Each replacement adjusts the content, and subsequent changes operate on the updated text.

### Search

Full-text search uses PostgreSQL's built-in `tsvector`/`tsquery` with a GIN index. The `search_vector` column is auto-updated via a database trigger on every INSERT or UPDATE of the document content.

**Trade-offs:**
- Postgres FTS is excellent for English prose and requires zero additional infrastructure
- Limited fuzzy/typo-tolerant matching — production would add Elasticsearch
- Indexing happens at write time, keeping read queries fast

### Performance

- Documents are stored as TEXT in Postgres — no size limit in practice
- The change engine avoids regex entirely for predictable linear-time performance
- Async SQLAlchemy with asyncpg for non-blocking database access
- Benchmark test verifies 10MB document with 100 changes completes in < 5s

## Running Tests

```bash
cd backend
pip install -e ".[dev]"
python -m pytest tests/ -v
```

## Sample Requests

```bash
chmod +x sample-requests/requests.sh
./sample-requests/requests.sh
```

## Project Structure

```
redline-service/
├── docker-compose.yml
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app + middleware
│   │   ├── config.py            # Settings
│   │   ├── database.py          # Async SQLAlchemy engine
│   │   ├── models.py            # Document + ChangeHistory models
│   │   ├── schemas.py           # Pydantic request/response schemas
│   │   ├── seed.py              # Sample document seeder
│   │   ├── routers/
│   │   │   ├── documents.py     # CRUD + PATCH + history endpoints
│   │   │   └── search.py        # Full-text search endpoints
│   │   └── services/
│   │       ├── change_engine.py # Core text replacement logic
│   │       └── search_service.py# Postgres FTS query builder
│   └── tests/
│       ├── test_change_engine.py # Unit tests for replacement logic
│       ├── test_documents_api.py # API integration tests
│       └── test_performance.py   # Large file benchmarks
└── frontend/
    └── src/
        ├── App.jsx               # Main layout
        ├── api/client.js         # API helper
        └── components/
            ├── DocumentList.jsx  # Sidebar document list
            ├── SearchBar.jsx     # Search with snippets
            ├── DiffEditor.jsx    # Side-by-side editor
            └── ChangeHistory.jsx # Change timeline
```
```

**Step 3: Commit**

```bash
git add README.md sample-requests/
git commit -m "docs: README with API docs, sample curl requests"
```

---

## Task 12: Railway Deployment Config

**Files:**
- Create: `backend/Procfile` (or use Railway nixpacks)
- Modify: `backend/app/config.py` (accept DATABASE_URL from Railway)
- Modify: `backend/app/main.py` (run migrations on startup)
- Modify: `frontend/vite.config.js` (production API URL)
- Create: `frontend/nginx.conf` (for production serving)
- Modify: `frontend/Dockerfile` (production build)

**Step 1: Update `backend/app/config.py`** for Railway

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/redline"

    model_config = {"env_prefix": "REDLINE_"}


settings = Settings()
```

Railway sets `DATABASE_URL` — we'll map it to `REDLINE_DATABASE_URL` in Railway's env vars, or add a fallback:

```python
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/redline"
    ).replace("postgresql://", "postgresql+asyncpg://")

    model_config = {"env_prefix": "REDLINE_"}


settings = Settings()
```

**Step 2: Update `backend/app/main.py`** — run migrations on startup

In the lifespan function, before seeding, add:

```python
from app.models import Base
from app.database import engine

async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)
```

This ensures tables exist even without running Alembic manually (fine for this prototype).

**Step 3: Update `frontend/Dockerfile`** for production

```dockerfile
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json .
RUN npm install
COPY . .
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

**Step 4: Create `frontend/nginx.conf`**

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass ${BACKEND_URL};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**Step 5: Update `frontend/src/api/client.js`** for production URL

```js
const BASE = import.meta.env.VITE_API_URL || '/api';
// ... rest stays the same, but prepend BASE differently:
```

Actually, keep it as `/api` — the nginx proxy handles it in production, and Vite proxy handles it in dev. No change needed.

**Step 6: Commit**

```bash
git add -A
git commit -m "feat: Railway deployment config with nginx, auto-migration"
```

---

## Task 13: Final Polish + End-to-End Verification

**Step 1: Run `docker compose up --build` and verify:**
- Frontend loads at http://localhost:5173
- Three seed documents visible in sidebar
- Click a document → side-by-side editor loads
- Edit text on right → diff preview shows
- Click "Submit Changes" → changes applied, history updates
- Search for a term → results with highlighted snippets appear
- Click search result → loads document

**Step 2: Run all backend tests**

```bash
cd /Users/arhansalunke/redline-service/backend
python -m pytest tests/ -v
```

**Step 3: Final commit**

```bash
git add -A
git commit -m "chore: final polish and verification"
```

**Step 4: Push to GitHub**

```bash
git remote add origin <github-url>
git push -u origin main
```

**Step 5: Deploy to Railway**

1. Connect GitHub repo in Railway dashboard
2. Add Postgres plugin
3. Set `REDLINE_DATABASE_URL` env var from Postgres plugin
4. Deploy backend service (from `./backend`)
5. Deploy frontend service (from `./frontend`, set `BACKEND_URL` env var)
6. Verify live URL works
