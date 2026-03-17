# Redline Service — Design Document

## Overview

A document redlining service with side-by-side editing, full-text search, change history, and bulk operations. Built as a take-home interview assessment demonstrating API design, code quality, and production thinking.

## Tech Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy (async), PostgreSQL, Alembic
- **Frontend:** React (Vite), TailwindCSS, diff-match-patch, react-diff-viewer
- **Infrastructure:** Docker Compose (local), Railway (hosted)
- **Testing:** pytest, httpx (async test client)

## Architecture

```
┌─────────────┐     ┌─────────────────┐     ┌────────────┐
│   React UI  │────▶│  FastAPI (8000)  │────▶│ PostgreSQL │
│  Vite (5173)│◀────│                  │◀────│            │
└─────────────┘     └─────────────────┘     └────────────┘
                           │
                    ┌──────┴──────┐
                    │  Services   │
                    │ - change_engine │
                    │ - search_service│
                    └─────────────┘
```

## API Design

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/documents | Create document |
| GET | /api/documents | List documents |
| GET | /api/documents/{id} | Get document |
| PATCH | /api/documents/{id} | Apply changes (bulk) |
| DELETE | /api/documents/{id} | Delete document |
| GET | /api/documents/search?q=&limit=&offset= | Search across all docs |
| GET | /api/documents/{id}/search?q= | Search within one doc |
| GET | /api/documents/{id}/history | Get change history |

### PATCH /api/documents/{id}

Request:
```json
{
  "changes": [
    {
      "operation": "replace",
      "target": { "text": "old text", "occurrence": 1 },
      "replacement": "new text"
    }
  ]
}
```

Response:
```json
{
  "id": "uuid",
  "title": "Contract Draft",
  "content": "...updated...",
  "version": 3,
  "changes_applied": 2,
  "updated_at": "2026-03-15T..."
}
```

### GET /api/documents/search

Response:
```json
{
  "results": [
    {
      "document_id": "uuid",
      "title": "Contract Draft",
      "snippets": ["...matching text..."],
      "rank": 0.95
    }
  ],
  "total": 5,
  "limit": 10,
  "offset": 0
}
```

### Error format

All errors: `{ "error": "message", "code": 404 }`

## Database Schema

### documents
- `id` UUID PRIMARY KEY
- `title` VARCHAR(500)
- `content` TEXT
- `search_vector` TSVECTOR (auto-updated via trigger)
- `version` INTEGER DEFAULT 1
- `created_at` TIMESTAMPTZ
- `updated_at` TIMESTAMPTZ

Indexes: GIN on `search_vector`

### change_history
- `id` UUID PRIMARY KEY
- `document_id` UUID FK → documents
- `changes` JSONB (the changes array as submitted)
- `previous_content` TEXT
- `created_at` TIMESTAMPTZ

## Core Logic

### Change Engine
- Processes changes array sequentially against document content
- `str.find()` with offset tracking — O(n) per change, no regex
- `occurrence` param: omitted = first match, 0 or "all" = all matches
- For bulk changes: apply sequentially, adjusting offsets after each replacement
- Validates target text exists, returns 400 with specific error if not
- Returns modified content + change summary for history storage

### Large File Performance (10MB+)
- `str.find()` over regex for linear-time matching
- Bulk changes sorted/adjusted to avoid offset drift
- Postgres FTS indexing at write time via trigger (reads stay fast)
- Async SQLAlchemy for non-blocking DB access
- Benchmark test: 10MB doc, 100 changes, asserts completion under threshold

### Search
- Postgres `tsvector` column updated via SQL trigger on INSERT/UPDATE
- GIN index for fast lookups
- `ts_headline()` for highlighted snippets
- `ts_rank()` for relevance ordering
- Trade-off: good for English prose, limited for fuzzy/typo search — production would consider Elasticsearch

### Change History
- Every PATCH writes to `change_history`: changes array (JSONB), previous content, timestamp
- History endpoint returns reverse chronological with pagination

## Frontend

### Layout
- **Left sidebar:** document list + search bar
- **Main area:** side-by-side editor (original left, editable right) with diff highlighting
- **Bottom panel:** change history timeline

### Side-by-Side Editor
- Left pane: read-only, current saved version
- Right pane: editable, user makes changes here
- "Submit Changes": frontend diffs using `diff-match-patch`, converts to API changes array, sends PATCH
- After success: left pane updates to match right (new baseline)
- Diff colors: red = deletions (left), green = insertions (right)

### Search
- Search bar sends `GET /documents/search?q=...`
- Results as document cards with highlighted snippets
- Click loads document into editor

### Change History Panel
- Timeline of edits per document
- Each entry: timestamp + summary ("Replaced 'X' with 'Y'")

## Project Structure

```
redline-service/
├── docker-compose.yml
├── README.md
├── INFRASTRUCTURE.md
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── database.py
│   │   ├── routers/
│   │   │   ├── documents.py
│   │   │   └── search.py
│   │   └── services/
│   │       ├── change_engine.py
│   │       └── search_service.py
│   └── tests/
│       ├── conftest.py
│       ├── test_change_engine.py
│       ├── test_documents_api.py
│       ├── test_search.py
│       └── test_performance.py
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       ├── App.jsx
│       ├── components/
│       │   ├── DocumentList.jsx
│       │   ├── SearchBar.jsx
│       │   ├── DiffEditor.jsx
│       │   └── ChangeHistory.jsx
│       └── api/
│           └── client.js
└── sample-requests/
    └── requests.sh
```

## Hosting

- **Local:** `docker-compose up` — Postgres, backend, frontend all in one command
- **Production:** Railway — deploy from GitHub, each service as a Railway service, managed Postgres addon
- **Seed data:** Startup script loads 2-3 sample documents (contract, ToS, memo)

## Time Budget (3-4 hours)

1. Project setup + Docker + DB schema + migrations (~30 min)
2. Backend API + change engine + search service (~60 min)
3. Tests (unit + integration + performance) (~30 min)
4. Frontend (side-by-side editor + search + history) (~60 min)
5. README + sample requests + polish (~20 min)
6. Railway deploy + verify (~20 min)
