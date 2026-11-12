"""Supervise one collector and the FastAPI server in the existing Render service.

No extra paid service is created. Set DASHBOARD_COLLECTOR_MODE=external after a
separate collector service is ready. Health of provider data lives at /ready;
/health remains liveness. Flask rollback command: gunicorn app:app.
"""
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from dashboard_service import DashboardService, ServiceError
from shared_store import SharedStore, StoreUnavailable

logger = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.INFO)
    stop = threading.Event()
    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, lambda *_: stop.set())
    children = []
    exit_code = 1
    try:
        directory = Path(__file__).resolve().parent
        mode = os.environ.get('DASHBOARD_COLLECTOR_MODE', 'external')
        if mode not in ('embedded', 'external'):
            raise ValueError('Invalid DASHBOARD_COLLECTOR_MODE')
        if mode == 'embedded':
            children.append(subprocess.Popen([sys.executable, '-u', 'snapshot_collector.py'], cwd=directory))
        store = SharedStore()
        deadline = time.monotonic() + 120
        ready = False
        while not stop.is_set() and time.monotonic() < deadline:
            if any(child.poll() is not None for child in children):
                raise RuntimeError('Collector exited before startup readiness')
            try:
                service = DashboardService(store)
                service.quote()
                service.candidates()
                ready = True
                break
            except (StoreUnavailable, ServiceError):
                stop.wait(2)
        if not ready:
            raise RuntimeError('Fresh shared snapshots unavailable during startup')
        port = int(os.environ.get('PORT', '5000'))
        children.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'asgi:app',
            '--host', '0.0.0.0', '--port', str(port), '--workers', '1', '--log-level', 'info'], cwd=directory))
        while not stop.wait(1):
            if any(child.poll() is not None for child in children):
                raise RuntimeError('A supervised process exited')
        exit_code = 0
    except Exception as error:
        logger.error('service_supervision_failed error=%s', type(error).__name__)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
