import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from dsr_mw2 import save_banks


class SaveBankTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bottle = Path(self.temp.name)
        self.live, self.root = save_banks.paths(self.bottle)
        self.live.mkdir(parents=True)
        (self.live/'existing.sl2').write_bytes(b'preserved stock save')
        self.mock = patch.object(save_banks, 'bottle_processes', return_value=[])
        self.mock.start(); self.addCleanup(self.mock.stop)

    def test_stock_and_m9_never_share_save_bytes(self):
        save_banks.select(self.bottle, 'm9')
        self.assertEqual(list(self.live.iterdir()), [])
        self.assertEqual((self.root/'stock/existing.sl2').read_bytes(), b'preserved stock save')
        (self.live/'new.sl2').write_bytes(b'M9 progress')
        save_banks.select(self.bottle, 'stock')
        self.assertEqual((self.live/'existing.sl2').read_bytes(), b'preserved stock save')
        self.assertFalse((self.live/'new.sl2').exists())
        save_banks.select(self.bottle, 'm9')
        self.assertEqual((self.live/'new.sl2').read_bytes(), b'M9 progress')

    def test_failed_incoming_move_restores_stock(self):
        original = save_banks.os.rename
        def fail(src, dst):
            if src == self.root/'m9': raise OSError('simulated storage failure')
            return original(src, dst)
        with patch.object(save_banks.os, 'rename', side_effect=fail):
            with self.assertRaises(OSError): save_banks.select(self.bottle, 'm9')
        self.assertEqual(save_banks.inspect(self.bottle)['active'], 'stock')
        self.assertEqual((self.live/'existing.sl2').read_bytes(), b'preserved stock save')

    def test_active_process_or_session_lock_prevents_changes(self):
        with patch.object(save_banks, 'bottle_processes', return_value=[123]):
            with self.assertRaisesRegex(ValueError, 'active'): save_banks.select(self.bottle, 'm9')
        with (self.bottle/'.dsr-mw2-session.lock').open('a') as lock:
            save_banks.fcntl.flock(lock, save_banks.fcntl.LOCK_EX)
            with self.assertRaises(BlockingIOError): save_banks.select(self.bottle, 'm9')
        self.assertFalse(self.root.exists())

    def test_redirects_and_interrupted_swap_fail_closed(self):
        (self.live/'linked.sl2').symlink_to(self.live/'existing.sl2')
        with self.assertRaisesRegex(ValueError, 'redirect'): save_banks.select(self.bottle, 'm9')
        (self.live/'linked.sl2').unlink()
        self.root.mkdir(); (self.root/'pending.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Interrupted'): save_banks.select(self.bottle, 'm9')
        self.assertEqual((self.live/'existing.sl2').read_bytes(), b'preserved stock save')
