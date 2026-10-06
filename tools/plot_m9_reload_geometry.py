"""Small CPU wireframe diagnostic PNG; no engine, GPU or third-party renderer.

Retail geometry and output remain under converted/. Top row is front view of
the full native skeleton and arms, bottom row is a close-up of the left hand.
Columns follow the frame numbers in m9-reload-geometry-samples.json.
"""
import json
from pathlib import Path
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "converted/mw2-2009/m9/havok"


def main():
    data = json.loads((OUT / "m9-reload-geometry-samples.json").read_text())
    width, height = 1250, 900
    pixels = bytearray([246, 247, 249] * width * height)
    def dot(x, y, color):
        if 0 <= x < width and 0 <= y < height:
            at = (y*width+x)*3
            pixels[at:at+3] = bytes(color)
    def line(a, b, color, bounds):
        x0,y0=map(round,a);x1,y1=map(round,b)
        # No unbounded traversal on corrupt or wildly distorted geometry.
        if max(abs(x1-x0),abs(y1-y0)) > 4000: raise ValueError("Projection outside plot bounds")
        dx,dy=abs(x1-x0),-abs(y1-y0);sx=1 if x0<x1 else -1;sy=1 if y0<y1 else -1
        err=dx+dy
        while True:
            if bounds[0] <= x0 < bounds[2] and bounds[1] <= y0 < bounds[3]: dot(x0,y0,color)
            if (x0,y0)==(x1,y1): break
            e=2*err
            if e>=dy: err+=dy;x0+=sx
            if e<=dx: err+=dx;y0+=sy
    for column,sample in enumerate(data['samples']):
        x0=column*250
        vertices=sample['vertices'];bones=sample['bones']
        for row in (0,1,2):
            bounds=(x0,row*300,x0+250,(row+1)*300)
            center=(0,.98,0) if row==0 else bones[data['bone_names'].index('L_Hand' if row==1 else 'R_Hand')]
            scale=120 if row==0 else 1150 if row==1 else 650
            def project(p): return x0+125+((p[0]-center[0]) if row!=2 else -(p[2]-center[2]))*scale,row*300+160-(p[1]-center[1])*scale
            for a,b in data['edges']:
                if row and max(abs(vertices[a][k]-center[k]) for k in range(3))>.22: continue
                line(project(vertices[a]),project(vertices[b]),(82,112,148),bounds)
            for i,parent in enumerate(data['parents']):
                if parent<0:continue
                side='L' if row==1 else 'R'
                if row and not (data['bone_names'][i].startswith(side+'_Finger') or data['bone_names'][i]==side+'_Hand'):continue
                line(project(bones[parent]),project(bones[i]),(194,53,93),bounds)
            if row!=1 and 'weapon_vertices' in sample:
                gun=sample['weapon_vertices']
                for face in data['weapon_triangles']:
                    for a,b in zip(face,face[1:]+face[:1]):line(project(gun[a]),project(gun[b]),(33,132,95),bounds)
                muzzle=sample['muzzle'];direction=sample['muzzle_forward']
                line(project(muzzle),project([a+.08*b for a,b in zip(muzzle,direction)]),(224,132,27),bounds)
        line((x0,0),(x0,height-1),(190,194,203),(0,0,width,height))
    for y in (300,600):line((0,y),(1249,y),(190,194,203),(0,0,width,height))
    def chunk(tag,payload):
        return struct.pack('>I',len(payload))+tag+payload+struct.pack('>I',zlib.crc32(tag+payload)&0xffffffff)
    raw=b''.join(b'\0'+pixels[y*width*3:(y+1)*width*3] for y in range(height))
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')
    path=OUT/'m9-reload-wire-review.png';path.write_bytes(png)
    print(json.dumps({'output':str(path),'frames':[s['frame'] for s in data['samples']],
        'note':'Offline CPU wireframe plot, not a game screenshot or native rendering test'}))


if __name__=='__main__':main()
