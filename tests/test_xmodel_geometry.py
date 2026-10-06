import unittest
from dsr_mw2.xmodel_geometry import read


def fixture():
    rig = '''MODEL
VERSION 6
NUMBONES 1
BONE 0 -1 "j_gun"
BONE 0
OFFSET 0, 0, 0
SCALE 1, 1, 1
X 1, 0, 0
Y 0, 1, 0
Z 0, 0, 1
NUMVERTS 3
'''
    for i, p in enumerate(('0, 0, 0','1, 0, 0','0, 1, 0')):
        rig += f'VERT {i}\nOFFSET {p}\nBONES 1\nBONE 0 1.0\n'
    rig += 'NUMFACES 1\nTRI 0 0 0 0\n'
    for i in range(3):rig += f'VERT {i}\nNORMAL 0 0 1\nCOLOR 1 1 1 1\nUV 1 {i/2} 0\n'
    rig += 'NUMOBJECTS 1\nOBJECT 0 "body"\nNUMMATERIALS 1\nMATERIAL 0 "body" "Phong" "../images/body.dds"\n'
    for name, n in (('COLOR',4),('TRANSPARENCY',4),('AMBIENTCOLOR',4),('INCANDESCENCE',4),('COEFFS',2),
                    ('GLOW',2),('REFRACTIVE',2),('SPECULARCOLOR',4),('REFLECTIVECOLOR',4),('REFLECTIVE',2),('BLINN',2),('PHONG',1)):
        rig += name+' '+' '.join(['0']*n)+'\n'
    return rig


class XModelGeometryTests(unittest.TestCase):
    def test_source_weights_and_per_corner_uv_are_preserved(self):
        m = read(fixture())
        self.assertEqual(m.positions,((0.,0.,0.),(1.,0.,0.),(0.,1.,0.)))
        self.assertEqual(m.influences,(((0,1.),),)*3)
        self.assertEqual([c.uv for c in m.faces[0].corners],[(0.,0.),(.5,0.),(1.,0.)])
        self.assertEqual(m.materials[0].diffuse_reference,'../images/body.dds')

    def test_undefined_references_truncation_and_nonfinite_values_fail(self):
        source = fixture()
        for s in (source.replace('TRI 0 0','TRI 1 0'),source.replace('TRI 0 0','TRI 0 1'),
                  source.replace('BONE 0 1.0','BONE 1 1.0'),source.replace('BONE 0 1.0','BONE 0 nan'),
                  source.replace('BONE 0 1.0','BONE 0 0.5'),source.replace('UV 1 0.0','UV 2 0.0'),
                  source[:source.index('NUMMATERIALS')],source+'UNKNOWN 1\n',source.replace('NORMAL 0 0 1','NORMAL 0 0 0')):
            with self.assertRaises(ValueError):read(s)

    def test_merged_degenerate_source_face_is_retained_not_silently_dropped(self):
        source = fixture().replace('VERT 1\nNORMAL','VERT 0\nNORMAL')
        m = read(source)
        self.assertEqual([c.vertex for c in m.faces[0].corners],[0,0,2])
        self.assertNotEqual(m.faces[0].corners[0].uv,m.faces[0].corners[1].uv)
