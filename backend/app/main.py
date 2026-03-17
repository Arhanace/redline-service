from contextlib import asynccontextmanager
from pathlib import Path

import sqlalchemy as sa
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.database import async_session, engine
from app.models import Base
from app.routers.documents import router as documents_router
from app.routers.search import router as search_router
from app.seed import seed_documents

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


SEARCH_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION documents_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('english', COALESCE(NEW.title, '') || ' ' || COALESCE(NEW.content, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""

SEARCH_TRIGGER_SQL = """
DO $$ BEGIN
    CREATE TRIGGER documents_search_vector_trigger
        BEFORE INSERT OR UPDATE OF title, content ON documents
        FOR EACH ROW
        EXECUTE FUNCTION documents_search_vector_update();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$
"""

BACKFILL_SEARCH_SQL = """
UPDATE documents SET search_vector = to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(content, ''))
WHERE search_vector IS NULL
"""

FIX_CASCADE_SQL = """
DO $$ BEGIN
    ALTER TABLE change_history DROP CONSTRAINT IF EXISTS change_history_document_id_fkey;
    ALTER TABLE change_history ADD CONSTRAINT change_history_document_id_fkey
        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE;
EXCEPTION WHEN OTHERS THEN NULL;
END $$
"""

ADD_RESULTING_CONTENT_SQL = """
DO $$ BEGIN
    ALTER TABLE change_history ADD COLUMN resulting_content TEXT NOT NULL DEFAULT '';
EXCEPTION WHEN duplicate_column THEN NULL;
END $$
"""

RESET_HISTORY_SQL = """
DELETE FROM change_history
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (for dev/Railway — production would use Alembic)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(sa.text(SEARCH_FUNCTION_SQL))
        await conn.execute(sa.text(SEARCH_TRIGGER_SQL))
        await conn.execute(sa.text(FIX_CASCADE_SQL))
        await conn.execute(sa.text(ADD_RESULTING_CONTENT_SQL))
    async with async_session() as db:
        await seed_documents(db)
    # Backfill search vectors for any existing rows missing them
    async with engine.begin() as conn:
        await conn.execute(sa.text(BACKFILL_SEARCH_SQL))
    yield


app = FastAPI(title="Redline Service", version="0.1.0", lifespan=lifespan)

app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_origin_regex=r"https://.*\.up\.railway\.app",
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


app.include_router(search_router)
app.include_router(documents_router)

# Serve frontend static files in production (when built frontend exists)
if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the SPA — any non-API route returns index.html."""
        file_path = STATIC_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")
