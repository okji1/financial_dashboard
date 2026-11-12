"""One lease-elected market-data process; never started by an ASGI lifespan."""
import datetime
import logging
import os
import signal
import tempfile
import threading
import time
import uuid
from pathlib import Path

import requests
from gold_data import _collect_gold_premium_data
from gold_master import load_gold_contracts, MAX_MASTER_BYTES
from futures_api import get_domestic_futures_data, get_domestic_futures_orderbook, FuturesUnavailable
from shared_store import SharedStore, LeaseLost, StoreUnavailable, section, utc_now
from krx_data import KRXDailyCache
from history_alerts import HistoryAlertsStore, ArchiveWorker, monitor_states

logger = logging.getLogger(__name__)
MASTER_URL = 'https://new.real.download.dws.co.kr/common/master/fo_com_code.mst.zip'


class MasterCache:
    def __init__(self, directory):
        self.path = Path(directory) / 'commodity-master.zip'
        self.candidates = None
        self.fetched_at = None
        self.last_attempt = None

    def get(self, force=False):
        age = (utc_now() - self.fetched_at).total_seconds() if self.fetched_at else float('inf')
        due = force or age >= 86400
        # Retry failures at most once per five minutes; keep a verified <=36h master.
        if due and (self.last_attempt is None or time.monotonic() - self.last_attempt >= 300):
            self.last_attempt = time.monotonic()
            temporary = None
            try:
                with requests.get(MASTER_URL, timeout=(3, 8), stream=True) as response:
                    response.raise_for_status()
                    with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as output:
                        temporary = Path(output.name)
                        size = 0
                        for chunk in response.iter_content(65536):
                            size += len(chunk)
                            if size > MAX_MASTER_BYTES:
                                raise ValueError('Master archive exceeds size limit')
                            output.write(chunk)
                candidates = load_gold_contracts(temporary)
                if not candidates:
                    raise ValueError('Official master has no verified gold futures')
                os.replace(temporary, self.path)
                self.candidates = candidates
                self.fetched_at = utc_now()
                age = 0
            except Exception as error:
                logger.warning('master_refresh_failed error=%s', type(error).__name__)
            finally:
                if temporary is not None and temporary.exists():
                    temporary.unlink()
        if not self.candidates or age > 36 * 3600:
            raise StoreUnavailable('Verified gold master unavailable')
        return list(self.candidates)


class SnapshotCollector:
    def __init__(self, store, master, owner=None, krx=None):
        self.store = store
        self.master = master
        self.owner = owner or str(uuid.uuid4())
        self.krx = krx if krx is not None else KRXDailyCache()

    def after_publish(self, payload):
        # Persistence failures must not discard an already published live quote.
        try:
            HistoryAlertsStore(self.store).monitor(self.owner, monitor_states(payload))
        except StoreUnavailable as error:
            logger.warning('monitor_write_failed error=%s', type(error).__name__)

    def renew(self):
        return self.store.claim(self.owner)

    def collect_once(self, force_master=False):
        self.renew()
        payload = {'gold': section(state='unavailable'), 'candidates': section(state='unavailable'),
                   'active_contract': section(state='unavailable'), 'orderbooks': {}}
        quote = _collect_gold_premium_data()
        payload['gold'] = section(quote, 'ok' if quote is not None else 'unavailable')
        payload['krx_daily'] = self.krx.get(renew=self.renew)
        self.renew()
        try:
            candidates = self.master.get(force=force_master)
        except StoreUnavailable:
            self.store.publish(self.owner, str(uuid.uuid4()), payload)
            self.after_publish(payload)
            return payload
        payload['candidates'] = section({'candidates': candidates, 'count': len(candidates)})
        prices, failed = [], False
        for candidate in candidates:
            symbol = candidate['symbol']
            self.renew()
            try:
                price = get_domestic_futures_data(symbol)
                price_at = utc_now().isoformat()
                if price:
                    prices.append((candidate, price, price_at))
            except FuturesUnavailable:
                failed = True
            self.renew()
            try:
                book = get_domestic_futures_orderbook(symbol)
                payload['orderbooks'][symbol] = section(book, 'ok' if book is not None else 'empty')
            except FuturesUnavailable:
                payload['orderbooks'][symbol] = section(state='unavailable')
        # A failed candidate may hide the highest-volume contract: fail closed.
        if not failed:
            if not prices:
                payload['active_contract'] = section(state='empty')
            else:
                candidate, price, captured = max(prices, key=lambda row: row[1]['volume'])
                active = {**candidate, **price, 'expiry_year': candidate.get('year'),
                    'expiry_month': candidate.get('month'), 'updated_at': captured}
                book_section = payload['orderbooks'][active['symbol']]
                if book_section['state'] == 'ok':
                    book = book_section['data']
                    active.update(buy_pressure=book['buy_pressure_pct'], sell_pressure=book['sell_pressure_pct'],
                        pressure_signal=book['pressure_signal'], total_bid_quantity=book['total_bid_quantity'],
                        total_ask_quantity=book['total_ask_quantity'],
                        best_bid=next(iter(book['orderbook'].get('bid_prices', [])), None),
                        best_ask=next(iter(book['orderbook'].get('ask_prices', [])), None))
                payload['active_contract'] = section(active)
                payload['active_contract']['collected_at'] = captured
        # Guarded atomic bundle publication prevents cross-generation books/signals.
        self.renew()
        self.store.publish(self.owner, str(uuid.uuid4()), payload)
        self.after_publish(payload)
        logger.info('snapshot_published gold=%s active=%s candidate_count=%d',
                    payload['gold']['state'], payload['active_contract']['state'], len(candidates))
        return payload


def main():
    logging.basicConfig(level=logging.INFO)
    if os.getenv('DASHBOARD_COLLECTOR_MODE') not in ('embedded', 'standalone'):
        raise SystemExit('Explicit collector mode is required; do not collect against production from development tasks')
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    store = SharedStore()
    with tempfile.TemporaryDirectory(prefix='dashboard-master-') as directory:
        collector = SnapshotCollector(store, MasterCache(directory))
        archive = ArchiveWorker(HistoryAlertsStore(store), os.getenv('KRX_API_KEY', ''))
        # Token issuance is permitted only while this process owns the shared lease.
        from kis_auth import set_issuance_guard
        set_issuance_guard(collector.renew)
        next_cycle = 0.0
        seen_request = None
        try:
            while not stop.is_set():
                try:
                    lease = collector.renew()
                    requested = lease.get('refresh_requested_at')
                    force = seen_request is not None and requested != seen_request
                    if time.monotonic() >= next_cycle or force:
                        cycle_started = time.monotonic()
                        payload = collector.collect_once(force_master=force)
                        seen_request = requested
                        next_cycle = cycle_started + 30
                        archive.run_once(payload.get('krx_daily', {}), collector.renew)
                except LeaseLost:
                    logger.info('collector_waiting_for_lease')
                except Exception as error:
                    logger.warning('collector_cycle_failed error=%s', type(error).__name__)
                    try:
                        HistoryAlertsStore(store).monitor(collector.owner, {'collector':'error'})
                    except StoreUnavailable:
                        pass
                stop.wait(3)
        finally:
            try:
                store.release(collector.owner)
            except StoreUnavailable:
                pass


if __name__ == '__main__':
    main()
