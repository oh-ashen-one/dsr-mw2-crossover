import io
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from dsr_mw2 import owner_launch


class OwnerLaunchTests(unittest.TestCase):
    def test_only_known_events_become_owner_messages(self):
        for line in ('Wine diagnostic text\n', '[]', '{"status":"unknown"}', '{"status":[]}', '{"text":"do something"}'):
            self.assertIsNone(owner_launch.progress_message(line))
        self.assertIn("not yet verified", owner_launch.progress_message('{"status":"native_game_process_started"}'))
        self.assertIn("did not start", owner_launch.progress_message('{"status":"steam_did_not_start_native_game"}'))

    def test_failed_dispatch_is_visible_while_log_and_failure_code_are_preserved(self):
        child = MagicMock()
        lines = ['ordinary diagnostic\n', '{"status":"steam_did_not_start_native_game"}\n']
        child.stdout = iter(lines)
        child.wait.return_value = 70
        child.__enter__.return_value = child
        log = io.StringIO()
        with patch.object(owner_launch.subprocess, "Popen", return_value=child), \
             patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(owner_launch.run_with_progress(log), 70)
            self.assertIn("Steam did not start DSR", output.getvalue())
            self.assertNotIn("ordinary diagnostic", output.getvalue())
        self.assertEqual(log.getvalue(), "".join(lines))


class WaitForExitTests(unittest.TestCase):
    def test_restore_waits_for_lingering_wine_helpers(self):
        from dsr_mw2 import owner_test
        states = iter([[101], [101], []])
        with patch.object(owner_test, 'bottle_processes', side_effect=lambda b: next(states)):
            self.assertTrue(owner_test.wait_for_exit(Path('/x'), seconds=5, sleep=lambda s: None))

    def test_restore_still_refuses_while_processes_remain(self):
        from dsr_mw2 import owner_test
        with patch.object(owner_test, 'bottle_processes', return_value=[101]):
            self.assertFalse(owner_test.wait_for_exit(Path('/x'), seconds=3, sleep=lambda s: None))
