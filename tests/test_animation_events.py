import unittest

from dsr_mw2.animation_events import classify_events, note_maps, weapon_fields
from dsr_mw2.xanim import Animation


class AnimationEventsTests(unittest.TestCase):
    def test_sound_and_rumble_never_confused_or_resolved_by_name(self):
        maps = note_maps({'notetrackSoundMap': 'clip_sound gun_clip_alias', 'notetrackRumbleMap': 'pulse hand_pulse'})
        clip = Animation(17, 60, 30, False, 1, (), (('clip_sound', 32), ('pulse', 35)))
        cues = classify_events(clip, maps)
        self.assertEqual([e['kind'] for e in cues], ['sound_alias', 'rumble_alias'])
        self.assertAlmostEqual(cues[0]['normalized_phase'], 32/60)
        self.assertAlmostEqual(cues[0]['source_seconds'], 32/30)
        self.assertIsNone(cues[0]['resolved_audio_file'])
        self.assertIsNone(cues[0]['native_event_id'])

    def test_unknown_cues_and_ambiguous_maps_fail(self):
        with self.assertRaises(ValueError):
            note_maps({'notetrackSoundMap': 'same audio', 'notetrackRumbleMap': 'same rumble'})
        with self.assertRaises(ValueError):
            classify_events(Animation(17, 3, 30, False, 1, (), (('unknown', 1),)), {})

    def test_weapon_duplicate_keys_fail_before_mapping(self):
        self.assertEqual(weapon_fields(b'WEAPONFILE\\key\\value'), {'key': 'value'})
        for data in (b'WEAPONFILE\\key\\value\\key\\different', b'WEAPONFILE\\key', b'OTHER'):
            with self.assertRaises(ValueError):
                weapon_fields(data)


if __name__ == '__main__':
    unittest.main()
