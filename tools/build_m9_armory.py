"""Stage an original native bonfire armory on the qualified action package.

Only local converted outputs are written. Native shops purchase real equipment
with souls; no save edit, item grant, runtime inventory writer or free ammo.
"""
import copy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from dsr_mw2.soulstruct_tools import configure,WORKSPACE as ROOT
from dsr_mw2.runtime_paths import bottle_path
from dsr_mw2.action_trial import OUT,PATHS,ARMORY_PATHS,manifest,receipt
from dsr_mw2.param_patch import append_fixed_row

WEAPON=9100000
MODEL=1406
MENU_TEXT=90000001

def sha(data):return hashlib.sha256(data).hexdigest()

def canonical(value):
    # Compiler uses tuples for empty subconditions; reader uses lists. Compare
    # every semantic field/byte while normalizing only sequence container type.
    if isinstance(value,dict):return {k:canonical(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [canonical(v) for v in value]
    return value

def main():
    b=bottle_path();stock=b/'drive_c/Games/Dark Souls Remastered'
    if receipt(b).exists():raise ValueError('Restore the action trial before building armory assets')
    baseline=manifest()
    if set(baseline['files'])!=set(PATHS):raise ValueError('Armory requires an unextended qualified action package')
    configure()
    from soulstruct.containers import Binder
    from soulstruct.darksouls1r.params import GameParamBND
    from soulstruct.darksouls1r.ezstate import TalkESD
    from soulstruct.darksouls1r.text.fmg import FMG
    from soulstruct.base.ezstate.esd.esp_compiler import ESPCompiler
    from soulstruct.base.ezstate.esd.esd_type import ESDType

    payload={p:(OUT/p).read_bytes() for p in PATHS}
    raw=payload[PATHS[4]];params=Binder.from_bytes(raw)
    tables={n.rsplit('\\',1)[-1]:t for n,t in GameParamBND.from_bytes(raw).params.items()}
    weapons=tables['EquipParamWeapon'];shops=tables['ShopLineupParam']
    if WEAPON in weapons.rows or any(r.WeaponModel==MODEL for r in weapons.rows.values()):
        raise ValueError('Armory weapon/model ID occupied')
    if (stock/ARMORY_PATHS[0]).exists():raise ValueError('Stock armory model ID occupied')
    weapon=copy.deepcopy(weapons[1250000]);weapon.WeaponModel=MODEL;weapon.Weight=1.5
    weapon.FramptSellValue=10
    # No implicit ascension into unrelated stock weapons. Keep the qualified
    # base reinforcement/behavior fields; unavailable upgrade origins are -1.
    for i in range(16):setattr(weapon,'UpgradeOrigin'+str(i),-1)
    we=next(e for e in params.entries if e.path.endswith('\\EquipParamWeapon.param'))
    we.set_uncompressed_data(append_fixed_row(we.get_uncompressed_data(),WEAPON,bytes(weapon)))
    additions=[]
    se=next(e for e in params.entries if e.path.endswith('\\ShopLineupParam.param'))
    shop_data=se.get_uncompressed_data()
    # Explicit trial economy: base M9 costs1000, attachment variant30. Native
    # Standard Bolt cost30 is retained. Purchases never replenish ammunition.
    for sid,item,cost in ((11000,1250000,1000),(11001,WEAPON,30),(11002,2100000,1)):
        if sid in shops.rows:raise ValueError('Armory shop ID occupied')
        row=copy.deepcopy(shops[1126]);row.ItemID=item;row.SoulCost=cost
        row.QuantityFlag=-1;row.InitialQuantity=-1;row.RequiredGood=-1;row.QWCID=-1
        shop_data=append_fixed_row(shop_data,sid,bytes(row));additions.append((sid,item,cost))
    se.set_uncompressed_data(shop_data);payload[PATHS[4]]=bytes(params)
    checked={n.rsplit('\\',1)[-1]:t for n,t in GameParamBND.from_bytes(payload[PATHS[4]]).params.items()}
    for name,table in tables.items():
        if any(bytes(checked[name][key])!=bytes(row) for key,row in table.rows.items()):
            raise ValueError('Original parameter row changed: '+name)
    old_binder=Binder.from_bytes(raw);new_binder=Binder.from_bytes(payload[PATHS[4]])
    for before,after in zip(old_binder.entries,new_binder.entries,strict=True):
        if before.path!=after.path or before.entry_id!=after.entry_id:raise ValueError('PARAM binder metadata changed')
        if not before.path.endswith(('\\EquipParamWeapon.param','\\ShopLineupParam.param')) and before.data!=after.data:
            raise ValueError('Unrelated PARAM member changed')
    if bytes(checked['EquipParamWeapon'][WEAPON])!=bytes(weapon):raise ValueError('New weapon roundtrip differs')

    weighted=json.loads((ROOT/'converted/mw2-2009/m9/havok/weapon-motion/weighted-suppressor-v1-report.json').read_text())
    parts=Binder.from_bytes(payload[PATHS[3]])
    for ext,key in (('.flver','flver'),('.tpf','tpf')):
        data=(ROOT/weighted[key+'_path']).read_bytes()
        if sha(data)!=weighted[key+'_sha256']:raise ValueError('Prepared suppressor changed')
        next(e for e in parts.entries if e.path.endswith(ext)).set_uncompressed_data(data)
    for e in parts.entries:e.path=e.path.replace('WP_A_1401','WP_A_1406')
    payload[ARMORY_PATHS[0]]=bytes(parts)

    original=(stock/ARMORY_PATHS[1]).read_bytes();talk=Binder.from_bytes(original)
    templates=ESPCompiler(ROOT/'native/data/m9-armory.esp.py',ESDType.TALK).states
    edited=[]
    for e in talk.entries:
        if not e.path.endswith(('t181000.esd','t181001.esd')):continue
        esd=TalkESD.from_bytes(e.get_uncompressed_data());states=esd.state_machines[1]
        before={i:asdict(s) for i,s in states.items()}
        if 9000 in states or len(states[4].conditions)<4:raise ValueError('Native bonfire state contract changed')
        encode=ESPCompiler.compile_number
        menu_commands=[c for c in states[4].enter_commands if (c.bank,c.index)==(1,19)]
        if len(menu_commands)!=12 or any(c.args[0]==encode(13)+b'\xa1' for c in menu_commands):
            raise ValueError('Bonfire menu entries changed')
        # Keep native death/attack/interaction guards ahead of new selection.
        states[4].enter_commands.extend(copy.deepcopy(templates[8000].enter_commands))
        states[4].conditions[3:3]=copy.deepcopy(templates[8000].conditions)
        states[9000]=copy.deepcopy(templates[9000])
        encoded=bytes(esd);rt=TalkESD.from_bytes(encoded).state_machines[1]
        if set(rt)!=set(before)|{9000}:raise ValueError('Bonfire state set changed')
        for i,old in before.items():
            if i!=4 and asdict(rt[i])!=old:raise ValueError('Unrelated bonfire state changed')
        if canonical(asdict(rt[4]))!=canonical(asdict(states[4])) or canonical(asdict(rt[9000]))!=canonical(asdict(states[9000])):
            raise ValueError('Armory state roundtrip differs')
        e.set_uncompressed_data(encoded);edited.append(e.entry_id)
    if len(edited)!=2:raise ValueError('Expected the two native Asylum bonfires')
    payload[ARMORY_PATHS[1]]=bytes(talk)

    for relative,ids in ((ARMORY_PATHS[2],(30,101)),(ARMORY_PATHS[3],(11,115,21,114,25,106))):
        # Start item text from the existing managed M9 package, preserving its
        # upgrade names and all unrelated localized descriptions.
        original=(b/'drive_c/Games/DSR-MW2'/relative).read_bytes();messages=Binder.from_bytes(original)
        for e in messages.entries:
            if e.entry_id not in ids:continue
            fmg=FMG.from_bytes(e.get_uncompressed_data());before=dict(fmg.entries)
            if relative==ARMORY_PATHS[2]:
                if MENU_TEXT in before:raise ValueError('Menu text ID occupied')
                edits={MENU_TEXT:'MW2 armory'}
            else:
                if WEAPON in before:raise ValueError('Weapon text ID occupied')
                if e.entry_id in (11,115):edits={1250000:'MW2 M9',WEAPON:'MW2 M9 + suppressor'}
                elif e.entry_id in (21,114):edits={1250000:'MW2 M9 sidearm.',WEAPON:'MW2 M9 with original suppressor attachment.'}
                else:edits={1250000:'Original MW2 M9. Uses native Standard Bolts.\nManual magazine reload and held aim.\nPresentation remains in development.',WEAPON:'Original MW2 M9 and suppressor model.\nUses native Standard Bolts; reload after switching.\nAttachment only: separate suppressed sound and\nrange effects are not implemented. Trial upgrades\nare unavailable.'}
            fmg.entries.update(edits);encoded=bytes(fmg);rt=FMG.from_bytes(encoded)
            if rt.entries!={**before,**edits}:raise ValueError('Localized text roundtrip changed')
            e.set_uncompressed_data(encoded)
        payload[relative]=bytes(messages)
        for old,new in zip(Binder.from_bytes(original).entries,messages.entries,strict=True):
            if old.entry_id!=new.entry_id or old.path!=new.path:raise ValueError('Message binder metadata changed')
            if old.entry_id not in ids and old.data!=new.data:raise ValueError('Unrelated localized text changed')

    result={**baseline,'variant':baseline['variant']+'-bonfire-armory',
        'files':{p:sha(data) for p,data in payload.items()},
        'stock':{p:sha((stock/p).read_bytes()) if (stock/p).exists() else None for p in payload},
        'armory':{'weapon':WEAPON,'model':MODEL,'menu_text':MENU_TEXT,'shop_rows':additions,
            'bonfire_entries':edited,'original_rows_preserved':True,'stock_bolt_price':30,
            'equipping':'Native inventory/equipment menu; no forced equip or grants',
            'magazine':'Switch clears transient magazine; total native ammo stays unchanged',
            'scope':'Asylum bonfires, standard M9 and authentic suppressor attachment only',
            'suppressed_audio_or_range_effect':False,'runtime_verified':False},
        'runtime_verified':False}
    for p,data in payload.items():
        target=OUT/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    (OUT/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    (ROOT/'evidence/native-armory-build.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['armory'],indent=2))

if __name__=='__main__':main()
