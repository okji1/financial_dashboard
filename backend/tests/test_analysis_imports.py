import json
from pathlib import Path
import subprocess
import sys
import unittest

BACKEND=Path(__file__).resolve().parents[1]


class AnalysisImportsTests(unittest.TestCase):
    def test_http_analysis_import_does_not_load_optional_heavy_providers(self):
        code="import analysis,sys,json; print(json.dumps([name for name in ['numpy','pandas','cot_reports'] if name in sys.modules]))"
        output=subprocess.check_output([sys.executable,'-c',code],cwd=BACKEND,text=True)
        self.assertEqual(json.loads(output),[])

    def test_lazy_volatility_computation_preserves_constant_return_behavior(self):
        code="import analysis,json; print(json.dumps(analysis.calculate_volatility([100*1.01**day for day in range(25)])))"
        output=subprocess.check_output([sys.executable,'-c',code],cwd=BACKEND,text=True)
        self.assertEqual(json.loads(output),0.0)
