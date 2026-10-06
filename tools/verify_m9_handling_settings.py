"""Verify controller constants against the exact owned/local MW2 weapon export."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / "converted/mw2-2009/unlinked/m9-reference-weapon/weapons/beretta_mp"
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != "4dbd3ef6addaae2d20608d96a252dcfde4958a24937953bb5c3694e6a377f3a3":
        raise ValueError("M9 weapon source changed")
    parts = data.decode("ascii").split("\\")
    if parts[0] != "WEAPONFILE" or len(parts) % 2 != 1:
        raise ValueError("Invalid weapon info string")
    fields = dict(zip(parts[1::2], parts[2::2], strict=True))
    if len(fields) * 2 + 1 != len(parts) or fields["fireType"] != "Single Shot":
        raise ValueError("Duplicate fields or unexpected fire type")
    header = (ROOT / "native/include/m9_handling.hpp").read_text()
    pairs = {
        "m9_capacity": ["clipSize"], "m9_fire_interval": ["fireTime"],
        "m9_reload_add": ["reloadAddTime"], "m9_reload_tactical": ["reloadTime"],
        "m9_reload_empty": ["reloadEmptyTime"], "m9_ads_time": ["adsTransInTime", "adsTransOutTime"],
        "m9_ads_fov": ["adsZoomFov"],
        "m9_view_pitch_min": ["adsViewKickPitchMin", "hipViewKickPitchMin"],
        "m9_view_pitch_max": ["adsViewKickPitchMax", "hipViewKickPitchMax"],
        "m9_view_yaw_min": ["adsViewKickYawMin", "hipViewKickYawMin"],
        "m9_view_yaw_max": ["adsViewKickYawMax", "hipViewKickYawMax"],
        "m9_view_center_speed": ["adsViewKickCenterSpeed", "hipViewKickCenterSpeed"],
    }
    verified = {}
    for name, keys in pairs.items():
        match = re.search(r"\b" + name + r"\s*=\s*(-?[0-9.]+)\b", header)
        if not match or any(float(fields[key]) != float(match[1]) for key in keys):
            raise ValueError("Controller/source constant mismatch: " + name)
        verified[name] = {"source_fields": keys, "value": float(match[1])}
    report = {"source_asset": "beretta_mp", "source_sha256": digest,
              "verified_constants": verified, "firing_mode": fields["fireType"],
              "recoil_camera_units_verified": False,
              "note": "IW4L view-kick integrator now consumes velocity impulses; DSR axis/ownership mapping remains unverified",
              "game_launched": False, "runtime_verified": False}
    (ROOT / "evidence/m9-handling-settings.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
