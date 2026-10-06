import io
import struct
import unittest
import wave
from dsr_mw2.wav_container import repair_oat_pcm


def fixture(channels=1):
    samples = struct.pack("<" + "h" * 64, *range(64))
    header = b"RIFF" + struct.pack("<I", 48) + b"WAVEfmt "
    header += struct.pack("<IHHIIHH", 16, 1, channels, 44100, 88200 * channels, 2 * channels, 16)
    return header + b"data" + struct.pack("<I", len(samples)) + samples


class WavContainerTests(unittest.TestCase):
    def test_known_bad_header_truncates_then_repair_preserves_complete_pcm(self):
        for channels in (1, 2):
            with self.subTest(channels=channels):
                before = fixture(channels)
                with wave.open(io.BytesIO(before), "rb") as w:
                    self.assertEqual(len(w.readframes(w.getnframes())), 12)
                after, report = repair_oat_pcm(before)
                self.assertEqual(after[8:], before[8:])
                with wave.open(io.BytesIO(after), "rb") as w:
                    self.assertEqual(w.readframes(w.getnframes()), before[44:])
                self.assertTrue(report["full_payload_decoded"])
                self.assertEqual(repair_oat_pcm(after)[0], after)

    def test_unknown_discrepancy_truncation_and_wrong_format_rejected(self):
        b = fixture()
        for bad in (b[:43], b[:-2], b + b"xx", b[:4]+struct.pack("<I", 17)+b[8:], b[:20]+b"\x03\x00"+b[22:]):
            with self.subTest(size=len(bad)), self.assertRaises(ValueError):
                repair_oat_pcm(bad)
