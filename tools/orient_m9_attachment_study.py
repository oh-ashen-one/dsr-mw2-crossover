"""Stage a proper half-turn about the M9 barrel axis for DSR's right hand.

CPU-only, source-asset and installed-prototype preserving. The target follows
the inspected DSR attachment convention and still requires native playback.
"""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from dsr_mw2.animation_pose import rotate
from dsr_mw2.skin_geometry import point, undo
from dsr_mw2.soulstruct_tools import configure
from tools.review_m9_attachment import read_model, native_rig, geometry, measure, require

ROOT=Path(__file__).resolve().parents[1]


def main():
    configure()
    import numpy as np
    from soulstruct.containers import Binder
    from soulstruct.utilities.maths import AABB, Vector3
    proof=json.loads((ROOT/'evidence/m9-attachment-review.json').read_text())
    results=[]
    turn=(1,0,0,0)
    def box(points):
        return AABB(Vector3(tuple(min(p[a] for p in points) for a in range(3))),
                    Vector3(tuple(max(p[a] for p in points) for a in range(3))))
    for source in proof['variants']:
        original=(ROOT/source['output']).read_bytes()
        require(hashlib.sha256(original).hexdigest()==source['candidate_sha256'],'Attachment input changed')
        binder=Binder.from_bytes(original)
        entry=next(e for e in binder.entries if e.path.endswith('.flver'))
        model=read_model(entry.get_uncompressed_data())
        before=copy.deepcopy(model)
        _,_,binds=native_rig(model)
        for mesh in model.meshes:
            array=mesh.vertex_arrays[0].array
            # Proper rotation has determinant +1: preserve triangle winding
            # and tangent handedness; rotate positions/normals/tangent xyz.
            for field in ('position','normal',*[n for n in array.dtype.names if n.startswith('tangent_')]):
                array[field][:,1:3]*=-1
            if mesh.uses_bounding_boxes:
                mesh.bounding_box=box(array['position'])
        positions,influences,_=geometry(model)
        require(all(w==((1,1.0),) for w in influences),'Expected rigid attachment bone')
        model.bounding_box=box(positions)
        model.bones[1].bounding_box=box([point(undo(binds[1]),p) for p in positions])
        for dummy in model.dummies:
            parent=binds[dummy.parent_bone_index]
            dummy.translate=Vector3(point(undo(parent),rotate(turn,point(parent,tuple(dummy.translate)))))
            for name in ('forward','upward'):
                world=rotate(parent.rotation,tuple(getattr(dummy,name)))
                setattr(dummy,name,Vector3(rotate(undo(parent).rotation,rotate(turn,world))))
        entry.set_uncompressed_data(bytes(model))
        encoded=bytes(binder)
        decoded=Binder.from_bytes(encoded)
        checked=read_model(next(e for e in decoded.entries if e.path.endswith('.flver')).get_uncompressed_data())
        for old,new in zip(Binder.from_bytes(original).entries,decoded.entries,strict=True):
            require((old.path,old.entry_id,old.flags)==(new.path,new.entry_id,new.flags),'Binder identity changed')
            if not old.path.endswith('.flver'):require(old.data==new.data,'Animation/texture payload changed')
        for old,new in zip(before.meshes,checked.meshes,strict=True):
            a=old.vertex_arrays[0].array;b=new.vertex_arrays[0].array
            for field in a.dtype.names:
                expected=a[field].copy()
                if field in ('position','normal') or field.startswith('tangent_'):expected[:,1:3]*=-1
                require(np.array_equal(expected,b[field]),'Serialized vertex field changed unexpectedly: '+field)
            require(old.material==new.material and np.array_equal(old.bone_indices,new.bone_indices),'Material or weights changed')
            for x,y in zip(old.face_sets,new.face_sets,strict=True):
                require(np.array_equal(x.vertex_indices,y.vertex_indices),'Triangle winding changed')
        for old,new in zip(before.bones,checked.bones,strict=True):
            for name in ('name','translate','rotate','scale','parent_bone_index','child_bone_index','usage_flags'):
                require(getattr(old,name)==getattr(new,name),'Native bind skeleton changed')
        for p in geometry(checked)[0]:
            require(all(lo-1e-6<=v<=hi+1e-6 for lo,v,hi in zip(checked.bounding_box.min,p,checked.bounding_box.max)),
                    'Model bounds exclude vertex')
            local=point(undo(binds[1]),p)
            require(all(lo-1e-6<=v<=hi+1e-6 for lo,v,hi in zip(checked.bones[1].bounding_box.min,local,checked.bones[1].bounding_box.max)),
                    'Bone bounds exclude vertex')
        muzzle=rotate(turn,tuple(source['source_muzzle_in_mesh_space_m']))
        measured=measure(checked,muzzle,driving_bone=1)
        require(max(p['muzzle_to_dummy_distance_m'] for p in measured['poses'])<1e-6,'Muzzle attachment separated')
        require(max(p['muzzle_to_dummy_forward_angle_degrees'] for p in measured['poses'])<.001,'Muzzle direction changed')
        path=ROOT/'converted/dsr/m9-upright-review'/source['variant']/'parts/WP_A_1401.partsbnd.dcx'
        require(path.resolve().is_relative_to(ROOT/'converted') and not path.is_symlink(),'Output escaped task')
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(encoded)
        results.append({'variant':source['variant'],'input_sha256':source['candidate_sha256'],
            'candidate_sha256':hashlib.sha256(encoded).hexdigest(),'output':str(path.relative_to(ROOT)),
            'source_muzzle_in_mesh_space_m':muzzle,'candidate':measured,
            'correction':'Proper 180-degree rotation around local X through original grip; winding/tangent w retained',
            'native_animation_and_texture_bytes_preserved':True,'native_bind_skeleton_preserved':True,
            'installed':False,'runtime_verified':False})
    report={'at':datetime.now(timezone.utc).isoformat(),'variants':results,
        'reference':'https://github.com/Meowmaritus/DSAnimStudio/blob/f1bff06cd422de991b0a0fa8a2da81db43417318/DSAnimStudioNETCore/NewChrAsm.cs#L699',
        'reason':'CPU character/weapon preview exposed inverted grip after applying actual DSR right-hand attachment flips',
        'game_launched':False,'renderer_used':False,'installed':False,'runtime_verified':False,
        'limits':['Reference application not executed; native game acceptance still unverified',
                  'Rigid world mesh; no slide/magazine articulation or native projectile-origin proof']}
    destination=ROOT/'converted/dsr/m9-upright-review/report.json'
    destination.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'report':str(destination),'variants':[{k:v[k] for k in ('variant','candidate_sha256')} for v in results]},indent=2))


if __name__=='__main__':main()
