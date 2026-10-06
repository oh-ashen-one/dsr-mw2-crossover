"""Package the reviewed upright models without replacing the legacy candidates."""
import hashlib
import json
from pathlib import Path

from dsr_mw2.install_private import WORKSPACE, PRESETS, checked_package
from dsr_mw2.model_candidate import read as read_model
from dsr_mw2.package_loadout import package
from dsr_mw2.audit import is_within


def main():
    review_path = WORKSPACE / 'converted/dsr/m9-upright-review/report.json'
    review = json.loads(review_path.read_text())
    for variant in ('base', 'suppressed'):
        old_name = 'm9-model-candidate' if variant == 'base' else 'm9-suppressed-model-candidate'
        original = WORKSPACE / 'converted/dsr' / old_name
        model, _ = read_model(original)
        record = next(r for r in review['variants'] if r['variant'] == variant)
        assert record['native_animation_and_texture_bytes_preserved']
        assert record['native_bind_skeleton_preserved']
        source = WORKSPACE / record['output']
        if not is_within(source, WORKSPACE / 'converted'):
            raise ValueError('Reviewed model path escapes converted data')
        payload = source.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == record['candidate_sha256']
        folder = WORKSPACE / 'converted/dsr/m9-upright-v1' / variant
        model['derivation'] = {
            'previous_model_sha256': model['output_sha256'],
            'review_sha256': hashlib.sha256(review_path.read_bytes()).hexdigest(),
            'review_relative_path': str(review_path.relative_to(WORKSPACE)),
            'correction': record['correction'],
            'weighted_global_bones': record['candidate']['weighted_global_bones'],
        }
        model['output_sha256'] = record['candidate_sha256']
        model['placement'] = 'Measured authentic grip; native move_poit weight; reviewed upright local X rotation. Runtime grip/muzzle verification pending.'
        text_report = json.loads((original / 'equipment-text/text-report.json').read_text())
        text_report['model_candidate_sha256'] = model['output_sha256']
        contents = {
            'parts/WP_A_1401.partsbnd.dcx': payload,
            'model-report.json': (json.dumps(model, indent=2)+'\n').encode(),
            'equipment-text/text-report.json': (json.dumps(text_report, indent=2)+'\n').encode(),
            'equipment-text/msg/ENGLISH/item.msgbnd.dcx': (original / 'equipment-text/msg/ENGLISH/item.msgbnd.dcx').read_bytes(),
        }
        for rel, data in contents.items():
            target = folder / rel
            if not is_within(target, WORKSPACE / 'converted/dsr/m9-upright-v1'):
                raise ValueError('Package model path escapes revision directory')
            if target.exists() and target.read_bytes() != data:
                raise ValueError('Preserving different existing revision data: '+rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    reports=[]
    for preset in PRESETS:
        variant = 'suppressed' if preset.endswith('-suppressed') else 'base'
        output = WORKSPACE / 'converted/packages/upright-v1' / preset
        report = package(WORKSPACE / 'loadouts' / (preset.removesuffix('-suppressed')+'.json'),
                         output=output, model=WORKSPACE / 'converted/dsr/m9-upright-v1' / variant)
        checked_package(WORKSPACE, preset, 'upright-v1')
        reports.append({'preset':preset,'files':report['files']})
    print(json.dumps({'revision':'upright-v1','packages':reports,'installed':False,'runtime_verified':False},indent=2))


if __name__ == '__main__':
    main()
