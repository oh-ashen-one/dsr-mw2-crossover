"""Convert owned MW2 hands/M9 into a separate native-renderer packet. No game."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from dsr_mw2.viewmodel_packet import assemble, encode, CLIPS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'converted/mw2-2009/viewmodel-v1'
from dsr_mw2.local_config import path as configured_path
MAIN = configured_path("mw2_root", ROOT / "retail/Call of Duty Modern Warfare 2") / "main"


def main():
    archives = [MAIN / ('iw_0' + n + '.iwd') for n in ('2', '3')]
    before = [(p.stat().st_size, p.stat().st_mtime_ns) for p in archives]
    packet = assemble(ROOT / 'converted/mw2-2009/unlinked', MAIN)
    data = encode(packet)
    if before != [(p.stat().st_size, p.stat().st_mtime_ns) for p in archives]:
        raise ValueError('Source archive changed during conversion')
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'm9.dsrvm').write_bytes(data)
    report = {'at': datetime.now(timezone.utc).isoformat(), 'file': str((OUT / 'm9.dsrvm').relative_to(ROOT)),
              'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'bones': packet['bones'],
              'vertices': len(packet['vertices']), 'triangles': len(packet['vertices'])//3,
              'draws': packet['draws'], 'textures': [{'width': w, 'height': h} for w,h,_ in packet['textures']],
              'clips': [{'name': name, 'seconds': c[0], 'frames': len(c[1]), 'sample_rate': 60}
                        for name,c in zip(CLIPS,packet['clips'],strict=True)],
              'sources': packet['provenance'], 'source_archives_unchanged': True,
              'pose_semantics': 'Original parent-local viewhands; relative gun pivots; authored tag_weapon attachment and tag_ads',
              'game_launched': False, 'runtime_verified': False, 'installed': False}
    (OUT / 'manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    (ROOT / 'evidence/m9-viewmodel-build.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ('file','sha256','bytes','bones','triangles','clips','runtime_verified')},indent=2))


if __name__ == '__main__':
    main()
