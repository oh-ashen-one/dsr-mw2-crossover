import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dsr_mw2 import owner_test, validation_session


class OwnerTestPackageTests(unittest.TestCase):
    def test_partial_install_restores_only_completed_steps(self):
        calls=[]
        with patch.object(owner_test,'bottle_path',return_value=Path('/private-fixture')), \
             patch.object(owner_test,'INSTALL_AUDIO_BANK',True), \
             patch.object(owner_test,'bottle_processes',return_value=[]), \
             patch.object(owner_test,'verify'), \
             patch.object(owner_test.action_trial,'mutate',side_effect=lambda x:calls.append(('actions',x))), \
             patch.object(owner_test.mpeg_audio_trial,'mutate',side_effect=ValueError('audio fixture failure')), \
             patch('tools.native_input_trial.mutate') as native:
            with self.assertRaisesRegex(ValueError,'audio fixture failure'):
                with owner_test.package():
                    self.fail('Failed setup must not enter session')
            self.assertEqual(calls,[('actions','install'),('actions','restore')])
            native.assert_not_called()

    def test_live_private_process_prevents_any_restore(self):
        calls=[]
        with patch.object(owner_test,'bottle_path',return_value=Path('/private-fixture')), \
             patch.object(owner_test,'INSTALL_AUDIO_BANK',True), \
             patch.object(owner_test,'bottle_processes',return_value=[123]), \
             patch('time.sleep'), \
             patch.object(owner_test,'verify'), \
             patch.object(owner_test.action_trial,'mutate',side_effect=lambda x:calls.append(('actions',x))), \
             patch.object(owner_test.mpeg_audio_trial,'mutate',side_effect=lambda x:calls.append(('audio',x))), \
             patch('tools.native_input_trial.mutate',side_effect=lambda x:calls.append(('native',x))):
            with self.assertRaisesRegex(RuntimeError,'still running'):
                with owner_test.package():pass
            self.assertEqual(calls,[('actions','install'),('audio','install'),('native','install')])

    def test_gates_restore_callers_environment_even_on_failure(self):
        with patch.dict(os.environ,{'DSR_MW2_GUN_TRIAL':'prior'},clear=True):
            with self.assertRaises(ValueError):
                with owner_test.gates():
                    self.assertEqual(os.environ['DSR_MW2_SESSION_TRIAL'],'owner-2h-test-v1')
                    raise ValueError('fixture')
            self.assertEqual(dict(os.environ),{'DSR_MW2_GUN_TRIAL':'prior'})

    def test_owner_marker_blocks_agent_input_before_inspecting_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            bottle=Path(directory);(bottle/owner_test.MARKER).write_text('{}')
            with patch.object(validation_session,'bottle_path',return_value=bottle), \
                 patch.object(validation_session,'guard') as guard, \
                 patch.object(validation_session,'verify') as verify:
                with self.assertRaisesRegex(RuntimeError,'agent input is disabled'):
                    validation_session.require_active()
                guard.assert_not_called();verify.assert_not_called()


class RecoverInterruptedTests(unittest.TestCase):
    def test_closed_window_leftovers_are_restored_and_marker_archived(self):
        with tempfile.TemporaryDirectory() as root:
            bottle=Path(root);(bottle/'drive_c/Games/DSR-MW2').mkdir(parents=True)
            (bottle/'drive_c/Games/DSR-MW2/xinput1_3_backend.dll').write_bytes(b'x')
            (bottle/owner_test.mpeg_audio_trial.RECEIPT).write_text('{}')
            (bottle/'.dsr-mw2-action-trial.json').write_text('{}')
            (bottle/owner_test.MARKER).write_text('{}')
            calls=[]
            with patch.object(owner_test,'guard',return_value=[]), \
                 patch.object(owner_test,'bottle_processes',return_value=[]), \
                 patch.object(owner_test,'verify',return_value={}), \
                 patch('dsr_mw2.save_banks.inspect',return_value={'active':'validation'}), \
                 patch('dsr_mw2.save_banks.select') as select, \
                 patch.object(owner_test,'atomic_write') as archive, \
                 patch.object(owner_test.action_trial,'mutate',side_effect=lambda x:calls.append(('actions',x))), \
                 patch.object(owner_test.mpeg_audio_trial,'mutate',side_effect=lambda x:calls.append(('audio',x))), \
                 patch('tools.native_input_trial.mutate',side_effect=lambda x:calls.append(('native',x))):
                self.assertEqual(owner_test.recover_interrupted(bottle),['native','audio','actions','save_bank'])
                select.assert_called_once_with(bottle,'m9')
            self.assertEqual(calls,[('native','restore'),('audio','restore'),('actions','restore')])
            archive.assert_called_once()
            self.assertFalse((bottle/owner_test.MARKER).exists())

    def test_running_session_is_never_touched(self):
        with tempfile.TemporaryDirectory() as root:
            bottle=Path(root);(bottle/'.dsr-mw2-action-trial.json').write_text('{}')
            with patch.object(owner_test,'guard',return_value=[]), \
                 patch.object(owner_test,'bottle_processes',return_value=[7]), \
                 patch('time.sleep'), \
                 patch.object(owner_test.action_trial,'mutate') as actions:
                with self.assertRaisesRegex(RuntimeError,'still running'):
                    owner_test.recover_interrupted(bottle)
            actions.assert_not_called()

    def test_clean_profile_does_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(owner_test,'bottle_processes') as processes, \
                 patch('dsr_mw2.save_banks.inspect',return_value={'active':'m9'}):
                self.assertEqual(owner_test.recover_interrupted(Path(root)),[])
            processes.assert_not_called()


class StockSoundBankTests(unittest.TestCase):
    def test_owner_package_leaves_stock_sound_bank(self):
        calls=[]
        with patch.object(owner_test,'bottle_path',return_value=Path('/private-fixture')), \
             patch.object(owner_test,'bottle_processes',return_value=[]), \
             patch.object(owner_test,'verify'), \
             patch.object(owner_test.action_trial,'mutate',side_effect=lambda x:calls.append(('actions',x))), \
             patch.object(owner_test.mpeg_audio_trial,'mutate',side_effect=lambda x:calls.append(('audio',x))), \
             patch('tools.native_input_trial.mutate',side_effect=lambda x:calls.append(('native',x))):
            with owner_test.package():pass
        self.assertNotIn(('audio','install'),calls)
        self.assertEqual(calls,[('actions','install'),('native','install'),('native','restore'),('actions','restore')])


class StaleNativeLeftoverTests(unittest.TestCase):
    def test_older_adapter_build_is_replaced_by_verified_retail(self):
        import hashlib
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as out:
            bottle=Path(root);game=bottle/'drive_c/Games/DSR-MW2';game.mkdir(parents=True)
            (game/'xinput1_3.dll').write_bytes(b'old adapter');(game/'xinput1_3_backend.dll').write_bytes(b'retail')
            retail=hashlib.sha256(b'retail').hexdigest()
            def refuse(action):raise ValueError('Preserving changed native input trial files')
            with patch('dsr_mw2.native_runtime.RUNTIME_HASHES',{'xinput1_3.dll':retail}), \
                 patch('tools.native_input_trial.OUT',Path(out)):
                owner_test.restore_native_leftover(bottle,refuse)
            self.assertEqual((game/'xinput1_3.dll').read_bytes(),b'retail')
            self.assertFalse((game/'xinput1_3_backend.dll').exists())

    def test_unverified_backend_is_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            bottle=Path(root);game=bottle/'drive_c/Games/DSR-MW2';game.mkdir(parents=True)
            (game/'xinput1_3.dll').write_bytes(b'old adapter');(game/'xinput1_3_backend.dll').write_bytes(b'unknown')
            def refuse(action):raise ValueError('Preserving changed native input trial files')
            with patch('dsr_mw2.native_runtime.RUNTIME_HASHES',{'xinput1_3.dll':'0'*64}):
                with self.assertRaisesRegex(ValueError,'not the verified retail'):
                    owner_test.restore_native_leftover(bottle,refuse)
            self.assertEqual((game/'xinput1_3.dll').read_bytes(),b'old adapter')
