from pathlib import Path
import hashlib
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from dsr_mw2 import native_runtime


class NativeRuntimeTests(unittest.TestCase):
    def test_unknown_dll_or_changed_executable_is_refused_without_execution(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            exe = root / "DarkSoulsRemastered.exe"
            exe.write_bytes(b"original fixture only")
            hashes = {exe.name: hashlib.sha256(exe.read_bytes()).hexdigest()}
            with patch.object(native_runtime, "RUNTIME_HASHES", hashes):
                self.assertEqual(native_runtime.check(root), [])
                proxy = root / "dinput8.dll"
                proxy.write_bytes(b"unexpected loader fixture")
                self.assertTrue(any("binary set changed" in r for r in native_runtime.check(root)))
                proxy.unlink()
                exe.write_bytes(b"another revision")
                self.assertTrue(any("revision changed" in r for r in native_runtime.check(root)))

    def test_symlink_to_matching_external_bytes_is_refused(self):
        with TemporaryDirectory() as folder:
            root = Path(folder) / "game"
            root.mkdir()
            outside = Path(folder) / "other-session"
            outside.write_bytes(b"original fixture only")
            exe = root / "DarkSoulsRemastered.exe"
            exe.symlink_to(outside)
            with patch.object(native_runtime, "RUNTIME_HASHES", {exe.name: native_runtime.digest(outside)}):
                self.assertTrue(native_runtime.check(root))
