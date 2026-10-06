"""Build a disposable-only native action/presentation trial from pinned local assets."""
import copy
import hashlib
import json
from pathlib import Path
import struct
from dsr_mw2.soulstruct_tools import configure,WORKSPACE as ROOT
from dsr_mw2.runtime_paths import bottle_path
from dsr_mw2.tae32 import read_events,remove_reload_bolt_effect
from dsr_mw2.action_trial import PATHS
from dsr_mw2.param_patch import patch_row

OUT=ROOT/'converted/dsr/action-trial-v1'
VARIANTS=('integrated','action-only','player-reference','timing-only','animation-only','native-hashes','native-bound','native-presentation','aligned-presentation','framed-presentation','precision-hold','precision-ready','raised-stance','mobile-hold','precision-only','upper-hold','upper-layer','mobile-fire','mobile-reload-sights','contact-reload','landmark-sights')
def sha(data):return hashlib.sha256(data).hexdigest()
def pinned(path,digest):
    data=path.read_bytes()
    if sha(data)!=digest:raise ValueError('Changed asset: '+str(path))
    return data

def main(variant='integrated'):
    if variant not in VARIANTS:
        raise ValueError('Unknown trial variant')
    requested_variant=variant
    contact_pose=variant in ('contact-reload','landmark-sights')
    landmark_pose=variant=='landmark-sights'
    moving_reload_sights=variant in ('mobile-reload-sights','contact-reload','landmark-sights')
    if moving_reload_sights:variant='mobile-fire'
    presentation=variant in ('native-presentation','aligned-presentation','framed-presentation','precision-hold','precision-ready','raised-stance','mobile-hold','precision-only','upper-hold','upper-layer','mobile-fire')
    framed=variant in ('framed-presentation','precision-hold','precision-ready','raised-stance','mobile-hold','precision-only','upper-hold','upper-layer','mobile-fire')
    if (bottle_path()/'.dsr-mw2-action-trial.json').exists():
        raise ValueError('Restore the installed trial before rebuilding its manifest')
    configure()
    from soulstruct.containers import Binder
    from soulstruct.darksouls1r.ezstate.esd import ChrESD
    from soulstruct.base.ezstate.esd.esp_compiler import ESPCompiler
    from soulstruct.base.ezstate.esd.esd_type import ESDType
    native=bottle_path()/'drive_c/Games/Dark Souls Remastered'
    initial={p:(native/p).read_bytes() for p in PATHS}
    esd=ChrESD.from_bytes(initial[PATHS[0]])
    states=esd.state_machines[1]
    if any(i in states for i in (9000,9001,9002,9003)):raise ValueError('Action IDs occupied')
    templates=ESPCompiler(ROOT/'native/data/m9-actions.esp.py',ESDType.CHR).states
    if framed and variant not in ('precision-ready','raised-stance','mobile-hold','precision-only','upper-hold','upper-layer','mobile-fire'):
        raise ValueError('Earlier hold routing is superseded; use precision-ready for the corrected lifecycle trial')
    template=templates[8000]
    def targets(conditions,target):
        return any(c.next_state_id==target or targets(c.subconditions,target) for c in conditions)
    selected=[0]  # Idle action machine also covers locomotion; don't bypass hit/roll/item states.
    if 0 not in selected:raise ValueError('Native idle routing differs')
    for i in selected:states[i].conditions=copy.deepcopy(template.conditions)+states[i].conditions
    states[9000]=copy.deepcopy(states[70]);states[9000].state_id=9000
    states[9001]=copy.deepcopy(states[69]);states[9001].state_id=9001
    states[9002]=copy.deepcopy(states[69]);states[9002].state_id=9002
    def replace(conditions,before,after):
        for c in conditions:
            if c.next_state_id==before:c.next_state_id=after
            replace(c.subconditions,before,after)
    replace(states[9000].conditions,71,0)
    states[9000].conditions=copy.deepcopy(template.conditions)+states[9000].conditions
    replace(states[9001].conditions,70,0);replace(states[9002].conditions,70,0)
    # Reuse the native command's encoding; change only the explicitly identified anim argument.
    cmd=states[9002].enter_commands[0]
    encode=ESPCompiler.compile_number
    if cmd.args[1]!=encode(5502)+b'\xa1':raise ValueError('Reload entry differs')
    cmd.args[1]=encode(5501)+b'\xa1'
    # Native damage/evade interrupt handling remains available during reload.
    states[9001].conditions=copy.deepcopy(states[70].conditions[:1])+states[9001].conditions
    states[9002].conditions=copy.deepcopy(states[70].conditions[:1])+states[9002].conditions
    if presentation:
        for number in (9001,9002):
            states[number].conditions=copy.deepcopy(templates[8001].conditions)+states[number].conditions
    if framed:
        if variant!='precision-only':
            states[0].conditions=copy.deepcopy(templates[8002].conditions)+states[0].conditions
            from dsr_mw2.action_priority import prioritize_requests
            prioritize_requests(states[0].conditions)
        states[9003]=copy.deepcopy(states[69]);states[9003].state_id=9003
        cmd=states[9003].enter_commands[0]
        if cmd.args[1]!=encode(5502)+b'\xa1' or cmd.args[4]!=encode(0)+b'\xa1':raise ValueError('Native ready loop command differs')
        cmd.args[1]=encode(5500)+b'\xa1';cmd.args[4]=encode(1)+b'\xa1'
        if variant in ('mobile-hold','precision-only','upper-hold','upper-layer','mobile-fire'):
            # Isolate the inherited native reload movement lock. Reuse the
            # stock idle SwitchMotion(1) command; do not write coordinates,
            # analog input, root motion, camera state or any other action.
            motion=states[9003].enter_commands[2]
            idle_motion=states[0].enter_commands[1]
            if (motion.bank,motion.index)!=(idle_motion.bank,idle_motion.index) or motion.args!=[encode(0)+b'\xa1'] or idle_motion.args!=[encode(1)+b'\xa1']:
                raise ValueError('Native SwitchMotion contract changed')
            states[9003].enter_commands[2]=copy.deepcopy(idle_motion)
        if variant in ('upper-hold','upper-layer','mobile-fire'):
            # The precision-only control proves native aim can walk. Isolate
            # the hold animation command, preserving every other9003 command,
            # animation/layer/blend/loop argument, input and root-motion data.
            template_upper=states[183].enter_commands[0]
            if (template_upper.bank,template_upper.index)!=(1,4) or len(template_upper.args)!=6 or template_upper.args[5]!=encode(1)+b'\xa1':
                raise ValueError('Native upper-body animation contract changed')
            for commands in (states[9003].enter_commands,states[9003].exit_commands):
                if len(commands[0].args)!=5:raise ValueError('Native general animation contract changed')
                upper=copy.deepcopy(template_upper)
                upper.args=copy.deepcopy(commands[0].args)+[encode(1)+b'\xa1']
                commands[0]=upper
                if variant in ('upper-layer','mobile-fire'):
                    # Second isolated factor: the exact native upper-body layer.
                    # Keep mode, clip, loop, flags, input and root motion unchanged.
                    native_layer=template_upper.args[2]
                    if commands[0].args[2]!=encode(6)+b'\xa1' or native_layer!=encode(4)+b'\xa1':
                        raise ValueError('Native upper animation layer contract changed')
                    commands[0].args[2]=copy.deepcopy(native_layer)
        states[9003].conditions=copy.deepcopy(template.conditions)+copy.deepcopy(templates[8001].conditions)+copy.deepcopy(templates[8003].conditions)
    if variant=='mobile-fire':
        # Hold layer4 has native movement proof. Apply that native upper-body
        # lifecycle to the shot only; preserve its clip/TAE/ammo event and
        # cancel branches. The upper action must use its native end predicate.
        fire=states[9000];upper_template=states[183].enter_commands[0]
        for commands,index in ((fire.enter_commands,2),(fire.exit_commands,0)):
            old=commands[index]
            if len(old.args)!=5 or old.args[2]!=encode(6)+b'\xa1':
                raise ValueError('Native fire animation contract changed')
            new=copy.deepcopy(upper_template)
            new.args=copy.deepcopy(old.args)+[encode(1)+b'\xa1']
            new.args[2]=copy.deepcopy(upper_template.args[2]);commands[index]=new
        for index in (0,5):
            old=fire.enter_commands[index];idle=states[0].enter_commands[1]
            if (old.bank,old.index)!=(idle.bank,idle.index) or old.args!=[encode(0)+b'\xa1']:
                raise ValueError('Native firing motion command changed')
            fire.enter_commands[index]=copy.deepcopy(idle)
        if any(c.next_state_id!=0 for c in fire.conditions[-2:]):
            raise ValueError('Native firing completion destinations changed')
        fire.conditions[-2:]=[copy.deepcopy(states[183].conditions[-1])]
    if moving_reload_sights:
        for number in (9001,9002):
            reload=states[number];upper_template=states[183].enter_commands[0]
            for commands in (reload.enter_commands,reload.exit_commands):
                old=commands[0]
                if len(old.args)!=5 or old.args[2]!=encode(6)+b'\xa1':
                    raise ValueError('Native reload animation contract changed')
                new=copy.deepcopy(upper_template)
                new.args=copy.deepcopy(old.args)+[encode(1)+b'\xa1']
                new.args[2]=copy.deepcopy(upper_template.args[2]);commands[0]=new
            old=reload.enter_commands[2];idle=states[0].enter_commands[1]
            if (old.bank,old.index)!=(idle.bank,idle.index) or old.args!=[encode(0)+b'\xa1']:
                raise ValueError('Native reload movement command changed')
            reload.enter_commands[2]=copy.deepcopy(idle)
            if any(c.next_state_id!=0 for c in reload.conditions[-2:]):
                raise ValueError('Native reload completion destinations changed')
            reload.conditions[-2:]=[copy.deepcopy(states[183].conditions[-1])]
    encoded=bytes(esd);roundtrip=ChrESD.from_bytes(encoded)
    if set(roundtrip.state_machines[1])!=set(states):raise ValueError('ESD state set changed')
    payload={PATHS[0]:encoded}
    clips=json.loads((ROOT/'converted/mw2-2009/m9/havok/m9-handling-studies.json').read_text())['clips']
    if variant in ('player-reference','animation-only'):
        clips=json.loads((ROOT/'converted/mw2-2009/m9/havok/player-reference-v2/report.json').read_text())['clips']
    if variant=='native-hashes':
        clips=json.loads((ROOT/'converted/mw2-2009/m9/havok/player-native-types-v3/report.json').read_text())['clips']
    if variant=='native-bound' or presentation:
        clips=json.loads((ROOT/'converted/mw2-2009/m9/havok/player-native-bound-v4/report.json').read_text())['clips']
    if variant=='aligned-presentation':
        clips=json.loads((ROOT/'converted/mw2-2009/m9/havok/player-native-aligned-v5/report.json').read_text())['clips']
    if framed:
        clips=json.loads((ROOT/'converted/mw2-2009/m9/havok/player-continuous-v6/report.json').read_text())['clips']
    if variant in ('raised-stance','mobile-hold','precision-only','upper-hold','upper-layer','mobile-fire'):
        clips=json.loads((ROOT/'converted/mw2-2009/m9/havok/player-raised-v7/report.json').read_text())['clips']
    if contact_pose:
        clips=json.loads((ROOT/'converted/mw2-2009/m9/havok'/('player-landmark-v9' if landmark_pose else 'player-contact-v8')/'report.json').read_text())['clips']
    motion_root=ROOT/'converted/mw2-2009/m9/havok/weapon-motion'
    motion=json.loads((motion_root/'report.json').read_text())
    weighted=json.loads((motion_root/'weighted-body-report.json').read_text())
    if presentation:
        motion=json.loads((ROOT/'converted/mw2-2009/m9/havok/weapon-native-bound-v1/report.json').read_text())
    if variant=='aligned-presentation' or framed:
        weighted=json.loads((motion_root/'weighted-muzzle-v2-report.json').read_text())
    if moving_reload_sights:
        weighted=json.loads((motion_root/'weighted-sights-v3-report.json').read_text())
    routes={463000:'fire',465502:'reload',465501:'reload_empty2'}
    if framed:routes[465500]='ready_hold'
    player=Binder.from_bytes(initial[PATHS[2]]);durations={}
    for number,clip in routes.items():
        item=next(x for x in clips if x['source_clip']==('m9_ready_hold' if clip=='ready_hold' else 'viewmodel_beretta_'+clip))
        data=pinned(ROOT/item['spline'],item['spline_sha256'])
        entry=next(x for x in player.entries if x.entry_id==number);entry.set_uncompressed_data(data)
        durations[number%10000]=item['duration_seconds']
    payload[PATHS[2]]=bytes(player)
    animations=Binder.from_bytes(initial[PATHS[1]])
    tae=next(x for x in animations.entries if x.path.endswith('a46.tae'))
    data=bytearray(tae.get_uncompressed_data());_,original_events=read_events(bytes(data))
    count,table=struct.unpack_from('<II',data,0x54)
    for i in range(count):
        number,header=struct.unpack_from('<II',data,table+8*i)
        if number not in durations:continue
        n,headers,groups,group_at,times,time_at,mini=struct.unpack_from('<7I',data,header)
        if framed and number==5500:
            if groups:raise ValueError('Expected ungrouped hold-slot TAE')
            struct.pack_into('<I',data,header,0)
            continue
        old=max(e.end for e in original_events if e.animation==number)
        ratio=durations[number]/old
        for index in range(times):
            at=time_at+4*index;value=struct.unpack_from('<f',data,at)[0]
            struct.pack_into('<f',data,at,value*ratio)
    if presentation:data=bytearray(remove_reload_bolt_effect(bytes(data)))
    read_events(bytes(data));tae.set_uncompressed_data(bytes(data));payload[PATHS[1]]=bytes(animations)
    parts=Binder.from_bytes(initial[PATHS[3]])
    flver=ROOT/weighted['flver_path'] if variant=='aligned-presentation' or framed else motion_root/'m9-weighted-body-study.flver'
    next(x for x in parts.entries if x.path.endswith('.flver')).set_uncompressed_data(pinned(flver,weighted['flver_sha256']))
    texture_data=(pinned(ROOT/weighted['tpf_path'],weighted['tpf_sha256']) if moving_reload_sights
                  else (motion_root/'m9-weighted-body-study.tpf').read_bytes())
    next(x for x in parts.entries if x.path.endswith('.tpf')).set_uncompressed_data(texture_data)
    animation_entry=next(x for x in parts.entries if x.path.endswith('.anibnd'));nested=Binder.from_bytes(animation_entry.get_uncompressed_data())
    skeleton=ROOT/motion['skeleton_path'] if presentation else motion_root/'m9-extended-weapon-skeleton.hkx'
    next(x for x in nested.entries if x.entry_id==1000000).set_uncompressed_data(pinned(skeleton,motion['skeleton_sha256']))
    for number,clip in routes.items():
        item=(json.loads((ROOT/'converted/mw2-2009/m9/havok/weapon-ready-v2/report.json').read_text())
              if clip=='ready_hold' else next(x for x in motion['clips'] if x['source']=='viewmodel_beretta_'+clip))
        entry=next((x for x in nested.entries if x.entry_id==number),None)
        if entry is None:
            entry=copy.deepcopy(next(x for x in nested.entries if x.entry_id==463000))
            entry.entry_id=number;entry.path=entry.path.replace('3000',str(number%10000));nested.entries.append(entry)
        entry.set_uncompressed_data(pinned(ROOT/item['path'],item['sha256']))
    nested.entries.sort(key=lambda x:x.entry_id);animation_entry.set_uncompressed_data(bytes(nested));payload[PATHS[3]]=bytes(parts)
    param_raw=(bottle_path()/'drive_c/Games/DSR-MW2'/PATHS[4]).read_bytes()
    projectile_change=None
    if framed:
        from soulstruct.darksouls1r.params import GameParamBND
        tables={k.rsplit('\\',1)[-1]:v for k,v in GameParamBND.from_bytes(param_raw).params.items()}
        row=tables['Bullet'][600];replacement=copy.deepcopy(row)
        if row.ProjectileVFX!=6001:raise ValueError('Native light-bolt VFX differs')
        replacement.ProjectileVFX=-1
        params=Binder.from_bytes(param_raw);entry=next(e for e in params.entries if e.path.endswith('\\Bullet.param'))
        raw=entry.get_uncompressed_data();patched,offset=patch_row(raw,600,bytes(row),bytes(replacement))
        # Undo just this VFX field to prove all native collision, attack, speed,
        # ammo and lifetime fields remain identical to the managed candidate.
        restored=copy.deepcopy(replacement);restored.ProjectileVFX=6001
        if bytes(restored)!=bytes(row):raise ValueError('Projectile mechanics changed')
        entry.set_uncompressed_data(patched);candidate=bytes(params)
        checked=Binder.from_bytes(candidate)
        old=Binder.from_bytes(param_raw)
        for a,b in zip(old.entries,checked.entries,strict=True):
            if a.entry_id!=b.entry_id or a.path!=b.path:raise ValueError('Parameter binder layout changed')
            if not a.path.endswith('\\Bullet.param') and a.data!=b.data:raise ValueError('Unrelated table changed')
        projectile_change={'table':'Bullet','row':600,'field':'ProjectileVFX','before':6001,'after':-1,'mechanics_byte_identical_after_undo':True,
            'scope':'Existing shared native light-bolt row; disposable trial only, dedicated M9 route required before release'}
        param_raw=candidate
    payload[PATHS[4]]=param_raw
    if variant!='integrated' and not presentation:
        # Isolate ESD routing against exact native animation data and the current
        # managed world model. This is a diagnostic, not improved presentation.
        from dsr_mw2.install_private import inspect_install
        if not inspect_install()['installed']:
            raise ValueError('Expected managed candidate for component isolation')
        unchanged={'action-only':PATHS[1:],'player-reference':PATHS[3:],
            'timing-only':PATHS[2:],'animation-only':(PATHS[1],PATHS[3]),'native-hashes':PATHS[3:],
            'native-bound':PATHS[3:]}[variant]
        for p in unchanged:
            payload[p]=(bottle_path()/'drive_c/Games/DSR-MW2'/p).read_bytes()
    for path,data in payload.items():
        target=OUT/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    report={'variant':requested_variant,'files':{p:sha(d) for p,d in payload.items()},'stock':{p:sha(d) for p,d in initial.items()},
        'action_states':{'fire':9000,'reload':9001,'empty_reload':9002},'dispatch_states':selected,
        'requests':{'fire':37,'reload':38,'empty_reload':39},'durations':durations,
        'authentic_model_sha256':weighted['source_model_sha256'] if variant=='integrated' or presentation else None,
        'model_vertices':weighted['vertices'] if variant=='integrated' or presentation else 765,
        'direct_reload_evade':presentation,'held_reload_bolt_removed':presentation,
        'full_body_anchor_aligned':variant=='aligned-presentation' or framed,'muzzle_dummy_on_tag_flash':variant=='aligned-presentation' or framed,
        'raised_hold_pose':framed,'upperarm_skin_helpers_follow_motion':framed,
        'raised_arm_anchor':variant in ('raised-stance','mobile-hold','precision-only','upper-hold','upper-layer','mobile-fire'),
        'held_native_motion_enabled':variant in ('mobile-hold','precision-only','upper-hold','upper-layer','mobile-fire'),
        'held_animation_command':'native upper-body bank1 command4' if variant in ('upper-hold','upper-layer','mobile-fire') else 'native general animation',
        'held_animation_layer':4 if variant in ('upper-layer','mobile-fire') else 6 if framed else None,
        'firing_native_locomotion':variant=='mobile-fire',
        'reload_native_locomotion':moving_reload_sights,
        'source_wrist_contact_pose':contact_pose,'anatomical_landmark_grip':landmark_pose,
        'authentic_sight_surfaces':moving_reload_sights,
        'held_pose_route_enabled':framed and variant!='precision-only',
        'hold_release_predicate':'IsPrecisionShoot()==0' if framed and variant!='precision-only' else None,
        'hold_entry_predicate':'IsPrecisionShoot()' if framed and variant!='precision-only' else None,
        'full_weapon_hold_tracks':16 if framed else None,
        'projectile_visual_change':projectile_change,
        'animation_replacement':variant not in ('action-only','timing-only'),
        'timing_replacement':variant not in ('action-only','animation-only'),
        'runtime_verified':False,'scope':'Disposable M9 trial only; shared a46 animation replacements require later dedicated category isolation',
        'limits':['Native routing, hand contact and moving-part playback need live validation','HUD, ADS/recoil, sound and loadout UI remain unfinished']}
    (OUT/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant',choices=VARIANTS,default='integrated')
    main(parser.parse_args().variant)
