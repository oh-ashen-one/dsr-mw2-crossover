"""Prepare one unchanged native animation round trip to isolate serialization."""
import hashlib
import json
from tools.havok_offline_trial import main as approved_havok
from dsr_mw2.runtime_paths import bottle_path

def main():
    _,out=approved_havok()
    from soulstruct.containers import Binder
    from soulstruct.havok.fromsoft.darksouls1r import AnimationHKX
    from tools.preserve_native_havok_types import preserve_types
    native=Binder.from_path(bottle_path()/'drive_c/Games/Dark Souls Remastered/chr/c0000_a4x.anibnd.dcx')
    entry=next(e for e in native.entries if e.entry_id==463000)
    raw=entry.get_uncompressed_data();before=AnimationHKX.from_bytes(raw)
    encoded=bytes(before);after=AnimationHKX.from_bytes(encoded)
    # Preserve TYPE exactly, which already failed as a standalone repair. Now
    # only native data serialization/order can differ, not authored motion.
    encoded=preserve_types(raw,encoded);after=AnimationHKX.from_bytes(encoded)
    assert before.animation_container.hkx_animation.data==after.animation_container.hkx_animation.data
    assert before.animation_container.hkx_binding.transformTrackToBoneIndices==after.animation_container.hkx_binding.transformTrackToBoneIndices
    target=out/'native-roundtrip';target.mkdir(exist_ok=True)
    (target/'a46_3000.hkx').write_bytes(encoded)
    report={'original_sha256':hashlib.sha256(raw).hexdigest(),'sha256':hashlib.sha256(encoded).hexdigest(),
        'original_size':len(raw),'roundtrip_size':len(encoded),'spline_payload_unchanged':True,
        'track_count':before.animation_container.hkx_animation.numberOfTransformTracks,
        'duration':before.animation_container.hkx_animation.duration,'bone_binding_unchanged':True,
        'native_TYPE_exact':True,'runtime_verified':False}
    (target/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
