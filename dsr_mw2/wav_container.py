"""Repair the measured OAT PCM RIFF-size bug without modifying sample bytes."""
import io
import struct
import wave


def repair_oat_pcm(raw: bytes) -> tuple[bytes, dict]:
    if len(raw) < 44 or len(raw) > 32 * 1024 * 1024:
        raise ValueError("Invalid PCM export size")
    if raw[:4] != b"RIFF" or raw[8:16] != b"WAVEfmt " or raw[36:40] != b"data":
        raise ValueError("Not the reviewed OAT PCM container layout")
    riff_size = struct.unpack_from("<I", raw, 4)[0]
    fmt_size, encoding, channels, rate, byte_rate, alignment, bits = struct.unpack_from("<IHHIIHH", raw, 16)
    data_size = struct.unpack_from("<I", raw, 40)[0]
    if fmt_size != 16 or encoding != 1 or channels not in (1, 2) or bits != 16 or rate != 44100:
        raise ValueError("Unexpected M9 PCM format")
    if alignment != channels * 2 or byte_rate != rate * alignment:
        raise ValueError("Invalid PCM alignment/rate")
    if data_size != len(raw) - 44 or data_size % alignment or not data_size:
        raise ValueError("Truncated or misaligned PCM payload")
    if riff_size not in (48, len(raw) - 8):
        raise ValueError("Unknown RIFF-size discrepancy")
    result = bytearray(raw)
    struct.pack_into("<I", result, 4, len(raw) - 8)
    result = bytes(result)
    if result[8:] != raw[8:]:
        raise ValueError("PCM repair changed format/sample bytes")
    with wave.open(io.BytesIO(result), "rb") as decoded:
        payload = decoded.readframes(decoded.getnframes())
        if payload != raw[44:]:
            raise ValueError("PCM payload does not survive standard WAV decoding")
        report = {"channels": channels, "sample_rate": rate, "sample_bytes": bits // 8,
                  "samples": decoded.getnframes(), "seconds": decoded.getnframes() / rate,
                  "source_riff_size": riff_size, "fixed_riff_size": len(raw) - 8,
                  "pcm_payload_bytes": len(payload), "pcm_payload_unchanged": True,
                  "full_payload_decoded": True}
    return result, report
