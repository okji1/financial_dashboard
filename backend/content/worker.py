"""Manual/scheduled worker entry point. No code executes on import.

Run only from an isolated scheduled job after reviewing NEWS_FEED_HOSTS and
staging migration. Never attach to a Flask request or run on first request.
"""
from __future__ import annotations

import argparse
import json
import os
from urllib.parse import urlsplit

from content.ingest import ingest_sources, allowed_hosts_from_env
from content.storage import load_enabled_sources, upsert_article_metadata


def run_worker(*, dry_run: bool) -> dict:
    from supabase import create_client

    url = os.environ.get("CONTENT_SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("CONTENT_SUPABASE_SERVICE_ROLE_KEY", "")
    expected = os.environ.get("CONTENT_SUPABASE_PROJECT_ID", "")
    hosts = allowed_hosts_from_env()
    if not url or not key or not expected or not hosts:
        raise RuntimeError("CONTENT_SUPABASE_* and NEWS_FEED_HOSTS must be set")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != f"{expected}.supabase.co"
        or not expected.replace("-", "").isalnum()
        or not parsed.hostname
    ):
        raise RuntimeError("Supabase URL and expected project ID mismatch")
    if not dry_run and os.environ.get("CONTENT_INGEST_WRITE_ENABLED") != "yes":
        raise RuntimeError("Explicit CONTENT_INGEST_WRITE_ENABLED=yes required for DB writes")

    client = create_client(url, key)
    sources = load_enabled_sources(client)
    sink = lambda source, rows: upsert_article_metadata(client, source, rows)
    return ingest_sources(
        sources,
        allowed_hosts=hosts,
        sink=sink if not dry_run else None,
        dry_run=dry_run,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Controlled RSS/Atom ingestion")
    parser.add_argument("--write", action="store_true", help="Write new metadata to configured Supabase project")
    args = parser.parse_args()
    report = run_worker(dry_run=not args.write)
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
