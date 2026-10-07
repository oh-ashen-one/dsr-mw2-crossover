"""Add an authentic Intervention to the local native armory; never edit saves."""
import copy,hashlib,json
from pathlib import Path
from dsr_mw2.soulstruct_tools import configure,WORKSPACE as ROOT
from dsr_mw2.runtime_paths import bottle_path
from dsr_mw2.action_trial import OUT,PATHS,ARMORY_PATHS,receipt
from dsr_mw2.param_patch import append_fixed_row

WEAPON=9200000
MODEL=1407
PART='parts/WP_A_1407.partsbnd.dcx'
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
    b=bottle_path();stock=b/'drive_c/Games/Dark Souls Remastered'
    from dsr_mw2.process_ownership import bottle_processes
    if receipt(b).exists() or bottle_processes(b):raise ValueError('Close private game before building')
    # The preserved complete M9 armory is immutable input, so rebuilding is
    # reproducible and never stacks another append on an already edited PARAM.
    base=ROOT/'tooling-local/intervention-backup/action-trial-v1'
    if not base.exists():
        # A fresh machine preserves its already-built nine-file M9 armory.
        # Never treat an extended/partially rebuilt package as the base.
        from dsr_mw2.action_trial import manifest
        original=manifest()
        if set(original['files'])!=set(PATHS+ARMORY_PATHS):raise ValueError('Build the complete M9 armory first')
        for p in original['files']:
            dest=base/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((OUT/p).read_bytes())
        (base/'manifest.json').write_text(json.dumps(original,indent=2)+'\n')
    if base.is_symlink() or base.resolve()!=base:raise ValueError('Redirected preserved armory')
    baseline=json.loads((base/'manifest.json').read_text())
    if set(baseline['files'])!=set(PATHS+ARMORY_PATHS):raise ValueError('Preserved M9 armory is incomplete')
    payload={p:(base/p).read_bytes() for p in baseline['files']}
    if any(sha(data)!=baseline['files'][p] for p,data in payload.items()):raise ValueError('Preserved armory changed')
    configure()
    # The immutable M9 baseline may predate the idle dispatch repair.
    from soulstruct.darksouls1r.ezstate.esd import ChrESD
    from dsr_mw2.action_priority import prioritize_requests, route_native_crossbow
    player_actions=ChrESD.from_bytes(payload[PATHS[0]])
    prioritize_requests(player_actions.state_machines[1][0].conditions)
    route_native_crossbow(player_actions.state_machines[1])
    payload[PATHS[0]]=bytes(player_actions)
    from soulstruct.containers import Binder,TPF
    from soulstruct.flver import FLVER
    from soulstruct.darksouls1r.params import GameParamBND
    from soulstruct.darksouls1r.text.fmg import FMG
    from soulstruct.darksouls1r.ezstate import TalkESD
    from soulstruct.base.ezstate.esd.esp_compiler import ESPCompiler
    from dsr_mw2.xmodel_geometry import read
    from dsr_mw2.intervention_assets import visible_faces,image
    from dsr_mw2.model_bridge import make_meshes
    from dsr_mw2.weapon_textures import bc5_from_packed,dds_header
    from dsr_mw2.tae32 import remove_shared_gunshot
    from tools.build_m9_viewmodel import MAIN
    from PIL import Image
    import numpy as np
    actions=Binder.from_bytes(payload[PATHS[1]])
    tae=next(e for e in actions.entries if e.path.endswith('a46.tae'))
    tae.set_uncompressed_data(remove_shared_gunshot(tae.get_uncompressed_data()))
    payload[PATHS[1]]=bytes(actions)
    src=ROOT/'converted/mw2-2009/unlinked/intervention/model_export/weapon_cheytac_lod0.xmodel_export'
    model=read(src.read_text());faces=visible_faces(model)
    geometry={'positions':model.positions,'uvs':[],'normals':[],'groups':{}}
    for face in faces:
        name=model.materials[face.material].name;triangle=[]
        for c in face.corners:
            # make_meshes consumes OBJ-style V; source XMODEL has original V.
            geometry['uvs'].append((c.uv[0],1-c.uv[1]));geometry['normals'].append(c.normal)
            triangle.append((c.vertex,len(geometry['uvs'])-1,len(geometry['normals'])-1))
        geometry['groups'].setdefault(name,[]).append(tuple(triangle))
    stems={name:'WP_A_1407_'+str(i) for i,name in enumerate(geometry['groups'])}
    parts=Binder.from_path(stock/PATHS[3]);flver_entry=next(e for e in parts.entries if e.path.endswith('.flver'))
    flver=make_meshes(FLVER.from_bytes(flver_entry.get_uncompressed_data()),geometry,material_stems=stems)
    encoded=bytes(flver);checked=FLVER.from_bytes(encoded)
    for a,z in zip(flver.meshes,checked.meshes,strict=True):
        if not np.allclose(a.vertex_arrays[0].array['position'],z.vertex_arrays[0].array['position'],atol=1e-6):raise ValueError('World mesh roundtrip changed')
    flver_entry.set_uncompressed_data(encoded)
    te=next(e for e in parts.entries if e.path.endswith('.tpf'));tpf=TPF.from_bytes(te.get_uncompressed_data());templates=copy.deepcopy(tpf.textures);tpf.textures=[];proof=[]
    for name,stem in stems.items():
        mat=next(m for m in model.materials if m.name==name);diffuse=Path(mat.diffuse_reference).stem
        tex,dds,p=image(MAIN,diffuse);proof.append(p)
        for old in templates:
            t=copy.deepcopy(old);suffix='_n' if old.stem.endswith('_n') else '_s' if old.stem.endswith('_s') else '';t.stem=stem+suffix;t.mipmap_count=1
            if suffix=='_n':
                normal=diffuse.replace('_col','_nml')
                try:nt,_,p=image(MAIN,normal);proof.append(p);im=Image.frombytes('RGBA',nt[:2],nt[2])
                except (ValueError,KeyError):im=Image.new('RGBA',(4,4),(128,128,255,128))
                blocks=bc5_from_packed(im);t.data=dds_header(im.width,im.height,b'ATI2',len(blocks),1)+blocks;t.format=36
            elif suffix=='_s':
                # Conservative neutral specular until packed IW4 channels are
                # separately qualified; never reuse a crossbow's material.
                buf=__import__('io').BytesIO();Image.new('RGBA',(4,4),(40,40,40,255)).save(buf,format='DDS',pixel_format='DXT5');t.data=buf.getvalue();t.format=5
            else:t.data=dds;t.format=0 if dds[84:88]==b'DXT1' else 5
            tpf.textures.append(t)
    te.set_uncompressed_data(bytes(tpf))
    for e in parts.entries:e.path=e.path.replace('WP_A_1401','WP_A_1407')
    if (stock/PART).exists():raise ValueError('Native model ID occupied')
    payload[PART]=bytes(parts)
    raw=payload[PATHS[4]];params=Binder.from_bytes(raw);tables={k.rsplit('\\',1)[-1]:v for k,v in GameParamBND.from_bytes(raw).params.items()}
    if WEAPON in tables['EquipParamWeapon'].rows or 11003 in tables['ShopLineupParam'].rows:raise ValueError('Intervention IDs occupied')
    weapon=copy.deepcopy(tables['EquipParamWeapon'][1250000]);weapon.WeaponModel=MODEL;weapon.Weight=7.0;weapon.BasePhysicalDamage=350
    for i in range(16):setattr(weapon,'UpgradeOrigin'+str(i),-1)
    entry=next(e for e in params.entries if e.path.endswith('\\EquipParamWeapon.param'));entry.set_uncompressed_data(append_fixed_row(entry.get_uncompressed_data(),WEAPON,bytes(weapon)))
    shop=copy.deepcopy(tables['ShopLineupParam'][11000]);shop.ItemID=WEAPON;shop.SoulCost=1
    entry=next(e for e in params.entries if e.path.endswith('\\ShopLineupParam.param'));entry.set_uncompressed_data(append_fixed_row(entry.get_uncompressed_data(),11003,bytes(shop)))
    payload[PATHS[4]]=bytes(params)
    rt={k.rsplit('\\',1)[-1]:v for k,v in GameParamBND.from_bytes(payload[PATHS[4]]).params.items()}
    for name,table in tables.items():
        if any(bytes(row)!=bytes(rt[name][i]) for i,row in table.rows.items()):raise ValueError('Existing parameter row changed')
    talk=Binder.from_bytes(payload[ARMORY_PATHS[1]])
    for e in talk.entries:
        if not e.path.endswith(('t181000.esd','t181001.esd')):continue
        esd=TalkESD.from_bytes(e.get_uncompressed_data());cmd=esd.state_machines[1][9000].enter_commands
        if len(cmd)!=1:raise ValueError('Armory command contract changed')
        expected=ESPCompiler.compile_number(11002)+b'\xa1'
        if cmd[0].args[-1]!=expected:raise ValueError('Armory end row changed')
        cmd[0].args[-1]=ESPCompiler.compile_number(11003)+b'\xa1';e.set_uncompressed_data(bytes(esd))
    payload[ARMORY_PATHS[1]]=bytes(talk)
    messages=Binder.from_bytes(payload[ARMORY_PATHS[3]])
    for e in messages.entries:
        if e.entry_id not in (11,115,21,114,25,106):continue
        f=FMG.from_bytes(e.get_uncompressed_data())
        f.entries[WEAPON]=('MW2 Intervention' if e.entry_id in (11,115) else 'Original MW2 Intervention bolt-action sniper.' if e.entry_id in (21,114) else 'Original MW2 Intervention, scope and animations.\nFive-round magazine; L2 aim, R2 fire.\nSquare reload while aiming. Uses Standard Bolts.\nNative DSR damage adapted to 350 physical.\nOne-soul test price; no upgrades.')
        e.set_uncompressed_data(bytes(f))
    payload[ARMORY_PATHS[3]]=bytes(messages)
    report={**baseline,'variant':baseline['variant']+'-intervention','files':{p:sha(d) for p,d in payload.items()},'stock':{p:sha((stock/p).read_bytes()) if (stock/p).exists() else None for p in payload},'intervention':{'weapon':WEAPON,'model':MODEL,'shop':11003,'souls':1,'base_physical_damage':350,'damage_note':'Explicit DSR adaptation; real native projectile collision/damage','world_model_sha256':sha(src.read_bytes()),'textures':proof,'third_person_animation':'Retained native crossbow skeleton; original MW2 first-person renderer','runtime_verified':False}}
    for p,d in payload.items():target=OUT/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(d)
    (OUT/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');(ROOT/'evidence/intervention-armory-build.json').write_text(json.dumps(report['intervention'],indent=2)+'\n')
    print(json.dumps(report['intervention'],indent=2))
if __name__=='__main__':main()
