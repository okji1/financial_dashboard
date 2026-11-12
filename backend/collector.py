"""One quote collector for a local filesystem shared with the web processes.

cd backend && QUOTE_SNAPSHOT_PATH=/workspace/state/quotes.sqlite venv/bin/python collector.py
The parent directory must already exist. No token/DB cleanup or futures token
issuance is triggered here. Separate hosting services require a shared store.
"""
import logging
import os
import time

from gold_data import _collect_gold_premium_data
from quote_store import write_snapshot

logger = logging.getLogger(__name__)


def refresh_snapshot(path):
    quote = _collect_gold_premium_data()
    write_snapshot(path, quote)
    logger.info('quote_snapshot_refreshed available=%s', quote is not None)
    return quote is not None


def main():
    logging.basicConfig(level=logging.INFO)
    path = os.environ.get('QUOTE_SNAPSHOT_PATH')
    if not path:
        raise SystemExit('QUOTE_SNAPSHOT_PATH is required for the standalone collector')
    while True:
        started = time.monotonic()
        try:
            refresh_snapshot(path)
        except Exception as error:
            logger.error('collector_refresh_failed error=%s', type(error).__name__)
        # Start-to-start cadence, allowing time for external request latency.
        time.sleep(max(1, 30 - (time.monotonic() - started)))


if __name__ == '__main__':
    main()
