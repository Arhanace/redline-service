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
    """Full-text search with phrase support and ILIKE fallback."""

    where_clause = ""
    params = {"query": query, "limit": limit, "offset": offset}

    if document_id:
        where_clause = "AND d.id = :doc_id"
        params["doc_id"] = str(document_id)

    # Determine search strategy:
    # - Multi-word queries use phraseto_tsquery (words must be adjacent)
    # - Single-word queries use plainto_tsquery
    # - If tsquery is empty (all stop words), fall back to ILIKE
    words = query.strip().split()
    is_phrase = len(words) > 1

    if is_phrase:
        check_sql = text("SELECT phraseto_tsquery('english', :query)::text")
    else:
        check_sql = text("SELECT plainto_tsquery('english', :query)::text")

    check_result = await db.execute(check_sql, {"query": query})
    tsquery_text = check_result.scalar()
    use_fts = tsquery_text and tsquery_text.strip() not in ("", "''")

    if use_fts:
        tsquery_func = "phraseto_tsquery" if is_phrase else "plainto_tsquery"

        count_sql = text(f"""
            SELECT COUNT(*)
            FROM documents d
            WHERE d.search_vector @@ {tsquery_func}('english', :query)
            {where_clause}
        """)
        count_result = await db.execute(count_sql, params)
        total = count_result.scalar()

        # If FTS finds nothing for a phrase, fall back to ILIKE
        # (phraseto_tsquery is strict about adjacency after stemming)
        if total == 0 and is_phrase:
            use_fts = False
        else:
            search_sql = text(f"""
                SELECT
                    d.id,
                    d.title,
                    ts_headline('english', d.content, {tsquery_func}('english', :query),
                        'StartSel=<mark>, StopSel=</mark>, MaxWords=25, MinWords=10, MaxFragments=3, HighlightAll=false'
                    ) as snippet,
                    ts_rank(d.search_vector, {tsquery_func}('english', :query)) as rank
                FROM documents d
                WHERE d.search_vector @@ {tsquery_func}('english', :query)
                {where_clause}
                ORDER BY rank DESC
                LIMIT :limit OFFSET :offset
            """)

    if not use_fts:
        # ILIKE fallback — always works, handles stop words and exact substrings
        params["pattern"] = f"%{query}%"
        count_sql = text(f"""
            SELECT COUNT(*)
            FROM documents d
            WHERE (d.title ILIKE :pattern OR d.content ILIKE :pattern)
            {where_clause}
        """)
        count_result = await db.execute(count_sql, params)
        total = count_result.scalar()

        search_sql = text(f"""
            SELECT
                d.id,
                d.title,
                CASE
                    WHEN d.content ILIKE :pattern THEN
                        REPLACE(
                            SUBSTRING(d.content FROM GREATEST(1, POSITION(LOWER(:query) IN LOWER(d.content)) - 60) FOR 200),
                            SUBSTRING(d.content FROM POSITION(LOWER(:query) IN LOWER(d.content)) FOR LENGTH(:query)),
                            '<mark>' || SUBSTRING(d.content FROM POSITION(LOWER(:query) IN LOWER(d.content)) FOR LENGTH(:query)) || '</mark>'
                        )
                    ELSE d.title
                END as snippet,
                1.0 as rank
            FROM documents d
            WHERE (d.title ILIKE :pattern OR d.content ILIKE :pattern)
            {where_clause}
            ORDER BY d.updated_at DESC
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
