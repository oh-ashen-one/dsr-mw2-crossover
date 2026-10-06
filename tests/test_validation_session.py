from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dsr_mw2 import save_banks, validation_session as validation


class ValidationSessionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.bottle = Path(temp.name).resolve()
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(save_banks, 'bottle_processes', return_value=[]))
        self.stack.enter_context(patch.object(validation, 'bottle_processes', return_value=[]))
        self.stack.enter_context(patch.object(validation, 'guard', return_value=[]))
        self.stack.enter_context(patch.object(validation, 'authorized'))
        self.live, self.root = save_banks.paths(self.bottle)
        self.live.mkdir(parents=True)
        (self.live/'stock.sl2').write_bytes(b'stock-owner-progress')
        save_banks.select(self.bottle, 'm9')
        (self.live/'m9.sl2').write_bytes(b'm9-owner-progress')

    def test_disposable_writes_and_restore_preserve_both_owner_banks(self):
        validation.prepare(self.bottle)
        save_banks.select(self.bottle, 'validation')
        self.assertTrue(validation.verify(self.bottle, active=True)['owner_banks_unchanged'])
        (self.live/'m9.sl2').write_bytes(b'disposable-gameplay-progress')
        self.assertEqual((self.root/'m9/m9.sl2').read_bytes(), b'm9-owner-progress')
        save_banks.select(self.bottle, 'm9')
        self.assertEqual((self.live/'m9.sl2').read_bytes(), b'm9-owner-progress')
        self.assertEqual((self.root/'stock/stock.sl2').read_bytes(), b'stock-owner-progress')
        self.assertEqual((self.root/'validation/m9.sl2').read_bytes(), b'disposable-gameplay-progress')
        self.assertTrue(validation.verify(self.bottle)['owner_banks_unchanged'])

    def test_owner_sessions_and_changed_preserved_bank_reject_input(self):
        validation.prepare(self.bottle)
        with self.assertRaisesRegex(RuntimeError, 'owner play is protected'):
            validation.verify(self.bottle, active=True)
        save_banks.select(self.bottle, 'validation')
        (self.root/'m9/m9.sl2').write_bytes(b'changed-owner')
        with self.assertRaisesRegex(ValueError, 'owner bank changed'):
            validation.verify(self.bottle, active=True)

    def test_copy_failure_never_moves_the_owner_bank(self):
        with patch.object(validation.shutil, 'copytree', side_effect=OSError('copy failed')):
            with self.assertRaises(OSError): validation.prepare(self.bottle)
        self.assertEqual(save_banks.inspect(self.bottle)['active'], 'm9')
        self.assertEqual((self.live/'m9.sl2').read_bytes(), b'm9-owner-progress')
        self.assertFalse(validation.receipt_path(self.bottle).exists())

    def test_preparation_reuses_receipt_but_never_overwrites_disposable_progress(self):
        first = validation.prepare(self.bottle)
        (self.root/'validation/m9.sl2').write_bytes(b'keep-existing-test')
        self.assertEqual(validation.prepare(self.bottle), first)
        self.assertEqual((self.root/'validation/m9.sl2').read_bytes(), b'keep-existing-test')

    def test_active_process_blocks_preparation(self):
        with patch.object(validation, 'bottle_processes', return_value=[17]):
            with self.assertRaisesRegex(ValueError, 'session is active'):
                validation.prepare(self.bottle)
        self.assertFalse((self.root/'validation').exists())
