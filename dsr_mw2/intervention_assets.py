"""Owned IW4 Intervention conversion. Outputs contain retail data: keep local."""
import hashlib
import io
import math
import struct
from pathlib import Path
from zipfile import ZipFile
from PIL import Image
from .animation_pose import compose, sample_components
from .animation_retarget import iw4_viewhand_pose
from .skin_geometry import undo
from .weapon_articulation import relative_part_pose
from .weapon_textures import iwi_blocks, dds_header
from .xmodel_geometry import read as read_model
from .xanim import read as read_animation
from .viewmodel_packet import matrix

CLIPS=('idle','fire','fire','reload','reload_empty','pullout','putaway','rechamber','ads_up')
HIDDEN={'tag_acog_2','tag_silencer','tag_thermal_scope','tag_heartbeat'}

def visible_faces(model):
    hidden=set()
    for i,b in enumerate(model.bones):
        if b.name in HIDDEN or b.parent in hidden:hidden.add(i)
    return tuple(f for f in model.faces if not any(i in hidden and w>.001
        for c in f.corners for i,w in model.influences[c.vertex]))

def image(main,name):
    matches=[]
    for archive in sorted(main.glob('*.iwd')):
        with ZipFile(archive) as z:
            entry='images/'+name+'.iwi'
            if entry in z.namelist():matches.append((archive,entry,z.read(entry)))
    if len(matches)!=1:raise ValueError('Expected one source image: '+name)
    archive,entry,data=matches[0]
    # The original scope UI image is a single mip: every offset is EOF.
    fmt,flags,w,h=struct.unpack_from('<BBHH',data,8)
    size=((w+3)//4)*((h+3)//4)*(8 if fmt==11 else 16)
    if (data[:4]==b'IWi\x08' and fmt in (11,13) and flags==0 and
        4<=w<=2048 and 4<=h<=2048 and not(w&(w-1) or h&(h-1)) and
        len(data)==32+size and struct.unpack_from('<4I',data,16)==(len(data),)*4):
        mips=[(w,h,data[32:])]
    else:fmt,mips=iwi_blocks(data)
    if fmt not in (11,13):raise ValueError('Unsupported source image codec')
    w,h,blocks=mips[0];dds=dds_header(w,h,b'DXT1' if fmt==11 else b'DXT5',len(blocks),1)+blocks
    with Image.open(io.BytesIO(dds)) as im:rgba=im.convert('RGBA').tobytes()
    return (w,h,rgba),dds,{'archive':archive.name,'entry':entry,'sha256':hashlib.sha256(data).hexdigest()}

def assemble(source,main):
    provenance=[]
    def owned(path):
        data=path.read_bytes();provenance.append({'file':str(path.relative_to(source)),'sha256':hashlib.sha256(data).hexdigest()});return data
    root=source/'intervention'
    hands=read_model(owned(source/'m9-handling-models/model_export/viewmodel_base_viewhands_lod0.xmodel_export').decode())
    gun=read_model(owned(root/'model_export/viewmodel_cheytac_lod0.xmodel_export').decode())
    if len(hands.bones)!=66 or len(gun.bones)!=24:raise ValueError('Intervention skeleton revision changed')
    animations={n:read_animation(owned(root/'xanim'/('viewmodel_cheytac_'+n))) for n in set(CLIPS)|{'rechamber_ads','ads_down'}}
    idle=sample_components(animations['idle'],0);ads=sample_components(animations['ads_up'],animations['ads_up'].frames)
    attach=next(i for i,b in enumerate(hands.bones) if b.name=='tag_weapon')
    inverse=tuple(undo(b.global_bind) for b in (*hands.bones,*gun.bones))
    textures=[];names=[];vertices=[];draws=[]
    def texture(name):
        if name not in names:
            tex,_,proof=image(main,name);names.append(name);textures.append(tex);provenance.append(proof)
        return names.index(name)
    for model,offset,faces in [(hands,0,hands.faces),(gun,66,visible_faces(gun))]:
        for i,mat in enumerate(model.materials):
            fs=[f for f in faces if f.material==i]
            if not fs:continue
            name=Path(mat.diffuse_reference).stem;tex=texture(name);first=len(vertices)
            for f in fs:
                for c in f.corners:
                    weights=model.influences[c.vertex];indices=[i+offset for i,_ in weights];values=[w for _,w in weights]
                    vertices.append((*model.positions[c.vertex],*c.normal,*c.uv,*(indices+[0]*(4-len(indices))),*(values+[0.]*(4-len(values)))))
            draws.append((first,len(vertices)-first,tex,0))
    scope=texture('scope_overlay_m40a3_1024#0')
    used={int(v[8+k]) for v in vertices for k in range(4) if v[12+k]>0}
    clips=[]
    for name in CLIPS:
        clip=animations[name];duration=clip.frames/clip.fps;frames=[]
        for i in range(math.ceil(duration*60)+1):
            sec=min(i/60.,duration);pairs=[]
            for aiming in (False,True):
                current=animations['rechamber_ads'] if aiming and name=='rechamber' else clip
                components=dict(idle);components.update(sample_components(current,min(sec*current.fps,current.frames)))
                if aiming:components.update(ads)
                handpose=iw4_viewhand_pose(hands.bones,components)
                _,gunpose=relative_part_pose(gun.bones,components,{'j_gun','j_bolt','j_ring','tag_clip','tag_cheytac_scope'})
                pose=(*handpose,*[compose(handpose[attach],p) for p in gunpose])
                # IW4 parks the unused gas-mask tag far offscreen. No exported
                # vertex uses it; omit its irrelevant transform rather than
                # weakening the native packet's finite coordinate limits.
                pairs.append(tuple(matrix(compose(p,b)) if j in used else
                    (1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.)
                    for j,(p,b) in enumerate(zip(pose,inverse,strict=True))))
            frames.append(tuple(pairs))
        clips.append((duration,tuple(frames)))
    return {'bones':90,'vertices':vertices,'draws':draws,'textures':textures,'clips':clips,
            'provenance':provenance,'scope_texture':scope,'texture_names':names,'hidden_tags':sorted(HIDDEN)}
