import unittest
from dsr_mw2.steam_manifest import installed_dsr_manifest,parse

SOURCE='''"AppState" { "appid" "570940" "Universe" "1" "StateFlags" "4" "buildid" "123" "SizeOnDisk" "99" "LastUpdated" "11"
"LastOwner" "PRIVATE-OWNER" "Token" "PRIVATE-TOKEN"
"InstalledDepots" { "570941" { "manifest" "456" "size" "99" "extra" "PRIVATE-EXTRA" } }
"UserConfig" { "language" "english" "credential" "PRIVATE-CREDENTIAL" } }'''


class ManifestTests(unittest.TestCase):
    def test_preserves_installed_depots_without_account_or_unknown_data(self):
        text=installed_dsr_manifest(SOURCE);self.assertNotIn('PRIVATE-',text)
        state=parse(text)['AppState'];self.assertEqual(state['InstalledDepots'],{'570941':{'manifest':'456','size':'99'}})
        self.assertEqual(state['UserConfig'],{'language':'english'})
        self.assertEqual(state['installdir'],'DARK SOULS REMASTERED')
        self.assertEqual(state['Universe'],'1')

    def test_rejects_incomplete_or_ambiguous_registration(self):
        for source in (SOURCE.replace('"4"','"6"'),SOURCE.replace('"size" "99"',''),SOURCE[:-1],SOURCE.replace('"buildid" "123"','"buildid" "123" "buildid" "124"')):
            with self.assertRaises(ValueError):installed_dsr_manifest(source)
