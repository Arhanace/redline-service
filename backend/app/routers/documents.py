from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.database import get_db
from app.models import Document, ChangeHistory
from app.schemas import (
    CreateDocumentRequest, DocumentResponse, DocumentListResponse,
    PatchDocumentRequest, PatchDocumentResponse,
    ChangeHistoryEntry, ChangeHistoryDetailEntry, ChangeHistoryResponse,
)
from app.services.change_engine import apply_changes, ChangeError
from app.services.file_parser import extract_text

router = APIRouter(prefix="/api/documents", tags=["documents"])

MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB


@router.post("", response_model=DocumentResponse, status_code=201)
async def create_document(req: CreateDocumentRequest, db: AsyncSession = Depends(get_db)):
    doc = Document(title=req.title, content=req.content)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


@router.post("/upload", response_model=DocumentResponse, status_code=201)
async def upload_document(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    if not file.filename:
        raise HTTPException(status_code=400, detail={"error": "No filename provided", "code": 400})

    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail={"error": "File too large (max 20MB)", "code": 400})

    # Run extraction in a thread to not block the event loop
    import asyncio
    loop = asyncio.get_event_loop()
    try:
        content = await loop.run_in_executor(None, extract_text, file.filename, file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e), "code": 400})

    title = file.filename.rsplit(".", 1)[0] if "." in file.filename else file.filename

    doc = Document(title=title, content=content)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


@router.get("", response_model=DocumentListResponse)
async def list_documents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            Document.id, Document.title, Document.version,
            func.length(Document.content).label("content_length"),
            Document.created_at, Document.updated_at,
        ).order_by(Document.updated_at.desc())
    )
    docs = result.all()
    return DocumentListResponse(documents=docs, total=len(docs))


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: UUID,
    request: Request,
    response: Response,
    max_length: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail={"error": "Document not found", "code": 404})

    etag = f'"{doc.id}-v{doc.version}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    response.headers["ETag"] = etag

    full_length = len(doc.content) if doc.content else 0
    content = doc.content
    truncated = False

    if max_length is not None and full_length > max_length:
        content = doc.content[:max_length]
        truncated = True

    return DocumentResponse(
        id=doc.id,
        title=doc.title,
        content=content,
        version=doc.version,
        truncated=truncated,
        content_length=full_length,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.get("/{doc_id}/content")
async def get_document_content(
    doc_id: UUID,
    offset: int = 0,
    limit: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Return document content as plain text with optional pagination."""
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail={"error": "Document not found", "code": 404})

    full_length = len(doc.content) if doc.content else 0
    content = doc.content

    if limit > 0:
        # Snap offset to a line boundary to avoid splitting mid-line
        if offset > 0 and offset < full_length:
            newline = doc.content.rfind('\n', 0, offset)
            if newline > 0:
                offset = newline + 1
        content = doc.content[offset:offset + limit]

    return PlainTextResponse(content, headers={
        "X-Document-Version": str(doc.version),
        "X-Content-Length": str(full_length),
        "X-Content-Offset": str(offset),
    })


@router.patch("/{doc_id}", response_model=PatchDocumentResponse)
async def patch_document(doc_id: UUID, req: PatchDocumentRequest, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail={"error": "Document not found", "code": 404})

    # Concurrency control: if client sends expected_version, reject stale updates
    if req.expected_version is not None and req.expected_version != doc.version:
        raise HTTPException(
            status_code=409,
            detail={
                "error": f"Version conflict: document is at version {doc.version}, "
                         f"but you sent changes for version {req.expected_version}",
                "code": 409,
                "current_version": doc.version,
            },
        )

    changes_dicts = [c.model_dump() for c in req.changes]

    try:
        result = apply_changes(doc.content, changes_dicts)
    except ChangeError as e:
        raise HTTPException(status_code=400, detail={"error": e.message, "code": 400})

    # Save history — full content preserved for audit trail
    history = ChangeHistory(
        document_id=doc.id,
        changes=changes_dicts,
        previous_content=doc.content,
        resulting_content=result.content,
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
        version=doc.version,
        content_length=len(doc.content),
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


@router.get("/{doc_id}/history/{entry_id}")
async def get_history_entry(doc_id: UUID, entry_id: UUID, db: AsyncSession = Depends(get_db)):
    """Return a history entry with before/after content for diffing."""
    entry = await db.get(ChangeHistory, entry_id)
    if not entry or entry.document_id != doc_id:
        raise HTTPException(status_code=404, detail={"error": "History entry not found", "code": 404})

    before = entry.previous_content
    after = entry.resulting_content

    # Backfill for old entries that don't have resulting_content
    if not after:
        try:
            result = apply_changes(before, entry.changes)
            after = result.content
        except Exception:
            after = before

    # For large docs, only send first 500KB of before/after to avoid OOM
    MAX_DIFF_SIZE = 500_000
    if len(before) > MAX_DIFF_SIZE or len(after) > MAX_DIFF_SIZE:
        before = before[:MAX_DIFF_SIZE]
        after = after[:MAX_DIFF_SIZE]

    return {
        "id": entry.id,
        "document_id": entry.document_id,
        "changes": entry.changes,
        "created_at": entry.created_at,
        "previous_content": before,
        "resulting_content": after,
    }
