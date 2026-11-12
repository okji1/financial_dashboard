import datetime
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gold_master import load_gold_contracts, parse_gold_contracts
from futures_api import generate_gold_futures_candidates

TODAY = datetime.date(2026, 11, 12)


def row(symbol='A88612', name='금     F 202612', prefix='31', product='KGD'):
    return prefix + symbol.ljust(9) + 'KR4XXXXXXXXX' + name.ljust(32) + '000000001' + product + '금'


class GoldMasterTests(unittest.TestCase):
    def test_current_gold_code_is_kgd_and_month_is_preserved(self):
        contracts = parse_gold_contracts(row(), today=TODAY)
        self.assertEqual(contracts[0]['symbol'], 'A88612')
        self.assertEqual((contracts[0]['year'], contracts[0]['month']), (2026, 12))
        self.assertIsNone(contracts[0]['expiry_date'])

    def test_spreads_wrong_products_and_past_months_are_excluded(self):
        text = '\n'.join([row(prefix='32'), row(product='USD'), row(name='금 F 202610'), row()])
        self.assertEqual(len(parse_gold_contracts(text, today=TODAY)), 1)

    def test_bad_month_or_symbol_fails_closed(self):
        for record in [row(name='금 F 202613'), row(symbol='BAD!')]:
            with self.assertRaises(ValueError): parse_gold_contracts(record, today=TODAY)

    def test_official_cp949_zip_and_env_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'master.zip'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('fo_com_code.mst', row().encode('cp949'))
            self.assertEqual(load_gold_contracts(path, today=TODAY)[0]['symbol'], 'A88612')
            with patch.dict('os.environ', {'KIS_GOLD_FUTURES_MASTER_PATH': str(path)}), patch('gold_master.datetime') as clock:
                clock.datetime.now.return_value.date.return_value = TODAY
                clock.date = datetime.date
                self.assertEqual(generate_gold_futures_candidates()[0]['symbol'], 'A88612')

    def test_duplicate_conflicting_codes_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_gold_contracts(row()+'\n'+row(name='금 F 202702'), today=TODAY)


    def test_old_master_is_rejected(self):
        import os
        import time
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'master.mst'
            path.write_bytes(row().encode('cp949'))
            stale = time.time() - 37 * 3600
            os.utime(path, (stale, stale))
            with self.assertRaises(ValueError):
                load_gold_contracts(path, today=TODAY)
