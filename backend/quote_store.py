"""Atomic quote snapshots for processes sharing one local SQLite filesystem.

Opt in with QUOTE_SNAPSHOT_PATH. Separate Render services do not normally
share a disk: use a managed shared store for that deployment topology.
"""
import datetime
import json
import logging
import math
import sqlite3
from pathlib import Path
from contextlib import closing

logger = logging.getLogger(__name__)
REQUIRED_PRICES = ('international_price_usd_oz', 'domestic_price_krw_g',
                   'usd_krw_rate', 'converted_intl_price_krw_g')


def valid_quote(quote):
    if not isinstance(quote, dict):
        return False
    if not all(isinstance(quote.get(key), (int, float)) and not isinstance(quote[key], bool)
               and math.isfinite(quote[key]) and quote[key] > 0 for key in REQUIRED_PRICES):
        return False
    premium = quote.get('premium_percentage')
    return (isinstance(premium, (int, float)) and not isinstance(premium, bool)
            and math.isfinite(premium) and isinstance(quote.get('premium_grade'), str))


def write_snapshot(path, quote, *, ttl_seconds=60, now=None):
    """Collector only. Persist success OR explicit unavailability atomically.

    A failed refresh replaces the old quote, avoiding stale trade signals.
    sqlite transaction/WAL is not a collector election mechanism; run ONE writer.
    """
    if not isinstance(ttl_seconds, (int, float)) or not math.isfinite(ttl_seconds) or ttl_seconds <= 0:
        raise ValueError('ttl_seconds must be finite and positive')
    if quote is not None and not valid_quote(quote):
        raise ValueError('Invalid quote snapshot')
    now = now or datetime.datetime.now(datetime.timezone.utc)
    payload = json.dumps(quote, allow_nan=False) if quote is not None else None
    with closing(sqlite3.connect(path, timeout=2)) as connection, connection:
        connection.execute('CREATE TABLE IF NOT EXISTS quote_snapshot (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT, expires_at REAL NOT NULL)')
        connection.execute('INSERT INTO quote_snapshot VALUES (1, ?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, expires_at=excluded.expires_at',
                           (payload, now.timestamp() + ttl_seconds))


def read_snapshot(path, *, now=None):
    """Readers never create the store, collect remotely, or return stale data."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    try:
        uri = Path(path).resolve().as_uri() + '?mode=ro'
        with closing(sqlite3.connect(uri, uri=True, timeout=2)) as connection:
            row = connection.execute('SELECT payload, expires_at FROM quote_snapshot WHERE id=1').fetchone()
        if not row or row[0] is None or not math.isfinite(row[1]) or row[1] <= now.timestamp():
            return None
        quote = json.loads(row[0])
        if not valid_quote(quote):
            return None
        collected = datetime.datetime.fromisoformat(quote['timestamp'])
        age = (now - collected).total_seconds()
        # Reject naive/future timestamps and snapshots older than the collection TTL.
        if collected.tzinfo is None or not 0 <= age <= 60:
            return None
        return quote
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError):
        logger.warning('quote_snapshot_unavailable')
        return None
