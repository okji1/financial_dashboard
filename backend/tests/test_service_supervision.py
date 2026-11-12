import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import run_service
from test_fastapi_migration import MemoryStore


class ServiceSupervisionTests(unittest.TestCase):
    @patch.dict('os.environ', {'DASHBOARD_COLLECTOR_MODE':'embedded'})
    def test_collector_is_stopped_if_the_web_process_dies(self):
        stop=Mock();stop.is_set.return_value=False;stop.wait.return_value=False
        collector=Mock();collector.poll.return_value=None
        web=Mock();web.poll.return_value=1
        with patch('run_service.threading.Event',return_value=stop),patch('run_service.signal.signal'),patch('run_service.SharedStore',return_value=MemoryStore()),patch('run_service.subprocess.Popen',side_effect=[collector,web]):
            self.assertEqual(run_service.main(),1)
        collector.terminate.assert_called_once();collector.wait.assert_called_once()

    @patch.dict('os.environ', {'DASHBOARD_COLLECTOR_MODE':'embedded'})
    def test_graceful_shutdown_terminates_both_children(self):
        stop=Mock();stop.is_set.return_value=False;stop.wait.return_value=True
        collector=Mock();collector.poll.return_value=None
        web=Mock();web.poll.return_value=None
        with patch('run_service.threading.Event',return_value=stop),patch('run_service.signal.signal'),patch('run_service.SharedStore',return_value=MemoryStore()),patch('run_service.subprocess.Popen',side_effect=[collector,web]):
            self.assertEqual(run_service.main(),0)
        collector.terminate.assert_called_once();web.terminate.assert_called_once()


    @patch.dict('os.environ', {}, clear=True)
    def test_development_default_never_starts_a_collector(self):
        stop=Mock();stop.is_set.return_value=False;stop.wait.return_value=True
        web=Mock();web.poll.return_value=None
        with patch('run_service.threading.Event',return_value=stop),patch('run_service.signal.signal'),patch('run_service.SharedStore',return_value=MemoryStore()),patch('run_service.subprocess.Popen',return_value=web) as popen:
            self.assertEqual(run_service.main(),0)
        popen.assert_called_once()
        self.assertNotIn('snapshot_collector.py',str(popen.call_args))

    @patch.dict('os.environ', {}, clear=True)
    def test_collector_cli_requires_explicit_opt_in(self):
        import snapshot_collector
        with patch('snapshot_collector.SharedStore') as store:
            with self.assertRaises(SystemExit):snapshot_collector.main()
            store.assert_not_called()
