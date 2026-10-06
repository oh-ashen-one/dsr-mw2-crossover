import io
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
