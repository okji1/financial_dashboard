"""Parse the official KIS commodity master without inventing contract codes.

The current master uses KGD for gold; the historical C header says GLD.
Only normal commodity futures (31), not spreads/options, are admitted.
"""
import datetime
import re
import time
import zipfile
from pathlib import Path
from zoneinfo import ZoneInfo

MAX_MASTER_BYTES = 5 * 1024 * 1024


def parse_gold_contracts(text, *, today=None):
    today = today or datetime.datetime.now(ZoneInfo('Asia/Seoul')).date()
    contracts = {}
    for row in text.splitlines():
        if len(row) < 67 or row[:2] != '31':
            continue
        # Match the official Python parser's character slices, including lstrip.
        suffix = row[55:].lstrip()
        if suffix[9:12] not in ('KGD', 'GLD'):
            continue
        name = row[23:55].strip()
        month = re.fullmatch(r'금\s+F\s+(\d{4})(\d{2})', name)
        symbol = row[2:11].strip()
        if not month or not re.fullmatch(r'[A-Z0-9]{4,9}', symbol):
            raise ValueError('Malformed gold futures master record')
        year, month_number = map(int, month.groups())
        datetime.date(year, month_number, 1)  # Reject invalid contract months.
        if (year, month_number) < (today.year, today.month):
            continue
        candidate = {'symbol': symbol, 'description': name, 'year': year,
                     'month': month_number, 'expiry_date': None,
                     'source': 'KIS_COMMODITY_MASTER'}
        if symbol in contracts and contracts[symbol] != candidate:
            raise ValueError('Conflicting gold futures master records')
        contracts[symbol] = candidate
    return sorted(contracts.values(), key=lambda item: (item['year'], item['month'], item['symbol']))


def load_gold_contracts(path, *, today=None):
    path = Path(path)
    metadata = path.stat()
    age = time.time() - metadata.st_mtime
    if age > 36 * 60 * 60 or age < -300:
        raise ValueError('Master file must be refreshed within 36 hours')
    if metadata.st_size > MAX_MASTER_BYTES:
        raise ValueError('Master file too large')
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            record = archive.getinfo('fo_com_code.mst')
            if record.file_size > MAX_MASTER_BYTES:
                raise ValueError('Uncompressed master too large')
            raw = archive.read(record)
    else:
        raw = path.read_bytes()
    return parse_gold_contracts(raw.decode('cp949'), today=today)


if __name__ == '__main__':
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('master_path')
    args = parser.parse_args()
    print(json.dumps(load_gold_contracts(args.master_path), ensure_ascii=False, indent=2))
