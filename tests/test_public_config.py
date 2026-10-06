import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from dsr_mw2 import local_config


class PublicConfigTests(unittest.TestCase):
    def test_fresh_checkout_has_no_inherited_authorization(self):
        with patch.object(local_config, 'read', return_value={}):
            for capability in ('allow_owner_test', 'allow_agent_gameplay', 'allow_offline_conversion'):
                with self.assertRaisesRegex(RuntimeError, 'Local authorization missing'):
                    local_config.require_permission(capability)

    def test_owner_test_does_not_grant_agent_gameplay(self):
        with patch.object(local_config, 'read', return_value={'allow_owner_test': True}):
            local_config.require_permission('allow_owner_test')
            with self.assertRaises(RuntimeError):
                local_config.require_permission('allow_agent_gameplay')

    def test_redirected_config_and_wrong_schema_are_rejected(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / 'local-config.json'
            config.write_text(json.dumps({'version': 2}))
            with self.assertRaises(ValueError): local_config.read(root)
            config.unlink()
            target = root / 'external.json'
            target.write_text(json.dumps({'version': 1}))
            config.symlink_to(target)
            with self.assertRaises(ValueError): local_config.read(root)
