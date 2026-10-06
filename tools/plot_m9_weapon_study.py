"""CPU plot of the authentic weighted weapon study; never captures/opens a game."""
import json
from pathlib import Path
from PIL import Image,ImageDraw


def main():
    folder=Path(__file__).resolve().parents[1]/'converted/mw2-2009/m9/havok/weapon-motion'
    data=json.loads((folder/'weighted-body-geometry.json').read_text())
    image=Image.new('RGB',(1400,920),'#f7f7f2');draw=ImageDraw.Draw(image)
    draw.text((30,18),'OFFLINE MW2 M9 articulation study - authentic geometry, not a game screenshot',fill='#192c37',font_size=22)
    draw.text((30,51),'Body / slide / hammer / magazine. Separate sights and attachments excluded. Native playback unverified.',fill='#43545b',font_size=15)
    colors={'j_gun':'#405d75','j_bolt':'#00836e','j_press_rear':'#c27920','tag_clip':'#b23476'}
    if len(data['samples'])!=4:raise ValueError('Expected four reviewed sample frames')
    for i,sample in enumerate(data['samples']):
        ox=(i%2)*700;oy=90+(i//2)*410
        draw.rounded_rectangle((ox+15,oy,ox+685,oy+390),radius=8,outline='#c8d0d3',width=2)
        title=sample['clip'].removeprefix('viewmodel_beretta_')+f"  {sample['seconds']:.3f} s"
        draw.text((ox+35,oy+15),title,fill='#233b44',font_size=20)
        def project(v):return ox+335-v[0]*1100,oy+135+v[1]*550+v[2]*200
        vertices=[project(v) for v in sample['vertices']]
        if any(not(ox+20<=x<=ox+680 and oy+40<=y<=oy+350) for x,y in vertices):
            raise ValueError('A gun part falls outside the plot; do not silently crop it')
        for triangle in data['triangles']:
            color=colors[data['vertex_bones'][triangle[0]]]
            for a,b in zip(triangle,triangle[1:]+triangle[:1]):draw.line((*vertices[a],*vertices[b]),fill=color,width=1)
        draw.text((ox+35,oy+355),'blue: body   green: slide   gold: hammer   magenta: magazine',fill='#43545b',font_size=15)
    image.save(folder/'weighted-body-offline-review.png')


if __name__=='__main__':main()
