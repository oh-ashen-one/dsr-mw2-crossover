from types import SimpleNamespace
import unittest

from dsr_mw2.weapon_progression import edits, FAMILIES


class WeaponProgressionTests(unittest.TestCase):
    def rows(self):
        rows = {key: SimpleNamespace(WeaponModel=1401, WeaponCategory=11, UsesEquippedBolts=1,
                                     BasePhysicalDamage=50, BaseMagicDamage=0,
                                     BaseFireDamage=0, BaseLightningDamage=0) for key in FAMILIES}
        rows[1250400].BasePhysicalDamage = 38
        rows[1250400].BaseMagicDamage = 41
        return rows

    def test_elemental_proportions_and_all_family_requirements_are_kept(self):
        rows = self.rows()
        preset = dict(physical_damage=70, weight=1.3, required_strength=6, required_dexterity=6)
        result = dict(edits(rows, preset))
        self.assertEqual(result[1250000]["BasePhysicalDamage"], 70)
        self.assertEqual(result[1250400]["BasePhysicalDamage"], 53)
        self.assertEqual(result[1250400]["BaseMagicDamage"], 57)
        self.assertEqual(result[1250400]["BaseFireDamage"], 0)
        self.assertEqual(rows[1250000].BasePhysicalDamage, 50)
        for changes in result.values():
            self.assertEqual(changes["RequiredStrength"], 6)
            self.assertNotIn("WeaponUpgradeID", changes)
            self.assertNotIn("UpgradeOrigin0", changes)

    def test_missing_or_additional_family_row_fails_closed(self):
        for extra in (False, True):
            rows = self.rows()
            if extra:
                rows[999] = rows[1250000]
            else:
                rows.pop(1250100)
            with self.assertRaisesRegex(ValueError, "family"):
                edits(rows, {})
