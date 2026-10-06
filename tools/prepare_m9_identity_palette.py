"""Equivalent full bone-palette encoding to isolate native weapon deformation.

No pose, geometry, weight, material or skeleton change. This is a diagnostic,
not proof that the native renderer ignores a compact per-mesh palette.
"""
import hashlib
import json
from dsr_mw2.soulstruct_tools import configure,WORKSPACE as ROOT
from tools.review_m9_attachment import read_model,geometry


def main():
    configure()
    import numpy as np
    folder=ROOT/'converted/mw2-2009/m9/havok/weapon-motion'
    proof=json.loads((folder/'weighted-muzzle-v2-report.json').read_text())
    raw=(ROOT/proof['flver_path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=proof['flver_sha256']:raise ValueError('Weighted model source changed')
    model=read_model(raw);before=geometry(model)
    for mesh in model.meshes:
        if mesh.bone_indices is None:raise ValueError('Expected compact source bone palette')
        for va in mesh.vertex_arrays:
            indices=va.array['bone_indices']
            if np.any(indices<0) or np.any(indices>=len(mesh.bone_indices)):raise ValueError('Source palette index outside bounds')
            va.array['bone_indices']=mesh.bone_indices[indices]
        mesh.bone_indices=np.arange(len(model.bones),dtype=np.int32)
    encoded=bytes(model);check=read_model(encoded)
    if geometry(check)!=before:raise ValueError('Equivalent palette changed geometry or effective influences')
    path=folder/'m9-identity-palette-v3.flver';path.write_bytes(encoded)
    report={**proof,'flver_path':str(path.relative_to(ROOT)),'flver_sha256':hashlib.sha256(encoded).hexdigest(),
        'source_flver_sha256':proof['flver_sha256'],'identity_palette':True,'effective_skinning_identical':True,
        'only_palette_representation_changed':True,'runtime_verified':False}
    (folder/'identity-palette-v3-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'sha256':report['flver_sha256'],'effective_skinning_identical':True}))


if __name__=='__main__':main()
