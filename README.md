# Redline Service

A document redlining service with inline editing, full-text search, bulk operations, change history tracking, and optimistic concurrency control.

**Live demo:** https://redline-service-production.up.railway.app

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
| Diff Engine | react-diff-viewer (history modal) |
| Testing | pytest, httpx, pytest-asyncio |
| Infrastructure | Docker Compose, Railway |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/documents` | Create a document |
| `GET` | `/api/documents` | List all documents |
| `GET` | `/api/documents/{id}` | Get a single document (with ETag) |
| `PATCH` | `/api/documents/{id}` | Apply text changes (supports bulk + versioning) |
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

### Concurrency Control

Optimistic locking via document versioning. Clients can send `expected_version` to prevent conflicting updates:

```bash
curl -X PATCH http://localhost:8000/api/documents/{id} \
  -H "Content-Type: application/json" \
  -d '{
    "changes": [{"operation": "replace", "target": {"text": "old"}, "replacement": "new"}],
    "expected_version": 2
  }'
```

If the document has been modified since the client last fetched it (version mismatch), the server returns **409 Conflict**:

```json
{ "error": "Version conflict: document is at version 3, but you sent changes for version 2", "code": 409 }
```

The `GET /api/documents/{id}` endpoint also returns an `ETag` header (`"{id}-v{version}"`) and supports `If-None-Match` for cache validation (returns 304 if unchanged).

### Error Responses

All errors follow a consistent JSON format:

| Status | When |
|--------|------|
| 400 | Invalid change (target text not found, occurrence out of range) |
| 404 | Document not found |
| 409 | Version conflict (stale `expected_version`) |
| 422 | Malformed request body (missing required fields) |
| 500 | Unexpected server error |

```json
{ "error": "Target text 'xyz' not found in document", "code": 400 }
```

## Architecture

```
React (Vite:5173) --> FastAPI (:8000) --> PostgreSQL (:5432)
                          |-- Change Engine (str.find, O(n))
                          |-- Search Service (tsvector + GIN index)
```

### Change Engine

The change engine processes replacements sequentially using `str.find()` with offset tracking — O(n) per change, no regex. This handles 10MB+ documents with 100 changes in under 5 seconds.

For bulk operations, changes are applied in order. Each replacement adjusts the content, and subsequent changes operate on the updated text. This sequential model is predictable: the Nth change sees the result of changes 1 through N-1.

**Why `str.find()` over regex?** Regular expressions have unpredictable performance on large inputs (backtracking, catastrophic patterns). `str.find()` is a simple linear scan — O(n) per call where n is the document length. For m changes on a document of length n, total cost is O(m*n) which is near-linear when m is small relative to n. The benchmark test proves this: 100 changes on a 10MB document finishes in under 5 seconds.

### Search Indexing

Full-text search uses PostgreSQL's built-in `tsvector`/`tsquery` with a GIN index. The `search_vector` column is auto-updated via a database trigger on every INSERT or UPDATE of the document content.

**How it works:**
1. A trigger converts `title + content` into a `tsvector` (normalized word list with positions) on every write
2. A GIN (Generalized Inverted Index) index on `search_vector` allows sub-linear lookup
3. Queries use `plainto_tsquery` to parse user input and `ts_rank` for relevance scoring
4. `ts_headline` generates context snippets with `<mark>` tags around matches

**Trade-offs vs. alternatives:**

| Approach | Pros | Cons |
|----------|------|------|
| **PostgreSQL tsvector (chosen)** | Zero additional infra, GIN index is fast, built-in ranking and snippets | English-centric stemming, limited fuzzy/typo tolerance |
| In-memory inverted index | Very fast repeated queries, no DB dependency | Lost on restart, memory-hungry for large corpora, complex to maintain consistency |
| Elasticsearch/Typesense | Best relevance, fuzzy matching, analyzers | Additional service to deploy and maintain, operational complexity |

For this use case (tens to hundreds of legal documents, exact-phrase heavy), Postgres FTS is the right balance of capability and simplicity. The GIN index means search is O(log n) in the number of documents, not O(n). An in-memory index would add speed for repeated queries but would require cache invalidation logic on every document write and would not survive restarts.

### Performance Considerations

- **Document storage:** TEXT columns in PostgreSQL have no practical size limit (up to 1GB). No chunking needed.
- **Change engine:** O(n) per change via `str.find()`, no regex. Benchmark: 100 changes on 10MB doc < 5s.
- **Search:** GIN-indexed tsvector lookup is O(log n) in corpus size. Snippet generation is O(n) per document but only runs on matched documents.
- **Async I/O:** SQLAlchemy async + asyncpg means database operations don't block the event loop. Multiple requests can be served concurrently on a single process.
- **For 10MB+ documents:** The main bottleneck is the change engine scanning the full text per change. Streaming or rope data structures could improve this but add significant complexity. For the expected use case (legal documents, typically 10-100KB), the current approach is well within acceptable latency.

### API Design Rationale

The API follows RESTful conventions with a clear separation between reads and writes:

- **GET** endpoints are pure reads with no side effects — safe to cache and retry
- **PATCH** (not PUT) for changes because we're applying partial modifications, not replacing the whole resource
- **Separate search router** registered before the document router to avoid `{doc_id}` path parameter matching the literal string "search"
- **Changes as a structured array** rather than sending raw text — this gives the server control over how changes are applied, enables conflict detection, and creates an audit trail
- **Version in response** rather than requiring version on every request — `expected_version` is optional, so simple clients can ignore concurrency control while careful clients opt in

**Why not action-based endpoints (e.g., POST /documents/{id}/redline)?** REST PATCH semantically matches what we're doing — modifying a resource in place. Action endpoints are appropriate when the operation doesn't map to CRUD (e.g., "publish" or "merge"), but text replacement is a modification of the document resource itself.

## Running Tests

```bash
cd backend
pip install -e ".[dev]"
python -m pytest tests/ -v
```

Tests use an in-memory SQLite database (with PostgreSQL type monkey-patching) so no running database is needed.

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
│   │   ├── main.py              # FastAPI app + middleware + static serving
│   │   ├── config.py            # Settings (Railway DATABASE_URL support)
│   │   ├── database.py          # Async SQLAlchemy engine
│   │   ├── models.py            # Document + ChangeHistory models
│   │   ├── schemas.py           # Pydantic request/response schemas
│   │   ├── seed.py              # Sample document seeder
│   │   ├── routers/
│   │   │   ├── documents.py     # CRUD + PATCH + history + ETag
│   │   │   └── search.py        # Full-text search endpoints
│   │   └── services/
│   │       ├── change_engine.py  # Core text replacement logic
│   │       └── search_service.py # Postgres FTS query builder
│   └── tests/
│       ├── conftest.py           # Test fixtures (SQLite, async client)
│       ├── test_change_engine.py # Unit tests (10 tests incl. perf benchmark)
│       └── test_documents_api.py # API integration tests (14 tests incl. concurrency)
└── frontend/
    └── src/
        ├── App.jsx               # Main layout
        ├── api/client.js         # API helper
        └── components/
            ├── DocumentList.jsx  # Sidebar document list
            ├── SearchBar.jsx     # Search with snippets
            ├── DiffEditor.jsx    # Side-by-side editor with diff preview
            └── ChangeHistory.jsx # Change timeline
```
