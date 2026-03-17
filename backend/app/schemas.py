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
    expected_version: int | None = None  # Optimistic concurrency control


class CreateDocumentRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    content: str = ""


# --- Response schemas ---

class DocumentSummary(BaseModel):
    id: UUID
    title: str
    version: int
    content_length: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentResponse(BaseModel):
    id: UUID
    title: str
    content: str
    version: int
    truncated: bool = False
    content_length: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PatchDocumentResponse(BaseModel):
    id: UUID
    title: str
    version: int
    content_length: int
    changes_applied: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    documents: list[DocumentSummary]
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


class ChangeHistoryDetailEntry(ChangeHistoryEntry):
    previous_content: str


class ChangeHistoryResponse(BaseModel):
    history: list[ChangeHistoryEntry]
    total: int


class ErrorResponse(BaseModel):
    error: str
    code: int
