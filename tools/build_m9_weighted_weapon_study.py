"""Pair the authentic M9 body/slide/hammer/magazine with the local HKX studies.

CPU-only, uninstalled authoring study. Keeps the installed rigid M9 untouched.
Separate sight, silencer and knife materials are explicitly excluded, not
replaced by invented textures. Native action/visibility/contact work is pending.
"""
import copy
import hashlib
import json
import math
from pathlib import Path

from dsr_mw2.animation_pose import Transform
from dsr_mw2.animation_retarget import OrthogonalBasis
from dsr_mw2.skin_geometry import point, skin, undo, world_transforms, mesh_displacement
from dsr_mw2.xmodel_geometry import read
from tools.build_m9_weapon_motion_study import pinned
from tools.havok_offline_trial import main as trial
from tools.review_m9_attachment import native_rig, read_model, geometry
from tools.correct_m9_winding import facing

ROOT=Path(__file__).resolve().parents[1]


def main():
    _,out=trial()
    import numpy as np
    from soulstruct.containers import Binder, TPF
    from soulstruct.flver.bone import FLVERBone
    from soulstruct.flver.vertex_array import VertexArray
    from soulstruct.utilities.maths import Matrix3, Vector3
    from soulstruct.havok.fromsoft.darksouls1r import SkeletonHKX, AnimationHKX

    folder=out/'weapon-motion'
    motion=json.loads((folder/'report.json').read_text())
    source=ROOT/'converted/mw2-2009/unlinked/m9-handling-models/model_export/viewmodel_beretta_lod0.xmodel_export'
    model=read(pinned(source,motion['source_model_sha256']).decode())
    native=ROOT/'profiles/dsr-mw2/drive_c/Games/Dark Souls Remastered/parts/WP_A_1401.partsbnd.dcx'
    binder=Binder.from_bytes(pinned(native,motion['native_binder_sha256']))
    flver=read_model(next(e for e in binder.entries if e.path.endswith('.flver')).get_uncompressed_data())
    native_count=len(flver.bones)
    if native_count!=7:raise ValueError('Native FLVER skeleton changed')
    native_parents,native_local,native_world=native_rig(flver)
    attach=next(i for i,b in enumerate(flver.bones) if b.name=='Model_Dmy')
    skeleton_raw=pinned(folder/'m9-extended-weapon-skeleton.hkx',motion['skeleton_sha256'])
    hk=SkeletonHKX.from_bytes(skeleton_raw).skeleton.skeleton
    hk_names=[b.name for b in hk.bones]
    if len(hk_names)!=len(set(hk_names)):raise ValueError('Ambiguous HKX bone names')
    hk_local=[Transform(tuple(p.rotation),tuple(p.translation[:3])) for p in hk.referencePose]
    # FLVER has seven native bones in a different order from the six HKX
    # bones. Append by exact name/parent, never by assuming matching indices.
    for index,bone in enumerate(model.bones):
        h=hk_names.index(bone.name);p=hk_local[h]
        columns=[point(Transform(p.rotation,(0,0,0)),a) for a in ((1,0,0),(0,1,0),(0,0,1))]
        rotate=Matrix3(np.asarray(columns).T).to_euler_angles_rad(order='xzy')
        flver.bones.append(FLVERBone(name=bone.name,translate=Vector3(p.translation),rotate=rotate,
                                   parent_bone_index=attach if bone.parent<0 else native_count+bone.parent))
    # Keep existing native parent/transform data; reconnect sibling metadata.
    for bone in flver.bones:
        bone.child_bone_index=bone.previous_sibling_bone_index=bone.next_sibling_bone_index=-1
    for parent in range(-1,len(flver.bones)):
        children=[i for i,b in enumerate(flver.bones) if b.parent_bone_index==parent]
        if parent>=0 and children:flver.bones[parent].child_bone_index=children[0]
        for i,index in enumerate(children):
            flver.bones[index].previous_sibling_bone_index=children[i-1] if i else -1
            flver.bones[index].next_sibling_bone_index=children[i+1] if i+1<len(children) else -1
    parents,local,binds=native_rig(flver)
    if parents[:native_count]!=native_parents or local[:native_count]!=native_local:
        raise ValueError('Original FLVER parent/transform changed')
    basis=OrthogonalBasis(((-1,0,0),(0,0,1),(0,-1,0)))
    scale=motion['unit_scale_m'];grip=motion['provisional_grip_source_inches']
    template=flver.meshes[0];mesh=copy.deepcopy(template)
    corners=[];faces=[];mapping={}
    for face in model.faces:
        if face.material!=0:continue
        if len({c.vertex for c in face.corners})<3:continue
        triangle=[]
        for c in face.corners:
            if c not in mapping:mapping[c]=len(corners);corners.append(c)
            triangle.append(mapping[c])
        # This XMODEL_EXPORT source differs from the earlier world-mesh route.
        # Measure the serialized result below instead of assuming its winding.
        faces.append(tuple(reversed(triangle)))
    if model.materials[0].name!='mc/mtl_weapon_beretta':raise ValueError('Body material identity changed')
    vertices=np.zeros(len(corners),dtype=template.vertex_arrays[0].array.dtype)
    source_influences=[]
    for i,c in enumerate(corners):
        position=basis.vector(tuple((v-g)*scale for v,g in zip(model.positions[c.vertex],grip)))
        vertices['position'][i]=point(native_world[attach],position)
        normal=basis.vector(c.normal)
        normal=point(Transform(native_world[attach].rotation,(0,0,0)),normal)
        vertices['normal'][i]=np.asarray(normal)/np.linalg.norm(normal)
        vertices['uv_0'][i]=c.uv
        vertices['color_0'][i]=c.color
        influence=model.influences[c.vertex];source_influences.append(influence)
        for slot,(bone,weight) in enumerate(influence):
            vertices['bone_indices'][i,slot]=bone
            vertices['bone_weights'][i,slot]=weight
    tangents=np.zeros((len(vertices),3));bitangents=np.zeros_like(tangents)
    for triangle in faces:
        a,b,c=triangle
        p=vertices['position'][b]-vertices['position'][a];q=vertices['position'][c]-vertices['position'][a]
        uv=vertices['uv_0'][b]-vertices['uv_0'][a];st=vertices['uv_0'][c]-vertices['uv_0'][a]
        determinant=uv[0]*st[1]-uv[1]*st[0]
        if abs(determinant)>1e-8:
            tangents[list(triangle)]+=(p*st[1]-q*uv[1])/determinant
            bitangents[list(triangle)]+=(q*uv[0]-p*st[0])/determinant
    for i in range(len(vertices)):
        normal=vertices['normal'][i];t=tangents[i]-normal*np.dot(normal,tangents[i])
        if np.linalg.norm(t)<1e-6:t=np.cross(normal,[0,1,0] if abs(normal[1])<.9 else [1,0,0])
        t/=np.linalg.norm(t);vertices['tangent_0'][i,:3]=t
        vertices['tangent_0'][i,3]=-1 if np.dot(np.cross(normal,t),bitangents[i])<0 else 1
    mesh.vertex_arrays=[VertexArray(vertices,copy.deepcopy(template.vertex_arrays[0].layout))]
    mesh.bone_indices=np.arange(native_count,len(flver.bones),dtype=np.int32)
    mesh.default_bone_index=native_count
    mesh.material.name='Authentic MW2 M9 body articulation study'
    for fs in mesh.face_sets:
        fs.is_triangle_strip=False;fs.vertex_indices=np.asarray(faces,dtype=np.uint32)
    flver.meshes=[mesh];flver.refresh_mesh_indices();flver.refresh_bounding_boxes();flver.refresh_bone_bounding_boxes()
    encoded=bytes(flver);restored=read_model(encoded)
    facing_report=facing(restored.meshes[0])
    if facing_report['positive'] or facing_report['negative']!=len(faces):
        raise ValueError('Weighted body facing differs from the measured native convention: '+str(facing_report))
    p,l,b=native_rig(restored);positions,influences,triangles=geometry(restored)
    if [x.name for x in restored.bones]!=[x.name for x in flver.bones] or p!=parents:
        raise ValueError('Serialized bone mapping changed')
    error=mesh_displacement(positions,skin(positions,influences,b,b))
    if error>2e-6:raise ValueError('Serialized bind skinning distorts source geometry')
    if not np.allclose(vertices['position'],restored.meshes[0].vertex_arrays[0].array['position'],atol=1e-7,rtol=0):
        raise ValueError('Serialized positions changed')
    for weights,expected in zip(influences,source_influences,strict=True):
        if weights!=tuple((i+native_count,w) for i,w in expected):raise ValueError('Serialized weights changed')
    for position,weights in zip(positions,influences,strict=True):
        for index,weight in weights:
            local_position=point(undo(b[index]),position)
            bounds=restored.bones[index].bounding_box
            if any(v<float(lo)-2e-6 or v>float(hi)+2e-6 for v,lo,hi in zip(local_position,bounds.min,bounds.max)):
                raise ValueError('Serialized bone culling bounds exclude a weighted vertex')
    # Exact names map the differently ordered native skeletons. WP_A_1401 is
    # a FLVER-only identity root and is not assigned an invented HKX track.
    hk_bind=world_transforms([int(x) for x in hk.parentIndices],hk_local)
    names=[x.name for x in restored.bones]
    results=[];samples=[]
    for clip in motion['clips']:
        raw=pinned(ROOT/clip['path'],clip['sha256'])
        animation=AnimationHKX.from_bytes(raw).animation_container;animation.load_spline_data()
        motion_max={name:0. for name in ('j_gun','j_bolt','j_press_rear','tag_clip')}
        minimum=np.array([math.inf]*3);maximum=-minimum
        for frame in range(clip['frames']):
            posed=list(hk_local)
            for bone,track in zip(animation.hkx_binding.transformTrackToBoneIndices,animation.spline_data.blocks[0],strict=True):
                t=track.get_trs_transform_at_frame(frame)
                posed[bone]=Transform(tuple(t.rotation),tuple(t.translation))
            world=world_transforms([int(x) for x in hk.parentIndices],posed)
            mapped=[world[hk_names.index(n)] if n in hk_names else b[i] for i,n in enumerate(names)]
            deformed=np.asarray(skin(positions,influences,b,mapped))
            if not np.isfinite(deformed).all():raise ValueError('Invalid animation geometry')
            minimum=np.minimum(minimum,deformed.min(axis=0));maximum=np.maximum(maximum,deformed.max(axis=0))
            for name in motion_max:
                index=names.index(name)
                motion_max[name]=max(motion_max[name],math.dist(mapped[index].translation,hk_bind[hk_names.index(name)].translation))
            if (clip['source'],frame) in {('viewmodel_beretta_fire',0),('viewmodel_beretta_fire',4),
                                         ('viewmodel_beretta_reload',40),('viewmodel_beretta_reload',64)}:
                samples.append({'clip':clip['source'],'frame':frame,'seconds':frame/60,'vertices':deformed.tolist()})
        results.append({'clip':clip['source'],'frames':clip['frames'],'posed_min_m':minimum.tolist(),
                        'posed_max_m':maximum.tolist(),'bone_displacement_from_reference_m':motion_max})
    # Retain the verified authentic body textures, without changing their bytes.
    texture_source=ROOT/'converted/dsr/m9-upright-v1/base/parts/WP_A_1401.partsbnd.dcx'
    original_textures=Binder.from_path(texture_source)
    tpf=next(e for e in original_textures.entries if e.path.endswith('.tpf')).get_uncompressed_data()
    texture_names={x.stem.lower() for x in TPF.from_bytes(tpf).textures}
    if any(Path(t.path.replace('\\','/')).stem.lower() not in texture_names for t in mesh.material.textures if t.path):
        raise ValueError('Native body material references missing textures')
    (folder/'m9-weighted-body-study.flver').write_bytes(encoded)
    (folder/'m9-weighted-body-study.tpf').write_bytes(tpf)
    (folder/'weighted-body-geometry.json').write_text(json.dumps({'samples':samples,'triangles':triangles,
        'vertex_bones':[names[w[0][0]] for w in influences],
        'label':'Offline CPU skinning of authentic MW2 geometry and source-motion studies; not native gameplay.'}))
    report={'flver_sha256':hashlib.sha256(encoded).hexdigest(),'source_model_sha256':motion['source_model_sha256'],
            'skeleton_sha256':motion['skeleton_sha256'],'vertices':len(positions),'triangles':len(triangles),
            'flver_bones':len(names),'hkx_bones':len(hk_names),'native_flver_transforms_preserved':True,
            'bone_mapping':'exact names; seven FLVER native bones versus six HKX native bones',
            'source_weights_preserved':True,'bind_error_m':error,'clips':results,
            'serialized_weighted_bone_bounds_verified':True,
            'native_clockwise_facing':facing_report,
            'installed':False,'game_launched':False,'runtime_verified':False,'ready_for_installation':False,
            'limits':['Body/slide/hammer/magazine only; separate sights, suppressor and knife surfaces excluded.',
                      'Source relative-offset interpretation and grip alignment remain authoring hypotheses.',
                      'Native action routing, material playback, contact, culling in motion and visibility unverified.',
                      'This is an offline geometry study, not a fix for the owner-reported missing in-game gun.']}
    (folder/'weighted-body-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('vertices','triangles','flver_bones','hkx_bones','bind_error_m','installed')}))


if __name__=='__main__':main()
