import contextlib
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from dsr_mw2 import action_trial as trial


class ArmoryTrialTests(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self):
        with TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            root=Path(tmp).resolve();b=root/'bottle';out=root/'out';backup=root/'backup'
            stock=b/'drive_c/Games/Dark Souls Remastered';candidate=b/'drive_c/Games/DSR-MW2'
            expected={};originals={};native={}
            for index,name in enumerate(trial.PATHS+trial.ARMORY_PATHS):
                data=('trial-'+str(index)).encode();f=out/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(data)
                expected[name]=hashlib.sha256(data).hexdigest()
                if name==trial.ARMORY_PATHS[0]:originals[name]=None;native[name]=None;continue
                for base,prefix in ((stock,'stock-'),(candidate,'stock-' if name.startswith('chr/') else 'owner-')):
                    f=base/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes((prefix+str(index)).encode())
                originals[name]=(candidate/name).read_bytes();native[name]=trial.sha(stock/name)
            manifest={'files':expected,'stock':native}
            for name,value in [('OUT',out),('BACKUP',backup)]:stack.enter_context(patch.object(trial,name,value))
            stack.enter_context(patch.object(trial,'bottle_path',return_value=b))
            stack.enter_context(patch.object(trial,'manifest',return_value=manifest))
            stack.enter_context(patch.object(trial,'guard',return_value=[]))
            stack.enter_context(patch.object(trial,'bottle_processes',return_value=[]))
            stack.enter_context(patch.object(trial,'verify',return_value={'fixture':True}))
            stack.enter_context(patch('dsr_mw2.install_private.inspect_install',return_value={'installed':True}))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            yield b,candidate,originals

    def test_roundtrip_restores_all_owner_bytes_and_removes_only_new_model(self):
        with self.fixture() as (b,candidate,originals):
            trial.mutate('install');self.assertTrue((candidate/trial.ARMORY_PATHS[0]).exists())
            trial.mutate('restore')
            for name,data in originals.items():
                if data is None:self.assertFalse((candidate/name).exists())
                else:self.assertEqual((candidate/name).read_bytes(),data)
            self.assertFalse(trial.receipt(b).exists())

    def test_changed_installed_model_blocks_restore_and_preserves_work(self):
        with self.fixture() as (_,candidate,_):
            trial.mutate('install');p=candidate/trial.ARMORY_PATHS[0];p.write_bytes(b'changed work')
            with self.assertRaises(ValueError):trial.mutate('restore')
            self.assertEqual(p.read_bytes(),b'changed work')

    def test_failed_install_rolls_back_existing_and_new_files(self):
        with self.fixture() as (b,candidate,originals):
            write=trial.atomic_write;failed=False
            def failing(path,data):
                nonlocal failed
                if path==candidate/trial.ARMORY_PATHS[1] and not failed:
                    failed=True;raise OSError('fixture write failure')
                return write(path,data)
            with patch.object(trial,'atomic_write',side_effect=failing):
                with self.assertRaises(OSError):trial.mutate('install')
            for name,data in originals.items():
                if data is None:self.assertFalse((candidate/name).exists())
                else:self.assertEqual((candidate/name).read_bytes(),data)
            self.assertFalse(trial.receipt(b).exists())
