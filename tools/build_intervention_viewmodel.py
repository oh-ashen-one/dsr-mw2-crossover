"""Build original MW2 Intervention packet locally. No game or renderer launch."""
from pathlib import Path
import hashlib,json
from dsr_mw2.intervention_assets import assemble,CLIPS
from dsr_mw2.viewmodel_packet import encode
from tools.build_m9_viewmodel import MAIN
ROOT=Path(__file__).resolve().parents[1]
def main():
    packet=assemble(ROOT/'converted/mw2-2009/unlinked',MAIN);data=encode(packet)
    out=ROOT/'converted/mw2-2009/intervention-viewmodel-v1';out.mkdir(exist_ok=True)
    target=out/'intervention.dsrvm';target.write_bytes(data)
    report={'file':str(target.relative_to(ROOT)),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
        'bones':packet['bones'],'triangles':len(packet['vertices'])//3,'draws':len(packet['draws']),
        'texture_names':packet['texture_names'],'scope_texture':packet['scope_texture'],
        'clips':[{'name':n,'seconds':c[0]} for n,c in zip(CLIPS,packet['clips'],strict=True)],
        'hidden_tags':packet['hidden_tags'],'sources':packet['provenance'],'runtime_verified':False}
    (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    (ROOT/'evidence/intervention-viewmodel-build.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='sources'},indent=2))
if __name__=='__main__':main()
