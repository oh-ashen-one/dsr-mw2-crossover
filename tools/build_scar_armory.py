"""Add an authentic MW2 SCAR-H (+M203) to the local native armory; never edit saves.

Layers on the current owner package (Intervention, crossbow routing, bolt price
and M203 grenade rows already applied): world model WP_A_1408, EquipParamWeapon
9300000, ShopLineupParam 11004 at one soul, the armory's shop range and text.
"""
import copy, hashlib, io, json
from pathlib import Path
from dsr_mw2.soulstruct_tools import configure, WORKSPACE as ROOT
from dsr_mw2.runtime_paths import bottle_path
from dsr_mw2.action_trial import OUT, PATHS, ARMORY_PATHS, INTERVENTION_PATHS, SCAR_PATHS, receipt, manifest
from dsr_mw2.install_private import atomic_write
from dsr_mw2.param_patch import append_fixed_row

WEAPON = 9300000
MODEL = 1408
SHOP = 11004
PART = SCAR_PATHS[0]
DAMAGE = 120  # explicit DSR adaptation per full-auto round (Intervention: 350 per shot)


def sha(data): return hashlib.sha256(data).hexdigest()


def world_model(stock, parts_path, main):
    from soulstruct.containers import Binder, TPF
    from soulstruct.flver import FLVER
    from dsr_mw2.xmodel_geometry import read
    from dsr_mw2.scar_assets import visible_faces
    from dsr_mw2.intervention_assets import image
    from dsr_mw2.model_bridge import make_meshes
    from dsr_mw2.weapon_textures import bc5_from_packed, dds_header
    from PIL import Image
    import numpy as np
    src = ROOT / 'converted/mw2-2009/unlinked/scar/model_export/weapon_scar_h_lod0.xmodel_export'
    model = read(src.read_text()); faces = visible_faces(model)
    geometry = {'positions': model.positions, 'uvs': [], 'normals': [], 'groups': {}}
    for face in faces:
        name = model.materials[face.material].name; triangle = []
        for c in face.corners:
            geometry['uvs'].append((c.uv[0], 1 - c.uv[1])); geometry['normals'].append(c.normal)
            triangle.append((c.vertex, len(geometry['uvs']) - 1, len(geometry['normals']) - 1))
        geometry['groups'].setdefault(name, []).append(tuple(triangle))
    stems = {name: 'WP_A_%d_%d' % (MODEL, i) for i, name in enumerate(geometry['groups'])}
    parts = Binder.from_path(stock / parts_path)
    flver_entry = next(e for e in parts.entries if e.path.endswith('.flver'))
    flver = make_meshes(FLVER.from_bytes(flver_entry.get_uncompressed_data()), geometry, material_stems=stems)
    encoded = bytes(flver); checked = FLVER.from_bytes(encoded)
    for a, z in zip(flver.meshes, checked.meshes, strict=True):
        if not np.allclose(a.vertex_arrays[0].array['position'], z.vertex_arrays[0].array['position'], atol=1e-6):
            raise ValueError('World mesh roundtrip changed')
    flver_entry.set_uncompressed_data(encoded)
    te = next(e for e in parts.entries if e.path.endswith('.tpf')); tpf = TPF.from_bytes(te.get_uncompressed_data())
    templates = copy.deepcopy(tpf.textures); tpf.textures = []; proof = []
    for name, stem in stems.items():
        mat = next(m for m in model.materials if m.name == name); diffuse = Path(mat.diffuse_reference).stem
        tex, dds, p = image(main, diffuse); proof.append(p)
        for old in templates:
            t = copy.deepcopy(old)
            suffix = '_n' if old.stem.endswith('_n') else '_s' if old.stem.endswith('_s') else ''
            t.stem = stem + suffix; t.mipmap_count = 1
            if suffix == '_n':
                im = None
                for normal in (diffuse.replace('_col', '_nrml'), diffuse.replace('_col', '_nml')):
                    try:
                        nt, _, p = image(main, normal); proof.append(p); im = Image.frombytes('RGBA', nt[:2], nt[2]); break
                    except (ValueError, KeyError):
                        continue
                im = im or Image.new('RGBA', (4, 4), (128, 128, 255, 128))
                blocks = bc5_from_packed(im); t.data = dds_header(im.width, im.height, b'ATI2', len(blocks), 1) + blocks; t.format = 36
            elif suffix == '_s':
                buf = io.BytesIO(); Image.new('RGBA', (4, 4), (40, 40, 40, 255)).save(buf, format='DDS', pixel_format='DXT5')
                t.data = buf.getvalue(); t.format = 5
            else:
                t.data = dds; t.format = 0 if dds[84:88] == b'DXT1' else 5
            tpf.textures.append(t)
    te.set_uncompressed_data(bytes(tpf))
    for e in parts.entries:
        e.path = e.path.replace('WP_A_1401', 'WP_A_%d' % MODEL)
    return bytes(parts), sha(encoded), proof


def main():
    b = bottle_path(); stock = b / 'drive_c/Games/Dark Souls Remastered'
    from dsr_mw2.process_ownership import bottle_processes
    if receipt(b).exists() or bottle_processes(b):
        raise ValueError('Close private game before building')
    current = manifest()
    if set(current['files']) == set(PATHS + ARMORY_PATHS + INTERVENTION_PATHS + SCAR_PATHS):
        print('SCAR-H already in the armory package'); return
    if set(current['files']) != set(PATHS + ARMORY_PATHS + INTERVENTION_PATHS):
        raise ValueError('Build the Intervention armory first')
    if (stock / PART).exists():
        raise ValueError('Native model ID occupied')
    payload = {p: (OUT / p).read_bytes() for p in current['files']}
    configure()
    from soulstruct.containers import Binder
    from soulstruct.darksouls1r.params import GameParamBND
    from soulstruct.darksouls1r.text.fmg import FMG
    from soulstruct.darksouls1r.ezstate import TalkESD
    from soulstruct.base.ezstate.esd.esp_compiler import ESPCompiler
    from tools.build_m9_viewmodel import MAIN
    payload[PART], world_sha, texture_proof = world_model(stock, PATHS[3], MAIN)
    raw = payload[PATHS[4]]; params = Binder.from_bytes(raw)
    tables = {k.rsplit('\\', 1)[-1]: v for k, v in GameParamBND.from_bytes(raw).params.items()}
    if WEAPON in tables['EquipParamWeapon'].rows or SHOP in tables['ShopLineupParam'].rows:
        raise ValueError('SCAR-H IDs occupied')
    weapon = copy.deepcopy(tables['EquipParamWeapon'][9200000])
    weapon.WeaponModel = MODEL; weapon.Weight = 5.0; weapon.BasePhysicalDamage = DAMAGE
    entry = next(e for e in params.entries if e.path.endswith('\\EquipParamWeapon.param'))
    entry.set_uncompressed_data(append_fixed_row(entry.get_uncompressed_data(), WEAPON, bytes(weapon)))
    shop = copy.deepcopy(tables['ShopLineupParam'][11003]); shop.ItemID = WEAPON; shop.SoulCost = 0
    entry = next(e for e in params.entries if e.path.endswith('\\ShopLineupParam.param'))
    entry.set_uncompressed_data(append_fixed_row(entry.get_uncompressed_data(), SHOP, bytes(shop)))
    payload[PATHS[4]] = bytes(params)
    checked = {k.rsplit('\\', 1)[-1]: v for k, v in GameParamBND.from_bytes(payload[PATHS[4]]).params.items()}
    for name, table in tables.items():
        if any(bytes(row) != bytes(checked[name][i]) for i, row in table.rows.items()):
            raise ValueError('Existing parameter row changed: ' + name)
    if bytes(checked['EquipParamWeapon'][WEAPON]) != bytes(weapon) or bytes(checked['ShopLineupParam'][SHOP]) != bytes(shop):
        raise ValueError('New SCAR-H rows round-trip differs')
    talk = Binder.from_bytes(payload[ARMORY_PATHS[1]]); edited = 0
    for e in talk.entries:
        if not e.path.endswith(('t181000.esd', 't181001.esd')):
            continue
        esd = TalkESD.from_bytes(e.get_uncompressed_data()); cmd = esd.state_machines[1][9000].enter_commands
        if len(cmd) != 1 or cmd[0].args[-1] != ESPCompiler.compile_number(11003) + b'\xa1':
            raise ValueError('Armory shop range changed')
        cmd[0].args[-1] = ESPCompiler.compile_number(SHOP) + b'\xa1'; e.set_uncompressed_data(bytes(esd)); edited += 1
    if edited != 2:
        raise ValueError('Expected the two native Asylum bonfires')
    payload[ARMORY_PATHS[1]] = bytes(talk)
    messages = Binder.from_bytes(payload[ARMORY_PATHS[3]])
    for e in messages.entries:
        if e.entry_id not in (11, 115, 21, 114, 25, 106):
            continue
        f = FMG.from_bytes(e.get_uncompressed_data())
        f.entries[WEAPON] = ('MW2 SCAR-H' if e.entry_id in (11, 115) else
                             'Original MW2 SCAR-H battle rifle with M203 launcher.' if e.entry_id in (21, 114) else
                             'Original MW2 SCAR-H and M203, model and animations.\nFull auto, 20-round magazine; L2 aim, R2 fire.\n'
                             'D-pad Up (or B) toggles the M203 grenade launcher.\nUses Standard Bolts. One-soul test price; no upgrades.')
        e.set_uncompressed_data(bytes(f))
    payload[ARMORY_PATHS[3]] = bytes(messages)
    report = {**current, 'variant': current['variant'] + '-scar', 'files': {p: sha(d) for p, d in payload.items()},
              'stock': {**current['stock'], PART: None},
              'scar': {'weapon': WEAPON, 'model': MODEL, 'shop': SHOP, 'souls': 1, 'base_physical_damage': DAMAGE,
                       'launcher': 'D-pad Up / B toggles M203; grenade Bullet 54014 swapped over Bullet 600 at runtime',
                       'world_model_sha256': world_sha, 'textures': texture_proof, 'runtime_verified': False}}
    for p, d in payload.items():
        target = OUT / p; target.parent.mkdir(parents=True, exist_ok=True); atomic_write(target, d)
    atomic_write(OUT / 'manifest.json', (json.dumps(report, indent=2) + '\n').encode())
    manifest()
    (ROOT / 'evidence/scar-armory-build.json').write_text(json.dumps(report['scar'], indent=2) + '\n')
    print(json.dumps({k: v for k, v in report['scar'].items() if k != 'textures'}, indent=2))


if __name__ == '__main__':
    main()
