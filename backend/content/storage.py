"""Supabase adapter for content ingestion; instantiate only in explicit CLI runs."""
from __future__ import annotations

from content.ingest import FeedSource


def load_enabled_sources(client) -> list[FeedSource]:
    response = (
        client.table("news_sources")
        .select("id,name,feed_url")
        .eq("enabled", True)
        .order("created_at")
        .limit(20)
        .execute()
    )
    return [
        FeedSource(id=str(row["id"]), name=row["name"], feed_url=row["feed_url"])
        for row in response.data or []
    ]


def upsert_article_metadata(client, source: FeedSource, rows: list[dict]) -> int:
    """Insert unseen URLs. Existing selected/ignored editorial state is preserved.

    PostgREST ignore_duplicates maps to ON CONFLICT DO NOTHING for url_hash.
    'saved' is the number of newly inserted rows, not total feed entries.
    """
    if not rows:
        return 0
    response = (
        client.table("news_articles")
        .upsert(rows, on_conflict="url_hash", ignore_duplicates=True, returning="representation")
        .execute()
    )
    return len(response.data or [])
