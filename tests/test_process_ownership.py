from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dsr_mw2 import process_ownership


class ProcessOwnershipTests(unittest.TestCase):
    def test_shared_and_similarly_named_bottles_are_not_owned(self):
        bottle = Path("/private/task-2")
        process_list = [(1, "S", "C:\\Games\\DarkSoulsRemastered.exe"),
                        (2, "S", "C:\\Steam\\Steam.exe"),
                        (3, "S", "/Applications/CrossOver/wineserver"),
                        (4, "S", "/Applications/CrossOver/wineserver"),
                        (5, "S", "UnrealEditor")]
        def lsof(args, **kwargs):
            pid = int(args[args.index("-p") + 1])
            if "cwd" in args:
                output = {1: "n/private/task-2/drive_c/Games\n", 2: "n/private/task-20/drive_c/Steam\n",
                          3: "n/tmp\n", 4: "n/tmp\n"}[pid]
            else:
                output = {3: "n/private/task-2/user.reg\n", 4: "n/private/shared/user.reg\n"}[pid]
            return SimpleNamespace(stdout=output)
        with patch.object(process_ownership, "processes", return_value=process_list), \
             patch.object(process_ownership.subprocess, "run", side_effect=lsof):
            self.assertEqual(process_ownership.bottle_processes(bottle), [1, 3])
