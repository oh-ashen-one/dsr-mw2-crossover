import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from dsr_mw2.mpeg_audio_trial import STOCK,digest,replace_pair,verified_payload,permitted
from dsr_mw2.install_private import atomic_write


class MpegTrialTests(unittest.TestCase):
    def test_explicit_disposable_gate_excludes_owner_modes(self):
        env={'DSR_MW2_NATIVE_INPUT_TRIAL':'validation-v1','DSR_MW2_FRAME_TRIAL':'observe-v3',
             'DSR_MW2_GUN_TRIAL':'play-v1','DSR_MW2_AUDIO_TRIAL':'mono-mpeg-v1'}
        with patch.dict('os.environ',env,clear=True):
            self.assertTrue(permitted('m9-test'))
            for mode in ('m9','stock','steam-login'):self.assertFalse(permitted(mode))
        for missing in env:
            with patch.dict('os.environ',{k:v for k,v in env.items() if k!=missing},clear=True):
                self.assertFalse(permitted('m9-test'))

    def prepare(self,root):
        data={p:('original '+p).encode() for p in STOCK}
        for p,b in data.items():
            (root/p).parent.mkdir(exist_ok=True);(root/p).write_bytes(b)
        return data,{p:digest(b) for p,b in data.items()}

    def test_partial_write_failure_restores_both_original_files(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);original,hashes=self.prepare(root);calls=[]
            def fail_once(path,data):
                calls.append(path)
                if len(calls)==2:raise OSError('Simulated second-file failure')
                atomic_write(path,data)
            with patch('dsr_mw2.mpeg_audio_trial.atomic_write',side_effect=fail_once):
                with self.assertRaises(OSError):replace_pair(root,hashes,{p:b'candidate' for p in STOCK})
            self.assertEqual(verified_payload(root,hashes),original)

    def test_changed_second_file_refuses_before_first_write(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);_,hashes=self.prepare(root);second=list(STOCK)[1];(root/second).write_bytes(b'owner change')
            with patch('dsr_mw2.mpeg_audio_trial.atomic_write') as writer:
                with self.assertRaises(ValueError):replace_pair(root,hashes,{p:b'candidate' for p in STOCK})
                writer.assert_not_called()

    def test_redirected_audio_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);_,hashes=self.prepare(root);first=list(STOCK)[0];(root/first).unlink();(root/first).symlink_to(root/list(STOCK)[1])
            with self.assertRaises(ValueError):verified_payload(root,hashes)
