import struct
import unittest
from dsr_mw2.tae32 import read_events,remove_reload_bolt_effect,remove_shared_gunshot


def fixture():
    d=bytearray(240)
    d[:8]=b'TAE \0\0\0\0'
    struct.pack_into('<II',d,8,0x1000B,len(d));struct.pack_into('<4I',d,0x10,0x40,1,0x50,0x70)
    struct.pack_into('<HH',d,0x20,2,1);struct.pack_into('<III',d,0x50,2046,1,160)
    struct.pack_into('<I',d,0x64,1);struct.pack_into('<II',d,0x80,2046,2046)
    struct.pack_into('<II',d,160,3000,168)
    struct.pack_into('<7I',d,168,1,204,0,0,2,196,232)
    struct.pack_into('<ff',d,196,0,1);struct.pack_into('<III',d,204,196,200,216)
    struct.pack_into('<IIii',d,216,128,224,1,10400)
    return bytes(d)


class TaeTests(unittest.TestCase):
    def test_remove_gunshot_leaves_projectile_and_other_sound(self):
        d=bytearray(fixture());d.extend(bytes(160))
        struct.pack_into('<I',d,12,len(d))
        struct.pack_into('<7I',d,168,3,260,0,0,2,196,232)
        for i,at in enumerate((300,328,352)):struct.pack_into('<III',d,260+12*i,196,200,at)
        struct.pack_into('<IIii',d,300,128,308,1,10400)
        struct.pack_into('<IIii',d,328,128,336,9,400)
        struct.pack_into('<II4i',d,352,2,360,55,30,300,0)
        result=remove_shared_gunshot(bytes(d));events=read_events(result)[1]
        self.assertEqual([e.kind for e in events],[128,2])
        self.assertEqual(events[0].sound,(9,400))
        self.assertEqual(result[300:],d[300:])
        with self.assertRaises(ValueError):remove_shared_gunshot(result)
        struct.pack_into('<I',d,176,1)
        with self.assertRaises(ValueError):remove_shared_gunshot(bytes(d))

    def test_remove_only_held_reload_effect_preserves_shot_and_sound(self):
        d=bytearray(fixture());d.extend(bytes(160))
        struct.pack_into('<I',d,12,len(d));struct.pack_into('<I',d,160,5502)
        struct.pack_into('<7I',d,168,3,260,0,0,2,196,232)
        for i,at in enumerate((300,328,352)):struct.pack_into('<III',d,260+12*i,196,200,at)
        struct.pack_into('<IIihhi',d,300,119,308,6000,55,0,1)
        struct.pack_into('<IIii',d,328,128,336,1,10400)
        struct.pack_into('<II4i',d,352,2,360,55,30,300,0)
        before=read_events(bytes(d))[1]
        encoded=remove_reload_bolt_effect(bytes(d),(5502,));after=read_events(encoded)[1]
        self.assertEqual([e.kind for e in after],[128,2])
        self.assertEqual(after[0].sound,(1,10400));self.assertEqual(encoded[300:],d[300:])
        self.assertEqual(after[1].parameter_offset,before[2].parameter_offset)
        bad=bytearray(d);struct.pack_into('<I',bad,176,1)
        with self.assertRaises(ValueError):remove_reload_bolt_effect(bytes(bad),(5502,))
        bad=bytearray(d);struct.pack_into('<i',bad,308,5000)
        with self.assertRaises(ValueError):remove_reload_bolt_effect(bytes(bad),(5502,))
        with self.assertRaises(ValueError):remove_reload_bolt_effect(bytes(d))

    def test_native_sound_route_and_version(self):
        identity,events=read_events(fixture())
        self.assertEqual(identity,2046);self.assertEqual(events[0].animation,3000)
        self.assertEqual(events[0].sound,(1,10400))
        for at,value in ((8,0x1000C),(12,1),(0x64,2),(160+4,1000),(204,1000),(220,1)):
            bad=bytearray(fixture());struct.pack_into('<I',bad,at,value)
            with self.assertRaises(ValueError):read_events(bytes(bad))

    def test_rejects_64bit_truncated_and_inverted_times(self):
        bad=bytearray(fixture());bad[7]=255
        with self.assertRaises(ValueError):read_events(bytes(bad))
        with self.assertRaises(ValueError):read_events(fixture()[:-4])
        bad=bytearray(fixture());struct.pack_into('<f',bad,200,-1)
        with self.assertRaises(ValueError):read_events(bytes(bad))
