import io
from contextlib import ExitStack, contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from dsr_mw2 import launch


class LaunchGateTests(unittest.TestCase):
    @contextmanager
    def isolated_launch(self):
        """Exercise dispatch/locks with a fake process and disposable files."""
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            root = Path(temp).resolve()
            bottle = root / "bottle"
            steam = bottle / "drive_c/Steam"
            (steam / "steamapps/common").mkdir(parents=True)
            (root / "tooling-local").mkdir()
            stock = bottle / "drive_c/Games/Dark Souls Remastered"
            candidate = bottle / "drive_c/Games/DSR-MW2"
            stock.mkdir(parents=True)
            candidate.mkdir()
            alias = steam / "steamapps/common/DARK SOULS REMASTERED"
            alias.symlink_to(stock, target_is_directory=True)
            for key, value in {"WORKSPACE": root, "BOTTLE": bottle, "STEAM": steam}.items():
                stack.enter_context(patch.object(launch, key, value))
            stack.enter_context(patch.dict(launch.os.environ, {"GPU_SLOT_HELD": "perf", "GPU_SLOT_DIR": str(launch.GPU)}))
            stack.enter_context(patch.object(launch, "environment", return_value={}))
            stack.enter_context(patch.object(launch, "bottle_processes", return_value=[]))
            stack.enter_context(patch.object(launch, "steam_processes", return_value=[999]))
            check = stack.enter_context(patch.object(launch, "preflight", return_value={"blockers": []}))
            config = stack.enter_context(patch.object(launch, "configure_steam_mode"))
            stack.enter_context(patch.object(launch, "select_save_bank"))
            start = stack.enter_context(patch.object(launch.subprocess, "Popen"))
            start.return_value.pid = 999
            start.return_value.poll.return_value = 0
            start.return_value.wait.return_value = 0
            stack.enter_context(patch("sys.stdout", new_callable=io.StringIO))
            yield alias, check, config, start

    def test_steam_success_without_game_returns_failure_and_shuts_down_own_client(self):
        with self.isolated_launch() as (alias, _, config, start), \
             patch.object(launch, "watch_game", return_value=False):
            self.assertEqual(launch.run_inside("m9"), 70)
            self.assertEqual(start.call_count, 2)
            self.assertEqual(start.call_args_list[0].args[0][-2:], ["-applaunch", "570940"])
            self.assertEqual(start.call_args.args[0][-1], "-shutdown")
            self.assertEqual(alias.resolve(), launch.BOTTLE / "drive_c/Games/DSR-MW2")
            config.assert_called_once_with(launch.STEAM / "config/loginusers.vdf", offline=True)

    def test_sign_in_restores_stock_library_and_save_bank_before_steam(self):
        with self.isolated_launch() as (alias, _, _, start), \
             patch.object(launch, 'select_save_bank') as saves:
            alias.unlink(); alias.symlink_to(launch.BOTTLE/'drive_c/Games/DSR-MW2')
            def launched(*args, **kwargs):
                saves.assert_called_once_with(launch.BOTTLE, 'stock')
                self.assertEqual(alias.resolve(), launch.BOTTLE/'drive_c/Games/Dark Souls Remastered')
                client=Mock();client.pid=999;client.poll.return_value=0;client.wait.return_value=0
                return client
            start.side_effect=launched
            self.assertEqual(launch.run_inside('steam-login'),0)

    def test_no_new_steam_client_is_started_to_shutdown_an_exited_one(self):
        with self.isolated_launch() as (_, _, _, start), \
             patch.object(launch, 'watch_game', return_value=False), \
             patch.object(launch, 'steam_processes', return_value=[]):
            self.assertEqual(launch.run_inside('m9'),70)
            self.assertEqual(start.call_count,1)

    def test_shutdown_dispatch_must_exit_before_session_lock_is_released(self):
        with self.isolated_launch() as (_, _, _, start), \
             patch.object(launch, 'watch_game', return_value=False), \
             patch.object(launch.time, 'sleep') as sleep:
            client = Mock(); client.pid = 999; client.poll.return_value = 0; client.wait.return_value = 0
            shutdown = Mock(); shutdown.poll.side_effect = [None, 0]
            start.side_effect = [client, shutdown]
            self.assertEqual(launch.run_inside('m9'), 70)
            sleep.assert_called_once_with(3)

    def test_invalid_library_alias_never_changes_steam_flags_or_starts(self):
        with self.isolated_launch() as (alias, _, config, start):
            alias.unlink()
            alias.symlink_to("/another/session")
            with self.assertRaisesRegex(ValueError, "library alias"):
                launch.run_inside("m9")
            config.assert_not_called()
            start.assert_not_called()

    def test_changed_preflight_is_caught_after_locking(self):
        with self.isolated_launch() as (_, check, config, start):
            check.side_effect = [{"blockers": []}, {"blockers": ["new private process"]}]
            self.assertEqual(launch.run_inside("m9"), 75)
            config.assert_not_called()
            start.assert_not_called()

    def test_slow_private_shutdown_reports_progress_and_retains_session_lock(self):
        clock = [0]
        def tick(seconds):
            clock[0] += seconds
            with (launch.BOTTLE / ".dsr-mw2-session.lock").open("a+") as other:
                with self.assertRaises(BlockingIOError):
                    launch.fcntl.flock(other, launch.fcntl.LOCK_EX | launch.fcntl.LOCK_NB)
        with self.isolated_launch(), \
             patch.object(launch, "watch_game", return_value=False), \
             patch.object(launch, "bottle_processes", side_effect=[[888]] * 12 + [[]]), \
             patch.object(launch.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(launch.time, "sleep", side_effect=tick), \
             patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(launch.run_inside("m9"), 70)
            self.assertEqual(output.getvalue().count("waiting_for_private_shutdown"), 1)

    def test_async_startup_survives_initial_empty_process_table(self):
        clock = [0]
        def tick(seconds): clock[0] += seconds
        child = Mock()
        child.poll.return_value = None
        with patch.object(launch, "game_processes", side_effect=[[], [], [321], [321], []]), \
             patch.object(launch, "bottle_processes", return_value=[]), \
             patch.object(launch.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(launch.time, "sleep", side_effect=tick), \
             patch("sys.stdout", new_callable=io.StringIO):
            self.assertTrue(launch.watch_game(child))

    def test_startup_without_game_is_reported_unverified(self):
        clock = [0]
        def tick(seconds): clock[0] += seconds
        child = Mock()
        child.poll.return_value = None
        with patch.object(launch, "game_processes", return_value=[]), \
             patch.object(launch, "bottle_processes", return_value=[123]), \
             patch.object(launch.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(launch.time, "sleep", side_effect=tick):
            self.assertFalse(launch.watch_game(child, timeout=9))
            self.assertEqual(clock[0], 9)

    def test_m9_always_uses_offline_sandbox(self):
        self.assertEqual(launch.network_wrapper("m9"), ["/usr/bin/sandbox-exec", "-f", str(launch.SANDBOX)])
        self.assertEqual(launch.network_wrapper("stock-online"), [])
        self.assertTrue(launch.network_wrapper("stock"))
        self.assertEqual(launch.network_wrapper('m9-test'), launch.network_wrapper('m9'))

    def test_validation_dispatch_selects_disposable_then_restores_owner_bank(self):
        with self.isolated_launch() as (alias, _, config, start), \
             patch.object(launch, 'watch_game', return_value=False), \
             patch.object(launch, 'select_save_bank') as saves, \
             patch('dsr_mw2.validation_session.verify', return_value={'owner_banks_unchanged': True}):
            self.assertEqual(launch.run_inside('m9-test'), 70)
            self.assertEqual([call.args[1] for call in saves.call_args_list], ['validation', 'm9'])
            self.assertEqual(alias.resolve(), launch.BOTTLE/'drive_c/Games/DSR-MW2')
            config.assert_called_once_with(launch.STEAM/'config/loginusers.vdf', offline=True)

    def test_only_exact_dsr_owner_reservation_is_accepted(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(launch, "GPU", Path(temp)):
            pause = Path(temp) / "PAUSED"
            self.assertFalse(launch.owner_reserved())
            pause.write_text("OWNER PAUSE: another game\n")
            self.assertFalse(launch.owner_reserved())
            pause.write_text(launch.OWNER_RESERVATION)
            self.assertTrue(launch.owner_reserved())
            pause.write_text(launch.OWNER_RESERVATION + "coordinator changed this\n")
            self.assertFalse(launch.owner_reserved())

    def test_owner_launch_retains_shared_lock_and_pause(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(launch, "GPU", Path(temp)):
            root = Path(temp)
            (root / "locks").mkdir()
            (root / "holders").mkdir()
            (root / "locks/perf.lock").touch()
            (root / "PAUSED").write_text(launch.OWNER_RESERVATION)
            def child(*args, **kwargs):
                with (root / "locks/perf.lock").open("a") as other:
                    with self.assertRaises(BlockingIOError):
                        launch.fcntl.flock(other, launch.fcntl.LOCK_EX | launch.fcntl.LOCK_NB)
                self.assertEqual((root / "PAUSED").read_text(), launch.OWNER_RESERVATION)
                self.assertEqual(kwargs["env"]["GPU_SLOT_HELD"], "perf")
                self.assertEqual(len(list((root / "holders").iterdir())), 1)
                return type("Result", (), {"returncode": 0})()
            with patch.object(launch, "preflight", return_value={"blockers": []}), \
                 patch.object(launch, "gpu_percent", return_value=0), \
                 patch.object(launch.time, "monotonic", side_effect=[0, 0, 0, 13]), \
                 patch.object(launch.time, "sleep"), \
                 patch.object(launch.subprocess, "run", side_effect=child), \
                 patch.object(launch.subprocess, "check_output", return_value="start"):
                self.assertEqual(launch.run_reserved("stock"), 0)
            self.assertEqual(list((root / "holders").iterdir()), [])
            self.assertEqual((root / "PAUSED").read_text(), launch.OWNER_RESERVATION)

    def test_sign_in_only_does_not_use_the_game_slot_launcher(self):
        with patch("sys.argv", ["launch", "--mode", "steam-login"]), \
             patch.object(launch, "preflight", return_value={"blockers": []}), \
             patch.object(launch, "run_inside", return_value=0) as sign_in, \
             patch.object(launch.subprocess, "run") as gpu_launcher, \
             patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(launch.main(), 0)
            sign_in.assert_called_once_with("steam-login")
            gpu_launcher.assert_not_called()

    def test_paused_launch_does_not_start_or_install_anything(self):
        report = {"blockers": ["shared pause"], "game_launched": False}
        with patch("sys.argv", ["launch", "--preset", "m9-low-damage"]), \
             patch.object(launch, "preflight", return_value=report), \
             patch.object(launch, "install") as install, \
             patch.object(launch.subprocess, "run") as run, \
             patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(launch.main(), 75)
            install.assert_not_called()
            run.assert_not_called()

    def test_inner_launch_refuses_a_forged_slot_context(self):
        with patch.object(launch, "preflight", return_value={"blockers": []}), \
             patch.dict(launch.os.environ, {}, clear=True), \
             patch.object(launch.subprocess, "Popen") as start, \
             patch("sys.stdout", new_callable=io.StringIO):
            with self.assertRaisesRegex(ValueError, "slot is missing"):
                launch.run_inside("m9")
            start.assert_not_called()

    def test_read_only_check_never_starts_a_game(self):
        with patch("sys.argv", ["launch", "--check"]), \
             patch.object(launch, "preflight", return_value={"blockers": []}), \
             patch.object(launch.subprocess, "run") as run, \
             patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(launch.main(), 0)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
