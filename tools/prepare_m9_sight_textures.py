"""Lossless offline DDS preparation of owned MW2 sight images; no installation."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile
from dsr_mw2.weapon_textures import iwi_blocks, dds_header

ROOT=Path(__file__).resolve().parents[1]
from dsr_mw2.local_config import path as configured_path
ARCHIVE=configured_path("mw2_root", ROOT / "retail/Call of Duty Modern Warfare 2") / "main/iw_03.iwd"


def main():
    target=ROOT/'converted/mw2-2009/m9/sights';target.mkdir(parents=True,exist_ok=True)
    before=ARCHIVE.stat();records=[]
    with ZipFile(ARCHIVE,'r') as archive:
        for name in ('weapon_trinium_site_c','weapon_trinium_site_white'):
            entry='images/'+name+'.iwi';info=archive.getinfo(entry)
            if info.file_size!=752:raise ValueError('Unexpected original sight image size')
            raw=archive.read(info);fmt,mips=iwi_blocks(raw)
            if fmt!=13 or mips[0][:2]!=(16,32):raise ValueError('Original sight image layout changed')
            w,h,data=mips[0]
            payload=b''.join(m[2] for m in mips)
            dds=dds_header(w,h,b'DXT5',len(data),len(mips))+payload
            if dds[128:]!=payload:raise ValueError('Compressed source blocks changed')
            path=target/(name+'.dds');path.write_bytes(dds)
            records.append({'game':'MW2 (2009)','steam_app_id':10180,'archive':str(ARCHIVE),
                'entry':entry,'source_sha256':hashlib.sha256(raw).hexdigest(),'crc32':f'{info.CRC:08x}',
                'path':str(path.relative_to(ROOT)),'dds_sha256':hashlib.sha256(dds).hexdigest(),
                'width':w,'height':h,'mip_count':len(mips),'tpf_format':5,'source_blocks_unchanged':True})
    after=ARCHIVE.stat()
    if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
        raise ValueError('Source archive changed during the read')
    report={'at':datetime.now(timezone.utc).isoformat(),'images':records,'installed':False,
        'source_model_materials':['mc/mtl_weapon_trinium_sight_glow','mc/mtl_weapon_trinium_sight'],
        'source_model_diffuse_reference':'../images/weapon_trinium_site_c.dds',
        'limits':'Original sight geometry/materials still need adding to the weighted FLVER/TPF. No lookalike pixels or invented glow; no runtime visual proof.'}
    (target/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    (ROOT/'evidence/m9-sight-texture-preparation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'textures':len(records),'source_blocks_unchanged':True,'installed':False}))


if __name__=='__main__':main()
