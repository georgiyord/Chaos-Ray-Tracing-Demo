#!/usr/bin/env python3
"""Offline test for blender/export_crtscene.py using a mocked bpy.

Run:  py-venv/bin/python blender/test_export_crtscene.py
Validates the exported document against schema.json (requires jsonschema,
already installed in py-venv).
"""
import sys, json, types, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

# ---- stub bpy before importing the addon ----
bpy = types.ModuleType('bpy'); bpy.utils = types.ModuleType('bpy.utils')
bpy.utils.register_class = lambda c: None
bpy.utils.unregister_class = lambda c: None
bpy.types = types.ModuleType('bpy.types')
bpy.types.TOPBAR_MT_file_export = types.SimpleNamespace(
    append=lambda f: None, remove=lambda f: None)
bpy.types.Operator = type('Operator', (), {})
sys.modules['bpy'] = bpy
sys.modules['bpy.types'] = bpy.types
bpy_extras = types.ModuleType('bpy_extras')
io_utils = types.ModuleType('bpy_extras.io_utils')
io_utils.ExportHelper = type('ExportHelper', (), {})
bpy_extras.io_utils = io_utils
sys.modules['bpy_extras'] = bpy_extras
sys.modules['bpy_extras.io_utils'] = io_utils
bpy.props = types.ModuleType('bpy.props')
for n in ('BoolProperty', 'IntProperty', 'StringProperty'):
    setattr(bpy.props, n, lambda *a, **k: None)
sys.modules['bpy.props'] = bpy.props


# ---- minimal bpy data mocks ----
class FakeMat3:
    def __init__(self, rows): self.rows = rows
    def __getitem__(self, idx):
        if isinstance(idx, tuple): return self.rows[idx[0]][idx[1]]
        return self.rows[idx]
    def transposed(self): return FakeMat3([list(r) for r in zip(*self.rows)])

class FakeColor:
    def __init__(self, c): self.c = c
    def __getitem__(self, i): return self.c[i]

class FakeInput:
    def __init__(self, v): self.default_value = v

class FakePrincipled:
    type = 'BSDF_PRINCIPLED'
    def __init__(self):
        self.inputs = {'Transmission': FakeInput(0.0),
                       'Emission Strength': FakeInput(0.0),
                       'Metallic': FakeInput(0.0),
                       'Roughness': FakeInput(0.5),
                       'IOR': FakeInput(1.45)}

class FakeNodeTree:
    def __init__(self): self.nodes = [FakePrincipled()]

class FakeMaterial:
    def __init__(self, name='Mat', color=(0.8, 0.2, 0.1, 1.0), transmission=0.0):
        self.name = name
        self.diffuse_color = color
        self.use_nodes = True
        self.node_tree = FakeNodeTree()
        self.node_tree.nodes[0].inputs['Transmission'] = FakeInput(transmission)

class FakeVec:
    def __init__(self, x, y, z): self.x, self.y, self.z = x, y, z
    def __iter__(self): return iter((self.x, self.y, self.z))

class FakeVert:
    def __init__(self, x, y, z): self.co = FakeVec(x, y, z)

class FakeLoopTri:
    def __init__(self, verts, loops): self.vertices = verts; self.loops = loops

class FakeUV:
    def __init__(self, u, v): self.uv = (u, v)

class FakeUVLayer:
    def __init__(self, data): self.active = types.SimpleNamespace(data=data)

class FakeMesh:
    def __init__(self):
        self.vertices = [FakeVert(0, 0, 0), FakeVert(1, 0, 0),
                         FakeVert(0, 1, 0), FakeVert(0, 0, 1)]
        self.loop_triangles = [FakeLoopTri((0, 1, 2), (0, 1, 2)),
                               FakeLoopTri((0, 2, 3), (0, 3, 4))]
        self.uv_layers = FakeUVLayer([FakeUV(0.25, 0.1), FakeUV(0.75, 0.2),
                                      FakeUV(0.5, 0.3), FakeUV(0.5, 0.3),
                                      FakeUV(0.9, 0.8)])
        self.polygons = [types.SimpleNamespace(use_smooth=True)]
    def calc_loop_triangles(self): pass

class FakeMat4:
    def __matmul__(self, v): return FakeVec(v.x, v.y, v.z)
    def to_3x3(self): return FakeMat3([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    def __getattr__(self, name):
        if name == 'translation': return (1, 2, 3)
        raise AttributeError(name)

class FakeLight:
    def __init__(self): self.energy = 100.0

class FakeObj:
    def __init__(self, name, material, obj_type='MESH'):
        self.type = obj_type
        self.name = name
        self.hide_get = lambda: False
        self.data = FakeMesh() if obj_type == 'MESH' else FakeLight()
        self.matrix_world = FakeMat4()
        self.material_slots = ([types.SimpleNamespace(material=material)]
                               if obj_type == 'MESH' else [])
    def evaluated_get(self, d): return self
    def to_mesh(self): return self.data
    def to_mesh_clear(self): pass

class FakeScene:
    camera = types.SimpleNamespace(matrix_world=FakeMat4())
    render = types.SimpleNamespace(resolution_x=1920, resolution_y=1080,
                                   resolution_percentage=100)
    world = types.SimpleNamespace(color=FakeColor((0.1, 0.2, 0.3, 1.0)))
    objects = []
    selected_objects = []

class FakeContext:
    scene = FakeScene()
    def evaluated_depsgraph_get(self): return None


import export_crtscene as e

ctx = FakeContext()
m_diffuse = FakeMaterial('Red', (0.8, 0.2, 0.1, 1.0))
m_refr = FakeMaterial('Glass', (0.9, 0.9, 0.9, 1.0), transmission=1.0)
ctx.scene.objects = [FakeObj('Cube', m_diffuse),
                     FakeObj('Sphere', m_refr),
                     FakeObj('Sun', None, 'LIGHT')]
ctx.scene.selected_objects = ctx.scene.objects

doc = e._build_crtscene(ctx, bucket_size=24, only_selected=False,
                        apply_modifiers=True, uv_wrap=True)

# schema validation against the real schema.json
import jsonschema
schema = json.load(open(os.path.join(os.path.dirname(__file__), '..', 'schema.json')))
jsonschema.validate(doc, schema)
print('SCHEMA VALIDATION: PASS')

assert len(doc['objects']) == 2, len(doc['objects'])
assert doc['objects'][0]['material_index'] == 0
assert doc['objects'][1]['material_index'] == 1
assert doc['materials'][0]['type'] == 'diffuse'
assert doc['materials'][1]['type'] == 'refractive'
assert doc['materials'][1]['ior'] == 1.45
assert doc['materials'][0]['smooth_shading'] is True
assert doc['textures'][0]['albedo'] == [0.8, 0.2, 0.1]
assert doc['textures'][1]['albedo'] == [0.9, 0.9, 0.9]
assert doc['lights'][0]['position'] == [1, 3, -2]
assert doc['lights'][0]['intensity'] == 100.0
assert doc['camera']['matrix'] == [1, 0, 0, 0, 0, -1, 0, 1, 0]
assert doc['camera']['position'] == [1, 3, -2]
assert doc['settings']['image_settings']['width'] == 1920
assert doc['settings']['image_settings']['bucket_size'] == 24
# Z-up -> Y-up: (x,y,z) -> (x,z,-y). Cube verts (0,0,0),(1,0,0),(0,1,0),(0,0,1)
# become (0,0,0),(1,0,0),(0,0,-1),(0,1,0).
assert doc['objects'][0]['vertices'][:12] == [0, 0, 0, 1, 0, 0, 0, 0, -1, 0, 1, 0]
# uvs: one 3-component value per vertex, matching vertex count
assert len(doc['objects'][0]['uvs']) == len(doc['objects'][0]['vertices'])
print('ALL LOGIC CHECKS: PASS')
print('object0: %d verts, %d tris, %d uv components' % (
    len(doc['objects'][0]['vertices']) // 3,
    len(doc['objects'][0]['triangles']) // 3,
    len(doc['objects'][0]['uvs'])))
print('OK')
