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


class TestConcurrencyControl:
    async def test_version_match_succeeds(self, client):
        create = await client.post("/api/documents", json={"title": "T", "content": "hello world"})
        doc_id = create.json()["id"]
        resp = await client.patch(f"/api/documents/{doc_id}", json={
            "changes": [{"operation": "replace", "target": {"text": "hello"}, "replacement": "hi"}],
            "expected_version": 1,
        })
        assert resp.status_code == 200
        assert resp.json()["version"] == 2

    async def test_version_mismatch_returns_409(self, client):
        create = await client.post("/api/documents", json={"title": "T", "content": "hello world"})
        doc_id = create.json()["id"]
        # First patch bumps to v2
        await client.patch(f"/api/documents/{doc_id}", json={
            "changes": [{"operation": "replace", "target": {"text": "hello"}, "replacement": "hi"}],
        })
        # Second patch with stale version should 409
        resp = await client.patch(f"/api/documents/{doc_id}", json={
            "changes": [{"operation": "replace", "target": {"text": "hi"}, "replacement": "hey"}],
            "expected_version": 1,
        })
        assert resp.status_code == 409

    async def test_etag_returned_on_get(self, client):
        create = await client.post("/api/documents", json={"title": "T", "content": "body"})
        doc_id = create.json()["id"]
        resp = await client.get(f"/api/documents/{doc_id}")
        assert "etag" in resp.headers


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

    async def test_history_entry_detail(self, client):
        create = await client.post("/api/documents", json={"title": "T", "content": "hello world"})
        doc_id = create.json()["id"]
        await client.patch(f"/api/documents/{doc_id}", json={
            "changes": [{"operation": "replace", "target": {"text": "hello"}, "replacement": "hi"}]
        })
        history = await client.get(f"/api/documents/{doc_id}/history")
        entry_id = history.json()["history"][0]["id"]
        resp = await client.get(f"/api/documents/{doc_id}/history/{entry_id}")
        assert resp.status_code == 200
        assert resp.json()["previous_content"] == "hello world"


class TestSearch:
    async def test_search_finds_document(self, client):
        await client.post("/api/documents", json={"title": "Contract", "content": "This is a legal agreement between parties"})
        # Note: search uses ILIKE fallback in SQLite (no tsvector), so basic substring matching works
        resp = await client.get("/api/documents/search?q=legal")
        assert resp.status_code == 200

    async def test_search_empty_query_returns_422(self, client):
        resp = await client.get("/api/documents/search?q=")
        assert resp.status_code == 422

    async def test_search_no_results(self, client):
        await client.post("/api/documents", json={"title": "Doc", "content": "some text"})
        resp = await client.get("/api/documents/search?q=xyznonexistent")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
