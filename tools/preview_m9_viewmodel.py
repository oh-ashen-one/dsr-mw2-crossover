"""CPU-rasterize the actual local packet. This is not DSR runtime evidence."""
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'converted/mw2-2009/viewmodel-v1'


def read(path=None):
    data=(path or OUT/'m9.dsrvm').read_bytes();at=8
    version,bones,vertices,draws,textures,clips=struct.unpack_from('<6I',data,at);at+=24
    assert data[:8]==b'DSRVM001' and version==1
    dtype=np.dtype([('p','<f4',3),('n','<f4',3),('uv','<f4',2),('j','<u2',4),('w','<f4',4)])
    v=np.frombuffer(data,dtype=dtype,count=vertices,offset=at);at+=vertices*56
    d=np.frombuffer(data,dtype='<u4',count=draws*4,offset=at).reshape((-1,4));at+=draws*16
    t=[]
    for _ in range(textures):
        w,h=struct.unpack_from('<2I',data,at);at+=8
        t.append(np.frombuffer(data,dtype=np.uint8,count=w*h*4,offset=at).reshape((h,w,4)));at+=w*h*4
    c=[]
    for _ in range(clips):
        frames,seconds=struct.unpack_from('<If',data,at);at+=8
        pose=np.frombuffer(data,dtype='<f4',count=frames*2*bones*12,offset=at).reshape((frames,2,bones,3,4));at+=pose.nbytes
        c.append((seconds,pose))
    assert at==len(data)
    return v,d,t,c


def render(name,clip,index,ads,suppressor=False,path=None,output=None):
    v,draws,textures,clips=read(path);m=clips[clip][1][index,ads]
    p=np.column_stack((v['p'],np.ones(len(v))))
    n=np.column_stack((v['n'],np.zeros(len(v))))
    matrices=m[v['j']]
    world=np.sum(np.einsum('vbxy,vy->vbx',matrices,p)*v['w'][:,:,None],axis=1)
    normals=np.sum(np.einsum('vbxy,vy->vbx',matrices,n)*v['w'][:,:,None],axis=1)
    camera=np.column_stack((-world[:,1],world[:,2]-60,world[:,0]))
    width,height=1280,720;y=1/np.tan(np.deg2rad(50)/2)
    xy=np.column_stack(((camera[:,0]*y*height/width/camera[:,2]+1)*width/2,(1-camera[:,1]*y/camera[:,2])*height/2))
    image=np.empty((height,width,3),dtype=np.uint8);image[:]=[36,43,50]
    depth=np.full((height,width),np.inf);triangles=0
    light=np.array([-.3,-.4,1]);light/=np.linalg.norm(light)
    for first,count,texture,only_suppressed in draws:
        if only_suppressed and not suppressor:continue
        tex=textures[texture];th,tw=tex.shape[:2]
        for start in range(int(first),int(first+count),3):
            ids=slice(start,start+3);q=xy[ids];z=camera[ids,2]
            if np.any(z<=.05) or not np.isfinite(q).all():continue
            lo=np.maximum(np.floor(q.min(axis=0)).astype(int),[0,0]);hi=np.minimum(np.ceil(q.max(axis=0)).astype(int),[width-1,height-1])
            if (lo>hi).any():continue
            a,b,c=q;den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
            if abs(den)<1e-8:continue
            yy,xx=np.mgrid[lo[1]:hi[1]+1,lo[0]:hi[0]+1];xx=xx+.5;yy=yy+.5
            u=((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/den
            vv=((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/den
            weights=np.stack((u,vv,1-u-vv),axis=-1);inside=np.all(weights>=-1e-7,axis=-1)
            recip=weights/z;inverse=recip.sum(axis=-1);distance=1/np.maximum(inverse,1e-12)
            region=depth[lo[1]:hi[1]+1,lo[0]:hi[0]+1];mask=inside&(distance<region)
            if not mask.any():continue
            interp=recip/np.maximum(inverse[:,:,None],1e-12)
            uv=interp@v['uv'][ids];rgb=tex[np.floor(uv[:,:,1]*th).astype(int)%th,np.floor(uv[:,:,0]*tw).astype(int)%tw]
            mask &= rgb[:,:,3]>=64
            normal=interp@normals[ids];normal/=np.maximum(np.linalg.norm(normal,axis=-1,keepdims=True),1e-12)
            shade=.45+.55*np.clip(normal@light,0,1)
            colors=np.clip(rgb[:,:,:3]*shade[:,:,None],0,255).astype(np.uint8)
            region[mask]=distance[mask];image[lo[1]:hi[1]+1,lo[0]:hi[0]+1][mask]=colors[mask];triangles+=1
    im=Image.fromarray(image);label=ImageDraw.Draw(im);label.text((20,20),'OFFLINE MW2 SOURCE ASSET PREVIEW — '+name,fill='white')
    label.line((width//2-5,height//2,width//2+5,height//2),fill=(80,160,180));label.line((width//2,height//2-5,width//2,height//2+5),fill=(80,160,180))
    im.save((output or OUT)/(name+'.png'));return {'name':name,'drawn_triangles':triangles,'covered_pixels':int(np.isfinite(depth).sum())}


if __name__=='__main__':
    report=[render('ads-idle',0,0,1),render('hip-idle',0,0,0),render('reload-middle',3,49,0),render('suppressed-ads',0,0,1,True)]
    (OUT/'preview.json').write_text(json.dumps({'game_launched':False,'runtime_verified':False,'previews':report},indent=2)+'\n')
    print(json.dumps(report,indent=2))
