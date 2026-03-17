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
