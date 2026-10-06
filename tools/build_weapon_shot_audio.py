"""Prepare two original MW2 PCM shot sounds; no audio device/game is opened."""
import hashlib,json
from pathlib import Path
from dsr_mw2.wav_container import repair_oat_pcm
ROOT=Path(__file__).resolve().parents[1]
def main():
    sources={
        'm9-shot.wav':'converted/mw2-2009/m9/audio/weap_beretta_slst_3c.wav',
        'intervention-shot.wav':'converted/mw2-2009/unlinked/intervention/sound/weapons/cheytac/weap_cheytac_slst_2d3.wav',
    }
    out=ROOT/'converted/mw2-2009/shot-audio';out.mkdir(exist_ok=True)
    sha=lambda d:hashlib.sha256(d).hexdigest()
    files={};provenance={}
    for name,relative in sources.items():
        original=(ROOT/relative).read_bytes();wav,metadata=repair_oat_pcm(original)
        if name=='m9-shot.wav' and sha(wav)!='09e57b78ec5a3b6a94b118ec378fa204b7a0b80213590f4c570dbd6c66829f3c':
            raise ValueError('Preserved M9 shot changed')
        (out/name).write_bytes(wav);files[name]=sha(wav)
        provenance[name]={'source':relative,'source_sha256':sha(original),**metadata}
    report={'files':files,'sources':provenance,'playback':'Original stereo PCM on qualified native ammo receipt; eight bounded voices',
        'limitations':['Owner shot audio follows system output volume; native DSR sound-slider attenuation is not integrated',
                       'Native reload/handling foley retained; MW2 reload/bolt foley not integrated'],
        'game_launched':False,'audio_played':False,'runtime_verified':False}
    (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    (ROOT/'evidence/weapon-shot-audio-build.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
