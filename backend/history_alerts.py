"""Persistent KRX history and operational events, independent of live expiry."""
import datetime
import logging
import time
from krx_data import KST, KRXUnavailable, fetch_daily
from shared_store import StoreUnavailable, LeaseLost, fresh_timestamp, utc_now

logger = logging.getLogger(__name__)
SOURCES = {'gold': '금 시세', 'futures': '금선물', 'krx': 'KRX 일별 자료', 'collector': '수집기'}


def monitor_states(payload):
    gold = payload.get('gold', {})
    futures = payload.get('active_contract', {})
    krx = payload.get('krx_daily', {})
    return {'collector': 'ok',
        'gold': 'ok' if gold.get('state') == 'ok' and fresh_timestamp((gold.get('data') or {}).get('timestamp')) else 'error',
        'futures': 'ok' if payload.get('candidates', {}).get('state') == 'ok' and futures.get('state') in ('ok','empty')
            and not any(book.get('state') == 'unavailable' for book in payload.get('orderbooks', {}).values()) else 'error',
        'krx': 'ok' if krx.get('state') == 'ok' and (krx.get('data') or {}).get('refresh_state') == 'ok'
            and fresh_timestamp((krx.get('data') or {}).get('fetched_at'), max_age=7200) else 'error'}


class HistoryAlertsStore:
    def __init__(self, store):
        self.store = store

    def archive(self, day, items, fetched_at):
        if items:
            self.store._request('POST', 'krx_gold_history', params={'on_conflict':'trade_date,symbol'},
                headers={'Prefer':'resolution=merge-duplicates,return=representation'},
                json=[{'trade_date':day.isoformat(), 'symbol':item['symbol'], 'quote':item,'fetched_at':fetched_at} for item in items])
        self.store._request('POST', 'krx_gold_days', params={'on_conflict':'trade_date'},
            headers={'Prefer':'resolution=merge-duplicates,return=representation'},
            json={'trade_date':day.isoformat(),'has_data':bool(items),'fetched_at':fetched_at})

    def checked_days(self, days=90):
        cutoff=(utc_now().astimezone(KST).date()-datetime.timedelta(days=days-1)).isoformat()
        return self.store._request('GET','krx_gold_days',params={'select':'trade_date,has_data', 'trade_date':'gte.'+cutoff,'limit':366})

    def history(self, symbol, days):
        return self.store._request('POST','rpc/dashboard_read_krx_history',json={'p_symbol':symbol,'p_days':days})

    def monitor(self, owner, states):
        if self.store._request('POST','rpc/dashboard_record_monitor',json={'p_owner':owner,'p_states':states}) is not True:
            raise LeaseLost('Collector lost ownership before monitor update')

    def alerts(self):
        bundle=self.store._request('POST','rpc/dashboard_read_system_alerts',json={})
        events=bundle['events']
        age=None
        if bundle.get('collected_at'):
            collected=datetime.datetime.fromisoformat(bundle['collected_at'].replace('Z','+00:00'))
            age=max(0,(utc_now()-collected).total_seconds())
            if age>90 and bundle.get('collector_status')!='error':
                started=collected+datetime.timedelta(seconds=90)
                event={'id':'collector-error-'+str(int(started.timestamp())),'source':'collector','status':'error','occurred_at':started.isoformat()}
                if not any(item['id']==event['id'] for item in events): events.insert(0,event)
        for event in events:
            event['message']=SOURCES[event['source']]+(' 수집 실패 또는 데이터 지연이 감지됐습니다.' if event['status']=='error' else ' 수집이 정상으로 복구됐습니다.')
        return {'events':events[:100], 'snapshot_age_seconds':age,'checked_at':utc_now().isoformat()}


class ArchiveWorker:
    """At most one historical provider request per cycle, after live publication."""
    def __init__(self, archive, key):
        self.archive=archive; self.key=key; self.checked=None; self.next_attempt=0
        self.last_daily=None

    def run_once(self, krx, renew):
        if not self.key or time.monotonic()<self.next_attempt: return
        self.next_attempt=time.monotonic()+30
        try:
            data=krx.get('data') or {}
            if krx.get('state')=='ok' and data.get('refresh_state')=='ok' and data.get('fetched_at')!=self.last_daily:
                renew()
                self.archive.archive(datetime.date.fromisoformat(data['trade_date']),data['items'],data['fetched_at'])
                self.last_daily=data['fetched_at']
            if self.checked is None:
                self.checked={row['trade_date'] for row in self.archive.checked_days()}
            today=utc_now().astimezone(KST).date()
            for offset in range(1,90):
                day=today-datetime.timedelta(days=offset)
                if day.weekday()>=5 or day.isoformat() in self.checked: continue
                renew()
                items=fetch_daily(self.key,day)
                renew()
                self.archive.archive(day,items,utc_now().isoformat())
                self.checked.add(day.isoformat())
                break
        except (KRXUnavailable,StoreUnavailable) as error:
            if isinstance(error,LeaseLost):raise
            self.next_attempt=time.monotonic()+300
            logger.warning('krx_archive_failed error=%s',type(error).__name__)
