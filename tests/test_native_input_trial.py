import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from dsr_mw2 import native_runtime
from dsr_mw2.launch import native_input_trial
from dsr_mw2.profile import command


class NativeInputTrialTests(unittest.TestCase):
    def test_override_uses_crossover_supported_option_before_application(self):
        exe=r'C:\Tools\original.exe'
        plain=command(exe,'argument')
        self.assertNotIn('--dll',plain)
        trial=command(exe,'argument',dll_overrides='xinput1_3=n,b')
        at=trial.index('--dll')
        self.assertEqual(trial[at+1],'xinput1_3=n,b')
        self.assertLess(at,trial.index('--ux-app'))
        self.assertEqual(trial[-2:],[exe,'argument'])
        with self.assertRaises(ValueError):command(exe,dll_overrides='unexpected=n')

    def test_trial_flag_never_enables_owner_or_stock_session(self):
        with patch.dict('os.environ',{'DSR_MW2_NATIVE_INPUT_TRIAL':'validation-v1'}):
            self.assertTrue(native_input_trial('m9-test'))
            for mode in ('m9','stock','stock-online','steam-login'):
                self.assertFalse(native_input_trial(mode))
        with patch.dict('os.environ',{'DSR_MW2_NATIVE_INPUT_TRIAL':'wrong'}):
            self.assertFalse(native_input_trial('m9-test'))

    def test_only_exact_trial_files_accepted_and_ordinary_check_refuses(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            payloads={'DarkSoulsRemastered.exe':b'fixture game','xinput1_3.dll':b'original proxy',
                      'xinput1_3_backend.dll':b'preserved controller'}
            expected={name:hashlib.sha256(data).hexdigest() for name,data in payloads.items()}
            for name,data in payloads.items():(root/name).write_bytes(data)
            with patch('tools.native_input_trial.expected',return_value=expected):
                self.assertEqual(native_runtime.check(root,input_trial=True),[])
                self.assertTrue(native_runtime.check(root))
                (root/'xinput1_3_backend.dll').write_bytes(b'changed')
                self.assertTrue(native_runtime.check(root,input_trial=True))

    def test_changed_source_receipt_fails_closed(self):
        with TemporaryDirectory() as tmp:
            with patch('tools.native_input_trial.expected',side_effect=ValueError('source changed')):
                self.assertIn('source changed',native_runtime.check(Path(tmp),input_trial=True)[0])
