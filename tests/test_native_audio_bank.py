import struct
import unittest
from dsr_mw2.native_audio_bank import inspect_bank, patch_waveform_playtimes, replace_pcm


def wav():
    payload = b"\x01\x00\xff\xff" * 7
    return (b"RIFF"+struct.pack("<I",36+len(payload))+b"WAVEfmt "+
            struct.pack("<IHHIIHH",16,1,2,44100,176400,4,16)+b"data"+struct.pack("<I",len(payload))+payload)


def bank():
    header = struct.pack("<4s5I",b"FSB4",2,160,64,0x40000,0x40)+b"IDENTITY"+b"G"*16
    members = []
    for name in (b"shot.wav", b"other.wav"):
        h = bytearray(80)
        struct.pack_into("<H30s6I",h,0,80,name,5,32,0,4,0x10100220,44100)
        struct.pack_into("<H",h,62,1)
        members.append(bytes(h))
    return header+b"".join(members)+b"A"*32+b"B"*32


class AudioBankTests(unittest.TestCase):
    def test_pcm_uses_native_slot_and_preserves_other_sounds(self):
        original = bank()
        new, report = replace_pcm(original,0,"shot.wav",wav())
        samples = inspect_bank(new)
        self.assertEqual(samples[0].channels,2)
        self.assertEqual(samples[0].frames,7)
        self.assertEqual(new[samples[0].data_at:samples[0].data_at+28],wav()[44:])
        self.assertEqual(new[samples[1].data_at:],b"B"*32)
        self.assertEqual(new[24:48],original[24:48])
        self.assertEqual(report['native_padding_bytes'],4)

    def test_invalid_layout_codec_or_identity_rejected(self):
        for offset,value in ((20,2),(8,1),(12,1),(48,81)):
            bad=bytearray(bank());struct.pack_into('<I',bad,offset,value)
            with self.assertRaises(ValueError): inspect_bank(bytes(bad))
        with self.assertRaises(ValueError): replace_pcm(bank(),0,'wrong.wav',wav())
        with self.assertRaises(ValueError): replace_pcm(bank(),2,'shot.wav',wav())
        with self.assertRaises(ValueError): inspect_bank(bank()[:-1])

    def test_waveform_duration_only_and_exact_multiplicity(self):
        def string(v):return struct.pack('<I',len(v)+1)+v+b'\0'
        record=b'\0'*4+struct.pack('<I',100)+string(b'bank/test/shot.wav')+string(b'test')+struct.pack('<II',0,1000)
        original=b'FEV1'+b'UNRELATED'+record+b'KEEP'+record+b'END'
        changed,positions=patch_waveform_playtimes(original,name='bank/test/shot.wav',bank_name='test',sample_index=0,old_ms=1000,new_ms=1117,expected_count=2)
        self.assertEqual(len(changed),len(original))
        for at in positions:self.assertEqual(struct.unpack_from('<I',changed,at)[0],1117)
        restored,_=patch_waveform_playtimes(changed,name='bank/test/shot.wav',bank_name='test',sample_index=0,old_ms=1117,new_ms=1000,expected_count=2)
        self.assertEqual(restored,original)
        with self.assertRaises(ValueError):patch_waveform_playtimes(original,name='bank/test/shot.wav',bank_name='test',sample_index=0,old_ms=1000,new_ms=1117,expected_count=1)


if __name__ == '__main__':unittest.main()
