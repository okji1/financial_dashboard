"""KRX official daily gold-market data. Called only by the elected collector."""
import copy
import datetime
from decimal import Decimal
import logging
import math
import os
import re
import time
from zoneinfo import ZoneInfo

import requests
from shared_store import section, utc_now

URL = 'https://data-dbg.krx.co.kr/svc/apis/gen/gold_bydd_trd'
KST = ZoneInfo('Asia/Seoul')
logger = logging.getLogger(__name__)


class KRXUnavailable(RuntimeError):
    pass


def fetch_daily(key, day):
    """One authenticated request, shared by live checks and archive backfills."""
    try:
        response = requests.get(URL, headers={'AUTH_KEY': key},
            params={'basDd': day.strftime('%Y%m%d')}, timeout=(3, 6), allow_redirects=False)
        if response.status_code != 200:
            raise KRXUnavailable('KRX HTTP error')
        return parse_daily(response.json(), day.strftime('%Y%m%d'))
    except (requests.RequestException, ValueError):
        raise KRXUnavailable('KRX request failed') from None


def numeric(value, *, integer=False, optional=False, nonnegative=False):
    if optional and value in (None, '', '-'):
        return None
    if not isinstance(value, str) or not re.fullmatch(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?', value):
        raise KRXUnavailable('Invalid KRX number')
    raw = value.replace(',', '')
    exact = Decimal(raw)
    result = float(exact)
    if not math.isfinite(result) or (nonnegative and result < 0) or (integer and exact != exact.to_integral_value()):
        raise KRXUnavailable('Invalid KRX number')
    return int(exact) if integer else result


def parse_daily(payload, requested_date):
    rows = payload.get('OutBlock_1') if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise KRXUnavailable('Invalid KRX response')
    items, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise KRXUnavailable('Invalid KRX row')
        symbol = row.get('ISU_CD')
        if symbol not in ('04020000', '04020100'):
            continue
        if row.get('BAS_DD') != requested_date or symbol in seen or not isinstance(row.get('ISU_NM'), str):
            raise KRXUnavailable('Invalid KRX date or instrument')
        seen.add(symbol)
        item = {'symbol': symbol, 'name': row['ISU_NM'],
            'close': numeric(row.get('TDD_CLSPRC'), optional=True, nonnegative=True),
            'change': numeric(row.get('CMPPREVDD_PRC'), optional=True),
            'change_rate': numeric(row.get('FLUC_RT'), optional=True),
            'open': numeric(row.get('TDD_OPNPRC'), optional=True, nonnegative=True),
            'high': numeric(row.get('TDD_HGPRC'), optional=True, nonnegative=True),
            'low': numeric(row.get('TDD_LWPRC'), optional=True, nonnegative=True),
            'volume_grams': numeric(row.get('ACC_TRDVOL'), integer=True, nonnegative=True),
            'trading_value_krw': numeric(row.get('ACC_TRDVAL'), integer=True, nonnegative=True)}
        if item['close'] == 0:
            item['close'] = None
        items.append(item)
    if rows and not items:
        raise KRXUnavailable('No supported KRX instruments')
    return sorted(items, key=lambda item: item['symbol'])


class KRXDailyCache:
    """Hourly checks; bounded holiday lookback and five-minute error backoff.

    Preserve the last verified daily data on transient errors, explicitly marked
    delayed. A daily trade date is never replaced with a collection timestamp.
    """
    def __init__(self, key=None):
        self.key = os.getenv('KRX_API_KEY', '') if key is None else key
        self.data = None
        self.next_check = 0
        self.failed = False

    def get(self, renew=lambda: None):
        if not self.key:
            return section(state='unavailable')
        if time.monotonic() >= self.next_check:
            self.next_check = time.monotonic() + 300
            try:
                today = utc_now().astimezone(KST).date()
                items = []
                for offset in range(14):
                    day = today - datetime.timedelta(days=offset)
                    if day.weekday() >= 5:
                        continue
                    renew()
                    items = fetch_daily(self.key, day)
                    if items:
                        self.data = {'source': 'KRX_OPEN_API', 'trade_date': day.isoformat(),
                            'fetched_at': utc_now().isoformat(), 'items': items}
                        break
                if not items:
                    raise KRXUnavailable('No KRX data within lookback')
                self.failed = False
                self.next_check = time.monotonic() + 3600
            except KRXUnavailable:
                # Never log provider bodies, URLs with keys, or request headers.
                logger.warning('krx_daily_refresh_failed')
                self.failed = True
        if self.data is None:
            return section(state='unavailable')
        return section({**copy.deepcopy(self.data), 'refresh_state': 'delayed' if self.failed else 'ok'})
