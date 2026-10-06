import unittest
from unittest.mock import patch
from dsr_mw2.profile import command, environment


class PrivateGraphicsLaunchTests(unittest.TestCase):
    def test_backend_override_is_explicit_and_preserves_input_route(self):
        args=command('Steam.exe','-applaunch','570940',
                     dll_overrides='xinput1_3=n,b',graphics_backend='d3dmetal')
        self.assertEqual(args[args.index('--env')+1],'CX_GRAPHICS_BACKEND=d3dmetal')
        self.assertEqual(args[args.index('--dll')+1],'xinput1_3=n,b')
        self.assertEqual(args[-3:],['Steam.exe','-applaunch','570940'])

    def test_default_launch_and_host_environment_are_unchanged(self):
        self.assertNotIn('--env',command('tool.exe'))
        with patch.dict('os.environ',{'CX_GRAPHICS_BACKEND':'unrelated-host-value'}):
            self.assertNotIn('CX_GRAPHICS_BACKEND',environment())

    def test_arbitrary_environment_injection_is_rejected(self):
        with self.assertRaises(ValueError):command('tool.exe',graphics_backend='d3dmetal OTHER=value')
