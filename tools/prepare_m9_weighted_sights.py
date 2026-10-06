"""Append original MW2 sight surfaces to the qualified weighted M9 offline.

Source geometry/weights and DDS blocks are preserved; UVs use the native fixed
precision layout. A native alpha material
is an initial translation, not verified MW2 glow equivalence or live acceptance.
"""
import copy
import hashlib
import json
from pathlib import Path

from dsr_mw2.animation_pose import Transform
from dsr_mw2.animation_retarget import OrthogonalBasis
from dsr_mw2.skin_geometry import point
from dsr_mw2.xmodel_geometry import read
from tools.havok_offline_trial import main as approved_havok
from tools.review_m9_attachment import read_model, native_rig
from tools.correct_m9_winding import facing

ROOT=Path(__file__).resolve().parents[1]


def main(include_suppressor=False):
    _,out=approved_havok()
    import numpy as np
    from soulstruct.containers import TPF
    from soulstruct.containers.tpf import TPFTexture
    from soulstruct.flver.vertex_array import VertexArray
    folder=out/'weapon-motion'
    base=json.loads((folder/'weighted-muzzle-v2-report.json').read_text())
    motion=json.loads((folder/'report.json').read_text())
    def pinned(path,digest):
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Changed source: '+str(path))
        return data
    raw=pinned(ROOT/base['flver_path'],base['flver_sha256'])
    model=read_model(raw);template=model.meshes[0]
    source=read(pinned(ROOT/'converted/mw2-2009/unlinked/m9-handling-models/model_export/viewmodel_beretta_lod0.xmodel_export',base['source_model_sha256']).decode())
    _,_,bind=native_rig(model)
    names=[b.name for b in model.bones];attach=names.index('Model_Dmy')
    if names[7:]!=[b.name for b in source.bones]:raise ValueError('Source bone palette changed')
    basis=OrthogonalBasis(((-1,0,0),(0,0,1),(0,-1,0)))
    scale=motion['unit_scale_m'];grip=motion['provisional_grip_source_inches']
    reports=[]
    surfaces=[(1,'mc/mtl_weapon_trinium_sight_glow'),(2,'mc/mtl_weapon_trinium_sight')]
    if include_suppressor:surfaces.append((3,'mc/mtl_weapon_suppressor_b'))
    for material,expected in surfaces:
        if source.materials[material].name!=expected:raise ValueError('Source sight identity changed')
        mesh=copy.deepcopy(template);corners=[];faces=[];indices={}
        for f in source.faces:
            if f.material!=material:continue
            tri=[]
            for c in f.corners:
                if c not in indices:indices[c]=len(corners);corners.append(c)
                tri.append(indices[c])
            faces.append(tuple(reversed(tri)))
        if not corners or not faces:raise ValueError('Missing original sight surfaces')
        v=np.zeros(len(corners),dtype=template.vertex_arrays[0].array.dtype)
        for i,c in enumerate(corners):
            p=basis.vector(tuple((a-b)*scale for a,b in zip(source.positions[c.vertex],grip)))
            v['position'][i]=point(bind[attach],p)
            normal=point(Transform(bind[attach].rotation,(0,0,0)),basis.vector(c.normal))
            v['normal'][i]=np.asarray(normal)/np.linalg.norm(normal)
            v['uv_0'][i]=c.uv;v['color_0'][i]=c.color
            for slot,(bone,weight) in enumerate(source.influences[c.vertex]):
                v['bone_indices'][i,slot]=bone;v['bone_weights'][i,slot]=weight
        tangent=np.zeros((len(v),3));bitangent=np.zeros_like(tangent)
        for tri in faces:
            a,b,c=tri;p=v['position'][b]-v['position'][a];q=v['position'][c]-v['position'][a]
            uv=v['uv_0'][b]-v['uv_0'][a];st=v['uv_0'][c]-v['uv_0'][a]
            d=uv[0]*st[1]-uv[1]*st[0]
            if abs(d)>1e-8:
                tangent[list(tri)]+=(p*st[1]-q*uv[1])/d
                bitangent[list(tri)]+=(q*uv[0]-p*st[0])/d
        for i in range(len(v)):
            n=v['normal'][i];t=tangent[i]-n*np.dot(n,tangent[i])
            if np.linalg.norm(t)<1e-6:t=np.cross(n,[0,1,0] if abs(n[1])<.9 else [1,0,0])
            t/=np.linalg.norm(t);v['tangent_0'][i,:3]=t
            v['tangent_0'][i,3]=-1 if np.dot(np.cross(n,t),bitangent[i])<0 else 1
        mesh.vertex_arrays=[VertexArray(v,copy.deepcopy(template.vertex_arrays[0].layout))]
        mesh.material.name=expected
        if material==3:
            for texture in mesh.material.textures:
                suffix='_n' if texture.texture_type=='g_Bumpmap' else '_s' if texture.texture_type=='g_Specular' else ''
                texture.path='WP_A_1401_suppressor'+suffix+'.tga'
        else:
            mesh.material.mat_def_path='C[D]_Alp.mtd'
            for texture in mesh.material.textures:
                texture.path='weapon_trinium_site_c.tga' if texture.texture_type=='g_Diffuse' else ''
        if not any(t.path for t in mesh.material.textures):raise ValueError('Diffuse binding missing')
        for fs in mesh.face_sets:
            fs.is_triangle_strip=False;fs.vertex_indices=np.asarray(faces,dtype=np.uint32)
        model.meshes.append(mesh)
        reports.append({'material':expected,'vertices':len(v),'triangles':len(faces),'source_vertex_ids':sorted({c.vertex for c in corners})})
    model.refresh_mesh_indices();model.refresh_bounding_boxes();model.refresh_bone_bounding_boxes()
    encoded=bytes(model);check=read_model(encoded)
    original=read_model(raw)
    for a,b in zip(check.dummies,original.dummies,strict=True):
        for field in ('reference_id','parent_bone_index','attach_bone_index','follows_attach_bone','use_upward_vector'):
            if getattr(a,field)!=getattr(b,field):raise ValueError('Qualified muzzle identity changed')
        for field in ('translate','forward','upward'):
            if tuple(getattr(a,field))!=tuple(getattr(b,field)):raise ValueError('Qualified muzzle vector changed')
    if not np.array_equal(check.meshes[0].vertex_arrays[0].array,original.meshes[0].vertex_arrays[0].array):
        raise ValueError('Body geometry or articulation changed')
    for a,b in zip(check.bones,original.bones,strict=True):
        for field in ('name','translate','rotate','scale','parent_bone_index'):
            va,vb=getattr(a,field),getattr(b,field)
            if field in ('translate','rotate','scale'):va,vb=tuple(va),tuple(vb)
            if va!=vb:raise ValueError('Bone binding changed')
    for index,(mesh,report) in enumerate(zip(check.meshes[1:],reports,strict=True),1):
        report['facing']=facing(mesh)
        if report['facing']['positive']:raise ValueError('Sight winding changed')
        before=model.meshes[index].vertex_arrays[0].array
        after=mesh.vertex_arrays[0].array
        report['roundtrip_max_error']={}
        for field in ('position','uv_0','bone_indices','bone_weights'):
            error=float(np.max(np.abs(before[field].astype(float)-after[field].astype(float))))
            report['roundtrip_max_error'][field]=error
            # The pinned native-layout writer multiplies by1024 then casts
            # to integer (truncation, not rounding). Bound to one storage step.
            tolerance=1/1024+1e-6 if field=='uv_0' else 1e-7
            if error>tolerance:raise ValueError('Sight roundtrip changed '+field+': '+str(error))
    texture_path=folder/'m9-weighted-body-study.tpf';tpf=TPF.from_bytes(texture_path.read_bytes())
    textures=json.loads((ROOT/'converted/mw2-2009/m9/sights/manifest.json').read_text())
    tex=next(t for t in textures['images'] if t['entry'].endswith('weapon_trinium_site_c.iwi'))
    data=pinned(ROOT/tex['path'],tex['dds_sha256'])
    tpf.textures.append(TPFTexture(stem='weapon_trinium_site_c',format=tex['tpf_format'],mipmap_count=tex['mip_count'],data=data))
    if include_suppressor:
        from soulstruct.containers import Binder
        from dsr_mw2.pack_textures import pack
        from dsr_mw2.runtime_paths import bottle_path
        native=Binder.from_path(bottle_path()/'drive_c/Games/Dark Souls Remastered/parts/WP_A_1401.partsbnd.dcx')
        template_tpf=TPF.from_bytes(next(e for e in native.entries if e.path.endswith('.tpf')).get_uncompressed_data())
        extra,_=pack(template_tpf,ROOT/'converted/mw2-2009/m9/dds',include_suppressor=True)
        tpf.textures.extend(t for t in TPF.from_bytes(extra).textures if '_suppressor' in t.stem)
    encoded_tpf=bytes(tpf);rt=TPF.from_bytes(encoded_tpf)
    if [(t.stem,t.data) for t in rt.textures]!=[(t.stem,t.data) for t in tpf.textures]:raise ValueError('Texture bytes changed')
    stem='weighted-suppressor-v1' if include_suppressor else 'weighted-sights-v3'
    target=folder/('m9-'+stem+'.flver');target.write_bytes(encoded)
    target_tpf=folder/('m9-'+stem+'.tpf');target_tpf.write_bytes(encoded_tpf)
    report={**base,'flver_path':str(target.relative_to(ROOT)),'flver_sha256':hashlib.sha256(encoded).hexdigest(),
        'tpf_path':str(target_tpf.relative_to(ROOT)),'tpf_sha256':hashlib.sha256(encoded_tpf).hexdigest(),
        'source_flver_sha256':base['flver_sha256'],'vertices':base['vertices']+sum(x['vertices'] for x in reports),
        'triangles':base['triangles']+sum(x['triangles'] for x in reports),'only_dummy_changed':False,
        'sight_surfaces':reports,'body_geometry_muzzle_and_bone_transforms_unchanged':True,
        'original_sight_texture':tex,'runtime_verified':False,'installed':False,
        'limits':['Native alpha material translation; original MW2 glow shader not reproduced.','Native visibility, hand contact and aligned sights remain unverified.']}
    report['suppressor_attachment_present']=include_suppressor
    report['suppression_sound_or_damage_effect']=False
    (folder/(stem+'-report.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'vertices':report['vertices'],'surfaces':reports,'runtime_verified':False},indent=2))


if __name__=='__main__':main()
