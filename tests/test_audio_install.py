import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from dsr_mw2 import install_audio as audio


class AudioInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bottle, self.stock, self.game = audio.layout(self.root)
        original = {}; changed = {}
        for i, relative in enumerate(audio.STOCK):
            a = ('native bank '+str(i)).encode(); b = ('M9 bank '+str(i)).encode()
            original[relative] = hashlib.sha256(a).hexdigest()
            changed[relative] = hashlib.sha256(b).hexdigest()
            for base, data in [(self.stock, a), (self.game, a),
                               (self.root / 'converted/dsr/m9-native-audio-candidate/mod', b)]:
                p = base / relative; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
        for key, value in [('STOCK', original), ('CANDIDATE', changed)]:
            p = patch.object(audio, key, value); p.start(); self.addCleanup(p.stop)
        p = patch.object(audio, 'bottle_processes', return_value=[])
        p.start(); self.addCleanup(p.stop)

    def hashes(self, base):
        return {p:audio.sha(base/p) for p in audio.STOCK}

    def test_observed_crashing_bank_cannot_be_reenabled(self):
        bad = dict(audio.CANDIDATE, **{'sound/frpg_main.fsb': audio.REJECTED_FSB})
        with patch.object(audio, 'CANDIDATE', bad):
            with self.assertRaisesRegex(ValueError, 'crashed native FMOD'):
                audio.install(self.root, enable=True)
        self.assertEqual(self.hashes(self.game), audio.STOCK)

    def test_enable_restore_preserves_stock_and_updates_real_files(self):
        audio.install(self.root, enable=True)
        self.assertTrue(audio.check(self.root)['enabled'])
        self.assertEqual(self.hashes(self.game), audio.CANDIDATE)
        self.assertEqual(self.hashes(self.stock), audio.STOCK)
        audio.install(self.root, enable=False)
        self.assertFalse(audio.check(self.root)['enabled'])
        self.assertEqual(self.hashes(self.game), audio.STOCK)

    def test_failure_between_banks_restores_both(self):
        original = audio.atomic_write
        calls = 0
        def fail(path, data):
            nonlocal calls
            calls += 1
            if calls == 2:raise OSError('Disk full')
            original(path, data)
        with patch.object(audio, 'atomic_write', side_effect=fail):
            with self.assertRaises(OSError):audio.install(self.root, enable=True)
        self.assertEqual(self.hashes(self.game), audio.STOCK)
        self.assertFalse((self.bottle / audio.RECEIPT).exists())

    def test_unmanaged_audio_and_forged_receipt_cannot_be_blessed(self):
        audio.install(self.root, enable=True)
        p = self.game / next(iter(audio.STOCK)); p.write_bytes(b'foreign data')
        receipt = self.bottle / audio.RECEIPT
        state = json.loads(receipt.read_text()); state['installed_hashes'][str(p.relative_to(self.game))] = audio.sha(p)
        receipt.write_text(json.dumps(state))
        self.assertFalse(audio.check(self.root)['valid'])
        with self.assertRaises(ValueError):audio.install(self.root, enable=False)
        self.assertEqual(p.read_bytes(), b'foreign data')

    def test_active_session_and_external_source_are_refused(self):
        with patch.object(audio, 'bottle_processes', return_value=[123]):
            with self.assertRaisesRegex(ValueError, 'active'):audio.install(self.root, enable=True)
        source = self.root / 'converted/dsr/m9-native-audio-candidate/mod' / next(iter(audio.STOCK))
        outside = self.root / 'outside'; source.rename(outside); source.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'escapes'):audio.install(self.root, enable=True)
        self.assertEqual(self.hashes(self.game), audio.STOCK)

    def test_session_lock_and_corrupt_receipt_preserve_files(self):
        with (self.bottle / '.dsr-mw2-session.lock').open('a+') as lock:
            audio.fcntl.flock(lock, audio.fcntl.LOCK_EX | audio.fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):audio.install(self.root, enable=True)
        (self.bottle / audio.RECEIPT).write_text('null')
        self.assertFalse(audio.check(self.root)['valid'])
        self.assertEqual(self.hashes(self.game), audio.STOCK)
