"""Archive verified KRX data without touching the live collector/snapshot.

backend/venv/bin/python ops/backfill_krx.py --days 90 --from-render
Only missing weekdays are queried. Empty holiday responses are remembered.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from shared_store import SharedStore, utc_now
from history_alerts import HistoryAlertsStore
from krx_data import KST, fetch_daily


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--days',type=int,choices=[30,90],default=90)
    parser.add_argument('--from-render',action='store_true')
    args=parser.parse_args()
    key=os.getenv('KRX_API_KEY')
    if args.from_render:
        import requests
        from preflight_production import api_call
        base='https://api.render.com/v1/services/srv-d2ldceripnbc7383k4kg'
        token=os.environ['RENDER_API_KEY']
        with requests.Session() as session:
            service=api_call(session,'GET',base,token)
            if service['repo']!='https://github.com/okji1/financial_dashboard':raise RuntimeError('Unexpected Render repository')
            rows=api_call(session,'GET',base+'/env-vars',token,params={'limit':100})
            values={r['envVar']['key']:r['envVar']['value'] for r in rows}
            if values.get('SUPABASE_URL','').rstrip('/')!=os.environ['SUPABASE_URL'].rstrip('/'):raise RuntimeError('Unexpected database project')
            key=values.get('KRX_API_KEY')
    if not key:raise RuntimeError('KRX_API_KEY configuration missing')
    archive=HistoryAlertsStore(SharedStore())
    checked={row['trade_date'] for row in archive.checked_days(args.days)}
    today=utc_now().astimezone(KST).date()
    days=[today-datetime.timedelta(days=i) for i in range(args.days)]
    missing=[day for day in days if day.weekday()<5 and day.isoformat() not in checked]
    print('missing_weekdays',len(missing),flush=True)
    def process(day):
        items=fetch_daily(key,day)
        archive.archive(day,items,utc_now().isoformat())
        return day,len(items)
    with ThreadPoolExecutor(max_workers=2) as executor:
        for day,count in executor.map(process,missing):print('archived',day,'instruments',count,flush=True)
    print('Backfill complete. No snapshot or token changes.',flush=True)


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('Backfill failed:',type(error).__name__,file=sys.stderr)
        raise SystemExit(1)
