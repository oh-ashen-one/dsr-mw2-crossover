"""Fix the measured OAT RIFF header defect in separate task-local M9 copies."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from dsr_mw2.wav_container import repair_oat_pcm

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "foley/wpfoly_beretta9mm_reload_chamber_v2.wav": "55df1c50ab82a7f6f7e9316b9a9af8f108e02ddbc1c5ec03e2e4541e82f09d59",
    "foley/wpfoly_beretta9mm_reload_clipin_v2.wav": "5c571080438a9a79fee710e686a45194b0163944987b89e7a64632c9e44a0d75",
    "foley/wpfoly_beretta9mm_reload_clipout_v2.wav": "e3cf9f22bdebab7de2ee61e602b0f7d8ec47edbe71abe3587566a87e2c8cdca1",
    "weapons/beretta/weap_beretta_slst_3c.wav": "9a73df06fdb74f0b695e6f803db67f2b9c78d10bb2dd598c2012957e76d72ad1",
}


def main():
    source = ROOT / "converted/mw2-2009/unlinked/m9-handling-sound/sound"
    output = ROOT / "converted/mw2-2009/m9/audio"
    if output.exists() and (output.is_symlink() or not output.resolve().is_relative_to(ROOT / "converted")):
        raise ValueError("Audio output escaped the task's converted directory")
    results = []
    for name, expected in SOURCES.items():
        original = (source / name).read_bytes()
        if hashlib.sha256(original).hexdigest() != expected:
            raise ValueError("M9 source PCM export changed: " + name)
        repaired, metadata = repair_oat_pcm(original)
        destination = output / Path(name).name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink():
            raise ValueError("Audio output cannot be a symlink")
        destination.write_bytes(repaired)
        results.append({"source_name": name, "output_name": destination.name,
                        "original_export_sha256": expected, "repaired_sha256": hashlib.sha256(repaired).hexdigest(),
                        "pcm_sha256": hashlib.sha256(original[44:]).hexdigest(), **metadata})
    print(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "files": results,
                      "original_exports_preserved": True, "audio_played": False, "installed": False,
                      "scope": "RIFF header repair only; native DSR audio event integration remains unfinished"}, indent=2))


if __name__ == "__main__":
    main()
