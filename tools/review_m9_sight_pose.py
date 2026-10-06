"""Measure actual prepared hold, weapon and omitted MW2 sight surfaces offline.

Reports actor-local coordinates, not live camera coordinates or visual proof.
No asset edits; uses the approved pinned Havok reader and source geometry.
"""
import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from dsr_mw2.animation_pose import Transform, compose, rotate
from dsr_mw2.animation_retarget import OrthogonalBasis
from dsr_mw2.skin_geometry import point, skin, undo, world_transforms
from dsr_mw2.xmodel_geometry import read
from dsr_mw2.soulstruct_tools import WORKSPACE as ROOT
from tools.havok_offline_trial import main as approved_havok
from tools.review_m9_attachment import read_model, native_rig, geometry


def main(player='player-raised-v7'):
    player_skeleton,out=approved_havok()
    from soulstruct.havok.fromsoft.darksouls1r import AnimationHKX, SkeletonHKX
    pins={}
    def pinned(path,digest):
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Changed source: '+str(path))
        pins[str(path.relative_to(ROOT))]=digest
        return raw
    def pose(raw,sk):
        c=AnimationHKX.from_bytes(raw).animation_container;c.load_spline_data()
        local=[Transform(tuple(t.rotation),tuple(t.translation[:3])) for t in sk.referencePose]
        for i,t in zip(c.hkx_binding.transformTrackToBoneIndices,c.spline_data.blocks[0],strict=True):
            p=t.get_trs_transform_at_frame(0)
            if any(abs(float(v)-1)>2e-6 for v in p.scale):raise ValueError('Scaled pose')
            local[i]=Transform(tuple(p.rotation),tuple(p.translation))
        return world_transforms([int(i) for i in sk.parentIndices],local)
    player_report=json.loads((out/player/'report.json').read_text())
    hold=next(c for c in player_report['clips'] if c['source_clip']=='m9_ready_hold')
    ps=player_skeleton.skeleton.skeleton;pn=[b.name for b in ps.bones]
    pw=pose(pinned(ROOT/hold['spline'],hold['spline_sha256']),ps)
    weapon_report=json.loads((out/'weapon-native-bound-v1/report.json').read_text())
    ws=SkeletonHKX.from_bytes(pinned(ROOT/weapon_report['skeleton_path'],weapon_report['skeleton_sha256'])).skeleton.skeleton
    wn=[b.name for b in ws.bones]
    ready=json.loads((out/'weapon-ready-v2/report.json').read_text())
    ww=pose(pinned(ROOT/ready['path'],ready['sha256']),ws)
    weighted=json.loads((out/'weapon-motion/weighted-sights-v3-report.json').read_text())
    model=read_model(pinned(ROOT/weighted['flver_path'],weighted['flver_sha256']))
    _,_,bind=native_rig(model);mn=[b.name for b in model.bones]
    mapped=[ww[wn.index(n)] if n in wn else bind[i] for i,n in enumerate(mn)]
    # Reviewed native right-hand attachment: pi X followed by pi Y.
    attached=compose(pw[pn.index('R_Weapon')],Transform((0,0,1,0),(0,0,0)))
    positions,weights,_=geometry(model)
    body=[point(attached,p) for p in skin(positions,weights,bind,mapped)]
    source_path=ROOT/'converted/mw2-2009/unlinked/m9-handling-models/model_export/viewmodel_beretta_lod0.xmodel_export'
    source=read(pinned(source_path,weighted['source_model_sha256']).decode())
    motion=json.loads((out/'weapon-motion/report.json').read_text())
    basis=OrthogonalBasis(((-1,0,0),(0,0,1),(0,-1,0)))
    scale=motion['unit_scale_m'];grip=motion['provisional_grip_source_inches']
    sights=[]
    for material in (1,2):
        indices=sorted({c.vertex for f in source.faces if f.material==material for c in f.corners})
        pos=[point(bind[mn.index('Model_Dmy')],tuple(v*scale for v in basis.vector(tuple(a-b for a,b in zip(source.positions[i],grip))))) for i in indices]
        influences=[tuple((mn.index(source.bones[b].name),w) for b,w in source.influences[i]) for i in indices]
        posed=[point(attached,p) for p in skin(pos,influences,bind,mapped)]
        # Separate front/rear sight islands by the source gun's longitudinal X.
        split=(min(source.positions[i][0] for i in indices)+max(source.positions[i][0] for i in indices))/2
        clusters=[]
        for front in (False,True):
            selected=[p for i,p in zip(indices,posed) if (source.positions[i][0]>split)==front]
            clusters.append({'source_positive_x':front,'count':len(selected),'centroid_m':[sum(p[a] for p in selected)/len(selected) for a in range(3)]})
        sights.append({'material':source.materials[material].name,'vertices':len(indices),'currently_included':True,'clusters':clusters})
    muzzle=point(attached,ww[wn.index('tag_flash')].translation)
    gun_delta=compose(ww[wn.index('j_gun')],undo(bind[mn.index('j_gun')]))
    direction=rotate(compose(attached,gun_delta).rotation,(-1,0,0))
    rear,front=[tuple(sum(s['clusters'][i]['centroid_m'][a] for s in sights)/len(sights) for a in range(3)) for i in (0,1)]
    sight_vector=tuple(b-a for a,b in zip(rear,front));sight_length=math.sqrt(sum(v*v for v in sight_vector))
    eye=tuple(a-v/sight_length*.30 for a,v in zip(rear,sight_vector))
    report={'player_candidate':player,'sightline_rear_m':rear,'sightline_front_m':front,
        'sightline_direction':tuple(v/sight_length for v in sight_vector),'eye_30cm_behind_rear_m':eye,
        'camera_candidate_from_actor_basis':[-eye[0],eye[1],-eye[2],0.],
        'at':datetime.now(timezone.utc).isoformat(),'source_hashes':pins,
        'scope':'Offline actor-local posed coordinates, not live camera/ADS acceptance',
        'player_bones_m':{n:pw[pn.index(n)].translation for n in ('Head','R_Hand','L_Hand','R_Weapon')},
        'body_min_m':[min(p[a] for p in body) for a in range(3)],'body_max_m':[max(p[a] for p in body) for a in range(3)],
        'muzzle_m':muzzle,'muzzle_forward':direction,'muzzle_angle_from_actor_forward_degrees':math.degrees(math.acos(max(-1,min(1,-direction[2])))),
        'original_sights':sights,'preceding_native_camera_offsets':[.06,1.42,.15,0],
        'camera_offset_semantics':['lateral','height','forward','setback'],'runtime_verified':False}
    target=out/('sight-pose-review-'+player+'.json');target.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='source_hashes'},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--player',choices=('player-raised-v7','player-contact-v8','player-landmark-v9'),default='player-raised-v7')
    main(parser.parse_args().player)
