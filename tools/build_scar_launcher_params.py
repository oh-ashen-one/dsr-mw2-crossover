"""Append the SCAR-H M203 grenade round to the existing local owner package.

Adds three rows cloned from the native firebomb chain: a ballistic parent
Bullet, its explosion child Bullet and the explosion's AtkParam_Pc. Nothing
existing changes. At runtime the adapter swaps the parent row over the
Standard Bolt's Bullet 600 only while the SCAR-H is in launcher mode.
"""
import copy
import json
from datetime import datetime, timezone
from dsr_mw2.action_trial import OUT, manifest, receipt, sha
from dsr_mw2.install_private import atomic_write
from dsr_mw2.param_patch import append_fixed_row
from dsr_mw2.process_ownership import bottle_processes
from dsr_mw2.runtime_paths import bottle_path
from dsr_mw2.soulstruct_tools import configure, WORKSPACE

GRENADE, EXPLOSION, ATTACK = 54014, 54015, 5101311


def main():
    bottle = bottle_path()
    if bottle_processes(bottle) or receipt(bottle).exists():
        raise ValueError('Close the private session and restore its package first')
    report = manifest()
    configure()
    from soulstruct.containers import Binder
    from soulstruct.darksouls1r.params import GameParamBND
    path = OUT / 'param/GameParam/GameParam.parambnd.dcx'
    before = path.read_bytes()
    tables = {k.rsplit('\\', 1)[-1]: v for k, v in GameParamBND.from_bytes(before).params.items()}
    bullets, attacks = tables['Bullet'], tables['AtkParam_Pc']
    if GRENADE in bullets.rows and EXPLOSION in bullets.rows and ATTACK in attacks.rows:
        print('M203 grenade rows already present'); return
    if GRENADE in bullets.rows or EXPLOSION in bullets.rows or ATTACK in attacks.rows:
        raise ValueError('Partial M203 rows present')
    if bullets[110].BulletOnHit != 111 or bullets[111].BulletAttack != 1052:
        raise ValueError('Native firebomb chain changed')
    # Ballistic 40mm round: firebomb arc, faster, no flask visual, standard bolt range.
    grenade = copy.deepcopy(bullets[110])
    grenade.InitialSpeed = 35.0; grenade.MaxSpeed = 60.0; grenade.MinSpeed = 35.0
    grenade.GravityAfterAttenuation = 9.8; grenade.AccelerationAfterAttenuation = 0.0
    grenade.ProjectileVFX = -1; grenade.LifeTime = 6.0; grenade.BulletOnHit = EXPLOSION
    grenade.FirstBulletElevationAngle = 2
    # Explosion: firebomb burst, wider radius, its own attack row.
    explosion = copy.deepcopy(bullets[111])
    explosion.BulletAttack = ATTACK; explosion.FinalHitRadius = 3.5; explosion.InitialHitRadius = 0.8
    blast = copy.deepcopy(attacks[1052])
    blast.PhysicalAttackPower = 260; blast.FireAttackPower = 140
    blast.PoiseAttackPower = 60; blast.ImpactLevel = 3; blast.KnockbackDistance = 1.5
    params = Binder.from_bytes(before)
    for name, rows in (('Bullet', ((GRENADE, grenade), (EXPLOSION, explosion))), ('AtkParam_Pc', ((ATTACK, blast),))):
        entry = next(e for e in params.entries if e.path.endswith('\\' + name + '.param'))
        data = entry.get_uncompressed_data()
        for row_id, row in rows:
            data = append_fixed_row(data, row_id, bytes(row))
        entry.set_uncompressed_data(data)
    encoded = bytes(params)
    checked = {k.rsplit('\\', 1)[-1]: v for k, v in GameParamBND.from_bytes(encoded).params.items()}
    for name, table in tables.items():
        if any(bytes(checked[name][key]) != bytes(row) for key, row in table.rows.items()):
            raise ValueError('Existing parameter row changed: ' + name)
    for name, row_id, row in (('Bullet', GRENADE, grenade), ('Bullet', EXPLOSION, explosion), ('AtkParam_Pc', ATTACK, blast)):
        if bytes(checked[name][row_id]) != bytes(row):
            raise ValueError('New row round-trip differs: %s %d' % (name, row_id))
    old, new = Binder.from_bytes(before), Binder.from_bytes(encoded)
    for a, b in zip(old.entries, new.entries, strict=True):
        if a.path != b.path or a.entry_id != b.entry_id:
            raise ValueError('PARAM binder metadata changed')
        if not a.path.endswith(('\\Bullet.param', '\\AtkParam_Pc.param')) and a.data != b.data:
            raise ValueError('Unrelated PARAM member changed')
    backup = WORKSPACE / 'tooling-local/scar-launcher-params-before'; backup.mkdir(exist_ok=True)
    atomic_write(backup / (sha(path) + '.dcx'), before)
    atomic_write(backup / (sha(OUT / 'manifest.json') + '.json'), (OUT / 'manifest.json').read_bytes())
    atomic_write(path, encoded)
    report['files']['param/GameParam/GameParam.parambnd.dcx'] = sha(path)
    report['scar_launcher_rows'] = {'grenade_bullet': GRENADE, 'explosion_bullet': EXPLOSION, 'explosion_attack': ATTACK}
    atomic_write(OUT / 'manifest.json', (json.dumps(report, indent=2) + '\n').encode())
    manifest()
    proof = {'at': datetime.now(timezone.utc).isoformat(), 'rows': report['scar_launcher_rows'],
             'existing_rows_unchanged': True, 'param_sha256': sha(path), 'game_launched': False, 'runtime_verified': False}
    atomic_write(WORKSPACE / 'evidence/scar-launcher-params.json', (json.dumps(proof, indent=2) + '\n').encode())
    print(json.dumps(proof, indent=2))


if __name__ == '__main__':
    main()
