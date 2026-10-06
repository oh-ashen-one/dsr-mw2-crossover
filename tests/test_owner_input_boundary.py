import unittest
from unittest.mock import patch

from tools import owned_dsr_input


class OwnerInputBoundaryTests(unittest.TestCase):
    def test_cli_cannot_send_input_or_inspect_a_game(self):
        with patch.object(owned_dsr_input, 'require_active', side_effect=RuntimeError('Owner play protected')), \
             patch.object(owned_dsr_input, 'game_processes') as processes, \
             patch.object(owned_dsr_input.ctypes, 'CDLL') as native_api:
            with self.assertRaisesRegex(RuntimeError, 'Owner play protected'):
                owned_dsr_input.main()
            processes.assert_not_called()
            native_api.assert_not_called()
