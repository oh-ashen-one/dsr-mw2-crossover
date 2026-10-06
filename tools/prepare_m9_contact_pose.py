"""Offline source-wrist trajectory/arm-contact candidate, not native acceptance.

Repositions arms by rotations only, preserves native bones and source duration.
Right-hand world orientation/weapon articulation stay on the existing motion;
left wrist follows the authentic source's displacement relative to the right.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
from dsr_mw2.animation_pose import Transform,read_rig,sample_components,multiply,inverse,slerp,rotate
from dsr_mw2.animation_retarget import OrthogonalBasis,iw4_viewhand_pose
from dsr_mw2.skin_geometry import world_transforms
from dsr_mw2.pose_ik import aim_child,two_bone,add,sub,mul
from dsr_mw2.hand_contact import palm_rotation
from dsr_mw2.xanim import read
from dsr_mw2.havok_study import make_spline_study
from tools.havok_offline_trial import main as approved_havok
from tools.preserve_native_havok_types import preserve_types

ROOT=Path(__file__).resolve().parents[1]


def main(landmarks=False):
    skeleton,out=approved_havok()
    from soulstruct.havok.fromsoft.darksouls1r import AnimationHKX
    from soulstruct.havok.utilities.maths import TRSTransform,Vector3,Quaternion
    def pinned(path,digest):
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Changed source: '+str(path))
        return data
    base=ROOT/'converted/mw2-2009/unlinked'
    rig=read_rig(pinned(base/'m9-handling-models/model_export/viewmodel_base_viewhands_lod0.xmodel_export',
        'e0cdf472f625d3c62525a8f5f43fbe14ebe6b6870441e9f6dd0500dd68f6cc5d').decode())
    source_names=[x.name for x in rig]
    proofs={x['name']:x for x in json.loads((ROOT/'evidence/m9-animation-export-check.json').read_text())['clips']}
    def source(name):return read(pinned(base/'m9-handling-animation/xanim'/name,proofs[name]['sha256']))
    idle=source('viewmodel_beretta_idle');source_idle=iw4_viewhand_pose(rig,sample_components(idle,0))
    si={side:source_names.index('j_wrist_'+suffix) for side,suffix in (('L','le'),('R','ri'))}
    sk=skeleton.skeleton.skeleton;names=[x.name for x in sk.bones];parents=[int(x) for x in sk.parentIndices]
    reference=[Transform(tuple(x.rotation),tuple(x.translation[:3])) for x in sk.referencePose]
    reference_world=world_transforms(parents,reference)
    basis=OrthogonalBasis(((0,0,-1),(1,0,0),(0,1,0)))
    records=json.loads((out/'player-raised-v7/report.json').read_text())['clips']
    hold=next(x for x in records if x['source_clip']=='m9_ready_hold')
    h=AnimationHKX.from_bytes(pinned(ROOT/hold['spline'],hold['spline_sha256'])).animation_container;h.load_spline_data()
    anchor=[Transform(tuple(p.rotation),tuple(p.translation)) for t in h.spline_data.blocks[0] for p in [t.get_trs_transform_at_frame(0)]]
    aw=world_transforms(parents,anchor);right_anchor=add(aw[names.index('R_Hand')].translation,(0.,0.,.18))
    native_length=sum(math.dist(aw[names.index('L_'+a)].translation,aw[names.index('L_'+b)].translation) for a,b in (('UpperArm','Forearm'),('Forearm','Hand')))
    source_length=sum(math.dist(source_idle[source_names.index('j_'+a+'_le')].translation,source_idle[source_names.index('j_'+b+'_le')].translation) for a,b in (('shoulder','elbow'),('elbow','wrist')))*.0254
    limb_ratio=native_length/source_length
    idle_offset=mul(basis.vector(sub(source_idle[si['L']].translation,source_idle[si['R']].translation)),.0254)
    target=out/('player-landmark-v9' if landmarks else 'player-contact-v8');target.mkdir(exist_ok=True);reports=[]
    for record in records:
        clip=idle if record['source_clip']=='m9_ready_hold' else source(record['source_clip'])
        raw=pinned(ROOT/record['spline'],record['spline_sha256']);hk=AnimationHKX.from_bytes(raw);c=hk.animation_container;c.load_spline_data()
        if c.hkx_binding.transformTrackToBoneIndices!=list(range(61)):raise ValueError('Native binding changed')
        frames=[];clamps={'L':0.,'R':0.};endpoints=[];clavicle_frames=0;max_joint_step=0.;worst_step=None;previous=None
        for frame in range(c.hkx_animation.numFrames):
            pose=[Transform(tuple(p.rotation),tuple(p.translation)) for t in c.spline_data.blocks[0] for p in [t.get_trs_transform_at_frame(frame)]]
            world=world_transforms(parents,pose)
            sp=source_idle if record['source_clip']=='m9_ready_hold' else iw4_viewhand_pose(rig,sample_components(clip,min(frame/2,clip.frames)))
            # Authored stance brings the extended native gun arm back18cm and
            # rotates the left clavicle forward so both hands can reach it.
            pose=aim_child(pose,parents,names.index('L_Clavicle'),names.index('L_UpperArm'),(.08,.04,-.08))
            targets={'R':add(right_anchor,mul(basis.vector(sub(sp[si['R']].translation,source_idle[si['R']].translation)),.0254*limb_ratio))}
            offset=mul(basis.vector(sub(sp[si['L']].translation,sp[si['R']].translation)),.0254)
            # Match anatomical palm frames, not unrelated bind quaternion axes.
            # The same right-grip correction rotates BOTH the left wrist offset
            # and its orientation, keeping the source two-hand relationship.
            contact_rotations=None;contact_correction=(0.,0.,0.,1.)
            if landmarks:
                mapped_palms={}
                for side,suffix in (('R','ri'),('L','le')):
                    wrist=sp[si[side]].translation
                    vectors=[basis.vector(sub(sp[source_names.index('j_'+f+'_'+suffix+'_0')].translation,wrist)) for f in ('index','thumb')]
                    mapped_palms[side]=palm_rotation(pose[names.index(side+'_Finger1')].translation,
                        pose[names.index(side+'_Finger0')].translation,*vectors)
                contact_correction=multiply(world[names.index('R_Hand')].rotation,inverse(mapped_palms['R']))
                contact_rotations={side:multiply(contact_correction,mapped_palms[side]) for side in ('R','L')}
            target_offset=add(idle_offset,mul(sub(offset,idle_offset),limb_ratio))
            targets['L']=add(targets['R'],rotate(contact_correction,target_offset))
            # When source reload reach exceeds the shortened target arm, rotate
            # the clavicle toward the wrist rather than stretch native bones.
            cw=world_transforms(parents,pose)
            shoulder=cw[names.index('L_UpperArm')].translation
            clavicle_frames+=1
            clav=cw[names.index('L_Clavicle')].translation
            ci=names.index('L_Clavicle')
            candidate=aim_child(pose,parents,ci,names.index('L_UpperArm'),sub(targets['L'],clav))
            # A constant blend avoids a reach-threshold snap during the source
            # reload's fast hand transfer. The wrist target remains unchanged.
            pose[ci]=Transform(slerp(pose[ci].rotation,candidate[ci].rotation,.6),pose[ci].translation)
            # Each wrist's bind axes remain explicit; one global correction
            # aligns the source right grip to the existing native gun grip.
            mapped={side:multiply(basis.rotation(multiply(sp[si[side]].rotation,inverse(rig[si[side]].global_bind.rotation))),
                reference_world[names.index(side+'_Hand')].rotation) for side in ('L','R')}
            correction=multiply(world[names.index('R_Hand')].rotation,inverse(mapped['R']))
            rotations=contact_rotations or {'R':world[names.index('R_Hand')].rotation,'L':multiply(correction,mapped['L'])}
            proof={}
            for side in ('R','L'):
                upper,fore,hand=[names.index(side+'_'+n) for n in ('UpperArm','Forearm','Hand')]
                pole=(.40 if side=='L' else -.40,1.05,-.25)
                if previous is not None:
                    pole=world_transforms(parents,previous)[fore].translation
                before=list(pose)
                pose,proof[side]=two_bone(pose,parents,upper,fore,hand,targets[side],pole,rotations[side])
                clamps[side]=max(clamps[side],proof[side]['target_clamp_m'])
                twist=names.index(side+'UpArmTwist')
                relative=multiply(inverse(before[upper].rotation),before[twist].rotation)
                pose[twist]=Transform(multiply(pose[upper].rotation,relative),before[twist].translation)
                twist=names.index(side+'_ForeTwist')
                relative=multiply(inverse(before[fore].rotation),before[twist].rotation)
                pose[twist]=Transform(multiply(pose[fore].rotation,relative),before[twist].translation)
            if any(a.translation!=b.translation for a,b in zip(pose,anchor,strict=True)):raise ValueError('Native lengths changed')
            if previous is not None:
                for index,(p,q) in enumerate(zip(pose,previous)):
                    step=math.degrees(2*math.acos(min(1.,abs(sum(a*b for a,b in zip(p.rotation,q.rotation))))))
                    if step>max_joint_step:max_joint_step=step;worst_step={'frame':frame,'bone':names[index]}
            previous=pose
            if frame in (0,c.hkx_animation.numFrames//2,c.hkx_animation.numFrames-1):endpoints.append({'frame':frame,'targets':targets,'result':proof})
            frames.append([TRSTransform(Vector3(p.translation),Quaternion(p.rotation),Vector3((1,1,1))) for p in pose])
        if max(clamps.values())>1e-6:raise ValueError('Source wrist target exceeds native reach: '+str((record['source_clip'],clamps)))
        if max_joint_step>60:raise ValueError('Discontinuous arm candidate: '+str((record['source_clip'],max_joint_step,worst_step)))
        packed=make_spline_study(frames,list(range(61)),names,60,translating=True).animation_container
        data=copy.deepcopy(packed.hkx_animation.data)
        c.hkx_animation.data=data;c.hkx_animation.floatBlockOffsets=[len(data)]
        encoded=preserve_types(raw,bytes(hk));check=AnimationHKX.from_bytes(encoded).animation_container;check.load_spline_data()
        rotation_error=0.;translation_error=0.
        for frame,expected in enumerate(frames):
            for i,p in enumerate(expected):
                actual=check.spline_data.blocks[0][i].get_trs_transform_at_frame(frame)
                dot=abs(sum(float(a)*float(b) for a,b in zip(p.rotation,actual.rotation)))
                rotation_error=max(rotation_error,math.degrees(2*math.acos(min(1.,dot))))
                translation_error=max(translation_error,max(abs(float(a)-float(b)) for a,b in zip(p.translation,actual.translation)))
        if rotation_error>.1 or translation_error>2e-6 or check.hkx_animation.duration!=c.hkx_animation.duration:raise ValueError('Pose serialization drift')
        path=target/(record['source_clip']+'.hkx');path.write_bytes(encoded)
        reports.append({**record,'spline':str(path.relative_to(ROOT)),'spline_sha256':hashlib.sha256(encoded).hexdigest(),
            'source_spline_sha256':record['spline_sha256'],'max_rotation_error_degrees':rotation_error,
            'max_translation_error_m':translation_error,'reach_clamp_m':clamps,'endpoints':endpoints,
            'anatomical_landmark_frame':landmarks,'clavicle_reach_frames':clavicle_frames,'max_joint_step_degrees_per_frame':max_joint_step,'worst_step':worst_step,'runtime_verified':False})
    report={'clips':reports,'authored_right_wrist_setback_m':.18,'source_inches_to_m':.0254,'motion_limb_ratio':limb_ratio,
        'source_wrist_trajectory_preserved_with_reported_reach_clamp':True,'bone_lengths_preserved':True,
        'anatomical_landmark_frame':landmarks,'runtime_verified':False,'limits':'Offline arm solve only; actual native hand contact, fingers and sight alignment unverified.'}
    (target/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({r['source_clip']:r['reach_clamp_m'] for r in reports},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--landmarks',action='store_true')
    main(parser.parse_args().landmarks)
