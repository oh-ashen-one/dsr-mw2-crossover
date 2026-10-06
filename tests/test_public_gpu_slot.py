import fcntl
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/gpu_slot.py'


class PublicGpuSlotTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        (self.root / 'locks').mkdir()
        self.lock = self.root / 'locks/perf.lock'
        self.lock.touch()
        self.marker = self.root / 'child-ran'

    def run_child(self):
        code = 'import os,pathlib; assert os.environ["GPU_SLOT_HELD"]=="perf"; pathlib.Path(os.environ["GPU_SLOT_DIR"],"child-ran").touch()'
        return subprocess.run([sys.executable, str(SCRIPT), 'perf', '--label', 'fixture',
            '--timeout', '0', '--', sys.executable, '-c', code],
            env=dict(os.environ, GPU_SLOT_DIR=str(self.root)), capture_output=True, timeout=5)

    def test_paused_coordinator_never_runs_child(self):
        (self.root / 'PAUSED').write_text('preserve another session')
        self.assertNotEqual(self.run_child().returncode, 0)
        self.assertFalse(self.marker.exists())

    def test_held_lease_never_runs_child(self):
        with self.lock.open('r+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.run_child().returncode, 75)
        self.assertFalse(self.marker.exists())

    def test_free_lease_runs_child_and_releases(self):
        self.assertEqual(self.run_child().returncode, 0)
        self.assertTrue(self.marker.exists())
        with self.lock.open('r+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
