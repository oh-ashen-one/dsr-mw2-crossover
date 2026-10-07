"""Set armory prices in the existing local owner package (bolts, Intervention, SCAR-H free)."""
import copy
import json
from datetime import datetime, timezone
from dsr_mw2.action_trial import OUT, manifest, receipt, sha
from dsr_mw2.install_private import atomic_write
from dsr_mw2.param_patch import patch_row
from dsr_mw2.process_ownership import bottle_processes
from dsr_mw2.runtime_paths import bottle_path
from dsr_mw2.soulstruct_tools import configure, WORKSPACE

PRICES = {11002: (2100000, 0), 11003: (9200000, 0), 11004: (9300000, 0)}  # row: (item, souls)


def main():
    bottle=bottle_path()
    if bottle_processes(bottle) or receipt(bottle).exists():
        raise ValueError('Close the private session and restore its package first')
    report=manifest()
    configure()
    from soulstruct.containers import Binder
    from soulstruct.darksouls1r.params import GameParamBND
    path=OUT/'param/GameParam/GameParam.parambnd.dcx'
    before=path.read_bytes()
    tables={k.rsplit('\\',1)[-1]:v for k,v in GameParamBND.from_bytes(before).params.items()}
    shops=tables['ShopLineupParam'];changes={}
    for row_id,(item,price) in PRICES.items():
        if row_id not in shops.rows or shops[row_id].ItemID!=item:raise ValueError('Armory row changed: %d'%row_id)
        if shops[row_id].SoulCost!=price:changes[row_id]=price
    if not changes:
        print('Armory prices already set');return
    params=Binder.from_bytes(before)
    entry=next(e for e in params.entries if e.path.endswith('\\ShopLineupParam.param'))
    patched=entry.get_uncompressed_data()
    for row_id,price in changes.items():
        replacement=copy.deepcopy(shops[row_id]);replacement.SoulCost=price
        patched,_=patch_row(patched,row_id,bytes(shops[row_id]),bytes(replacement))
    entry.set_uncompressed_data(patched);encoded=bytes(params)
    checked={k.rsplit('\\',1)[-1]:v for k,v in GameParamBND.from_bytes(encoded).params.items()}
    for name,table in tables.items():
        for key,old in table.rows.items():
            new=checked[name][key]
            if name=='ShopLineupParam' and key in changes:
                restored=copy.deepcopy(new);restored.SoulCost=old.SoulCost
                if new.SoulCost!=changes[key] or bytes(restored)!=bytes(old):raise ValueError('Shop row changed beyond its price')
            elif bytes(new)!=bytes(old):raise ValueError('Unrelated parameter row changed: '+name)
    backup=WORKSPACE/'tooling-local/bolt-price-before';backup.mkdir(exist_ok=True)
    atomic_write(backup/(sha(path)+'.dcx'),before)
    atomic_write(backup/(sha(OUT/'manifest.json')+'.json'),(OUT/'manifest.json').read_bytes())
    atomic_write(path,encoded)
    report['files']['param/GameParam/GameParam.parambnd.dcx']=sha(path)
    report['armory_prices']={str(k):v[1] for k,v in PRICES.items()}
    atomic_write(OUT/'manifest.json',(json.dumps(report,indent=2)+'\n').encode())
    manifest()
    proof={'at':datetime.now(timezone.utc).isoformat(),'changed':{str(k):v for k,v in changes.items()},
           'only_price_changed':True,'param_sha256':sha(path),'game_launched':False,'runtime_verified':False}
    atomic_write(WORKSPACE/'evidence/armory-bolt-price.json',(json.dumps(proof,indent=2)+'\n').encode())
    print(json.dumps(proof,indent=2))


if __name__=='__main__':main()
