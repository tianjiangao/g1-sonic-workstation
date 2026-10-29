"""Workstation-only XRoboToolkit lifecycle; never publishes robot commands."""
import fcntl
import logging
import math
import os
from pathlib import Path
import socket
import subprocess
import time

from gear_sonic.utils.teleop.body_freshness import (
    BodyFreshnessGate, FreshnessConfig, read_body_snapshot, valid_body_pose,
)

logger = logging.getLogger(__name__)


def service_pids():
    """Count the actual service executable, excluding shell launchers."""
    found = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            if (proc / 'comm').read_text().strip().startswith('RoboticsService'):
                found.append(int(proc.name))
        except OSError:
            continue
    return found


def ensure_pc_service(timeout=15.0, manage_service=True):
    pids = service_pids()
    if len(pids) > 1:
        raise RuntimeError(f'Multiple PC Services {pids}; inspect them before continuing')
    if not pids:
        if not manage_service:
            raise RuntimeError('No PC Service; start /opt/apps/roboticsservice/runService.sh once')
        log_dir = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'sonic'
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / 'pc-service.log').open('a') as log:
            subprocess.Popen(['bash', '/opt/apps/roboticsservice/runService.sh'],
                             stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        logger.info('Started PC Service; log: %s', log_dir / 'pc-service.log')
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pids = service_pids()
        if len(pids) > 1:
            raise RuntimeError(f'Multiple PC Services {pids}; no automatic termination')
        if len(pids) == 1:
            try:
                with socket.create_connection(('127.0.0.1', 60061), timeout=.2):
                    logger.info('PC Service pid=%s SDK port 60061 ready (headset not yet verified)', pids[0])
                    return
            except OSError:
                pass
        time.sleep(.1)
    raise TimeoutError('PC Service SDK port 127.0.0.1:60061 not ready; inspect service log')


class XrtSession:
    def __init__(self, sdk, timeout=60.0, poll_interval=.1, manage_service=True,
                 lock_path='default', freshness_config=None):
        self.sdk = sdk
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.manage_service = manage_service
        self.freshness_config = freshness_config or FreshnessConfig.from_env()
        self.freshness = BodyFreshnessGate(self.freshness_config)
        if timeout <= 0 or poll_interval <= 0:
            raise ValueError('XRT timeout and polling interval must be positive')
        if lock_path == 'default':
            lock_path = Path(os.environ.get('XDG_RUNTIME_DIR', f'/tmp/sonic-{os.getuid()}')) / 'sonic-xrt.lock'
        self.lock_path = Path(lock_path) if lock_path else None
        self._lock = None
        self._initialized = False
        self._readers = []

    def open(self):
        """Initialize SDK only; no readiness claim and no publishers."""
        if self._initialized:
            return self
        try:
            if self.lock_path:
                self.lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                self._lock = self.lock_path.open('a')
                try:
                    fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise RuntimeError('Another SONIC XRT session is active; do not initialize a second SDK')
            ensure_pc_service(timeout=min(self.timeout, 15.0), manage_service=self.manage_service)
            self.sdk.init()
            self._initialized = True
            return self
        except BaseException:
            self.close()
            raise

    def start(self):
        try:
            self.open()
            deadline = time.monotonic() + self.timeout
            last_log = -math.inf
            while time.monotonic() < deadline:
                try:
                    pose, timestamps, available = read_body_snapshot(self.sdk)
                    sample = self.freshness.update(pose, timestamps, available=available)
                except Exception as exc:
                    self.freshness.invalidate('sdk_snapshot_error:' + str(exc))
                    sample = None
                if sample is not None:
                    logger.info('XRT Full Body ready: all 24 joint timestamps advance; policy=%s',
                                self.freshness.stats()['config'])
                    return self
                now = time.monotonic()
                if now - last_log >= 5:
                    logger.warning('Waiting XRT Full Body: reason=%s config=%s; '
                                   'PC/PICO WORKING is distinct from per-joint freshness',
                                   self.freshness.reason, self.freshness.stats()['config'])
                    last_log = now
                time.sleep(self.poll_interval)
            raise TimeoutError('Full Body freshness not established: ' + self.freshness.reason +
                               '; no head/overall timestamp fallback. Run pico_readonly_probe.py for joint diagnostics.')
        except BaseException:
            self.close()
            raise

    def add_reader(self, reader):
        self._readers.append(reader)
        return reader

    def close(self):
        for reader in self._readers:
            reader.stop()
            thread = getattr(reader, '_thread', None)
            if thread is not None and thread.is_alive():
                raise RuntimeError('XRT reader did not stop; refusing to close SDK underneath it')
        self._readers.clear()
        try:
            if self._initialized:
                self._initialized = False
                self.sdk.close()
        finally:
            if self._lock is not None:
                self._lock.close()
                self._lock = None
