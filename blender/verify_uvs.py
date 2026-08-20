"""End-to-end UV correctness verification for blender/export_crtscene.py.

Runs inside real Blender (headless): builds meshes with hand-computable UVs,
exports via the plugin's _build_crtscene, and compares every exported UV
value against independently computed expectations.

Run: blender --background --python blender/verify_uvs.py
"""
import sys, json, math, os

BLENDER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "blender")
sys.path.insert(0, BLENDER_DIR)

import bpy
import export_crtscene as e

failures = []


def approx(a, b, tol=1e-6):
    """Blender stores UVs as float32; compare with tolerance."""
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(approx(x, y, tol) for x, y in zip(a, b))
    return abs(a - b) <= tol


def check(name, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   [{detail}]" if detail else ""))
    if not cond:
        failures.append(name)


def fresh_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    bpy.context.scene.camera = cam
    bpy.context.collection.objects.link(cam)


def link(obj):
    bpy.context.collection.objects.link(obj)
    return obj


def select_only(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def export_sel(uv_wrap):
    ctx = bpy.context
    return e._build_crtscene(ctx, bucket_size=24, only_selected=True,
                             apply_modifiers=False, uv_wrap=uv_wrap)


def uvs_of(doc):
    """Return list of per-vertex (u, v) tuples for the single exported object."""
    obj = doc["objects"][0]
    nv = len(obj["vertices"]) // 3
    assert len(obj["uvs"]) == 3 * nv, "uv component count != 3*vertex count"
    return [(obj["uvs"][3 * i], obj["uvs"][3 * i + 1]) for i in range(nv)]


# ---------------------------------------------------------------------------
# Test 1: standard quad, textbook UVs -> hand-computable result
# ---------------------------------------------------------------------------
fresh_scene()
mesh = bpy.data.meshes.new("QuadStd")
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)])
uv = mesh.uv_layers.new(name="UVMap")
for i, (u, v) in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
    uv.data[i].uv = (u, v)
quad1 = link(bpy.data.objects.new("QuadStd", mesh))
select_only(quad1)
doc = export_sel(uv_wrap=True)
got = uvs_of(doc)
# Expected: per-vertex = first loop's UV per vertex (loop == corner index here)
exp = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
check("T1 standard quad UVs (1.0 boundary preserved)", approx(got, exp), f"got={got} exp={exp}")

# ---------------------------------------------------------------------------
# Test 2: out-of-range UVs with wrap=True and wrap=False
# ---------------------------------------------------------------------------
fresh_scene()
mesh = bpy.data.meshes.new("QuadWrap")
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)])
uv = mesh.uv_layers.new(name="UVMap")
for i, (u, v) in enumerate([(2.3, -0.4), (0.7, 1.6), (-0.2, 0.5), (0.9, 1.1)]):
    uv.data[i].uv = (u, v)
quad2 = link(bpy.data.objects.new("QuadWrap", mesh))
select_only(quad2)

doc = export_sel(uv_wrap=True)
got = uvs_of(doc)
# wrap01: x -> x - floor(x) for out-of-range values only
exp = [(0.3, 0.6), (0.7, 0.6), (0.8, 0.5), (0.9, 0.1)]
check("T2 wrap=True out-of-range UVs", approx(got, exp), f"got={got} exp={exp}")

doc = export_sel(uv_wrap=False)
got = uvs_of(doc)
exp = [(1.0, 0.0), (0.7, 1.0), (0.0, 0.5), (0.9, 1.0)]  # clamp01
check("T2 wrap=False clamps to [0,1]", approx(got, exp), f"got={got} exp={exp}")

# ---------------------------------------------------------------------------
# Test 3: UV seam -> first loop's UV per vertex wins (documented trade-off)
# ---------------------------------------------------------------------------
fresh_scene()
# Two adjacent quads sharing vertex 3; vertex 3 has DIFFERENT UVs in the two
# loops (loop3 vs loop5). Plugin must export the first-seen one.
mesh = bpy.data.meshes.new("QuadSeam")
verts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (2, 1, 0), (2, 0, 0), (0, 1, 0)]
faces = [(0, 1, 3, 2), (2, 3, 4, 5)]  # two quads, shared edge (2,3)
mesh.from_pydata(verts, [], faces)
uv = mesh.uv_layers.new(name="UVMap")
loop_uvs = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.9, 0.1),   # face0: v3 loop3=(0.9,0.1)
            (0.0, 1.0), (0.2, 0.7), (1.0, 1.0), (0.0, 0.0)]  # face1: v3 loop5=(0.2,0.7)
for i, (u, v) in enumerate(loop_uvs):
    uv.data[i].uv = (u, v)
seam = link(bpy.data.objects.new("QuadSeam", mesh))
select_only(seam)
doc = export_sel(uv_wrap=True)
# Seam split: face0=(0,1,3,2) loops(0,1,2,3), face1=(2,3,4,5) loops(4,5,6,7).
# loop UVs: loop0=(0,0)[v0] loop1=(1,0)[v1] loop2=(1,1)[v3] loop3=(0.9,0.1)[v2]
#           loop4=(0,1)[v2] loop5=(0.2,0.7)[v3] loop6=(1,1)[v4] loop7=(0,0)[v5]
# Vertices shared across the seam (v2, v3) with DIFFERENT UVs must split:
# expected (position_yup, uv) multiset:
exp_pairs = {
    ((0.0, 0.0, 0.0), (0.0, 0.0)),      # v0
    ((1.0, 0.0, 0.0), (1.0, 0.0)),      # v1
    ((2.0, 0.0, -1.0), (1.0, 1.0)),     # v3 side A
    ((2.0, 0.0, -1.0), (0.2, 0.7)),     # v3 side B  <- seam split
    ((1.0, 0.0, -1.0), (0.9, 0.1)),     # v2 side A
    ((1.0, 0.0, -1.0), (0.0, 1.0)),     # v2 side B  <- seam split
    ((2.0, 0.0, 0.0), (1.0, 1.0)),      # v4
    ((0.0, 0.0, -1.0), (0.0, 0.0)),     # v5
}
obj = doc["objects"][0]
nv = len(obj["vertices"]) // 3
got_pairs = set()
for i in range(nv):
    p = tuple(round(c, 6) for c in obj["vertices"][3 * i:3 * i + 3])
    u = tuple(round(c, 6) for c in obj["uvs"][3 * i:3 * i + 2])
    got_pairs.add((p, u))
exp_pairs = {tuple(tuple(round(c, 6) for c in x) for x in pair) for pair in exp_pairs}
check("T3 seam: vertices split, per-side UVs correct",
      got_pairs == exp_pairs,
      f"{nv} verts; got={sorted(got_pairs)}")
ok_idx = all(0 <= idx < nv for idx in obj["triangles"])
check("T3 seam: triangle indices reference split vertices", ok_idx)

# ---------------------------------------------------------------------------
# Test 4: no UV layer -> all-zero fallback
# ---------------------------------------------------------------------------
fresh_scene()
mesh = bpy.data.meshes.new("NoUV")
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
nou = link(bpy.data.objects.new("NoUV", mesh))
select_only(nou)
doc = export_sel(uv_wrap=True)
got = uvs_of(doc)
check("T4 no UV layer -> zeros", approx(got, [(0.0, 0.0)] * 3), f"got={got}")

# ---------------------------------------------------------------------------
# Test 5: independent ground-truth on a richer mesh (grid + procedural UVs)
# ---------------------------------------------------------------------------
fresh_scene()
import bmesh
bm = bmesh.new()
grid = bmesh.ops.create_grid(bm, x_segments=3, y_segments=2, size=1.0)
me = bpy.data.meshes.new("Grid")
bm.to_mesh(me)
bm.free()
uv = me.uv_layers.new(name="UVMap")
# procedural per-loop UV: deterministic function of loop index
n_loops = len(uv.data)
for i in range(n_loops):
    uv.data[i].uv = ((i * 7 % 13) / 13.0, (i * 3 % 5) / 5.0)
grid_obj = link(bpy.data.objects.new("Grid", me))
select_only(grid_obj)
doc = export_sel(uv_wrap=True)

# independent ground truth: every distinct (vertex, uv) loop corner must be
# emitted exactly once as a (position_yup, uv) pair
me.calc_loop_triangles()
exp_set = set()
for tri in me.loop_triangles:
    for k in range(3):
        v = tri.vertices[k]
        l = tri.loops[k]
        u, w = uv.data[l].uv
        u -= math.floor(u)
        w -= math.floor(w)
        pos = tuple(round(c, 6) for c in e._to_yup(me.vertices[v].co))
        exp_set.add((pos, (round(u, 6), round(w, 6))))
obj = doc["objects"][0]
nv = len(obj["vertices"]) // 3
got_set = set()
for i in range(nv):
    pos = tuple(round(c, 6) for c in obj["vertices"][3 * i:3 * i + 3])
    u = tuple(round(c, 6) for c in obj["uvs"][3 * i:3 * i + 2])
    got_set.add((pos, u))
check("T5 grid: exported (pos,uv) set == every distinct loop corner",
      got_set == exp_set,
      f"{nv} exported verts vs {len(exp_set)} distinct corners")

# ---------------------------------------------------------------------------
# Test 6: loose vertex next to faces (potential KeyError at line 252)
# ---------------------------------------------------------------------------
fresh_scene()
bm = bmesh.new()
bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0)
bm.verts.new((5.0, 5.0, 5.0))  # loose vertex, not in any face
me = bpy.data.meshes.new("Loose")
bm.to_mesh(me)
bm.free()
uv = me.uv_layers.new(name="UVMap")
for i in range(len(uv.data)):
    uv.data[i].uv = (0.25, 0.5)
loose = link(bpy.data.objects.new("Loose", me))
select_only(loose)
try:
    doc = export_sel(uv_wrap=True)
    got = uvs_of(doc)
    # The loose vertex is not referenced by any face, so it is dropped.
    ok = len(got) == 4  # 4 grid verts only
    ok = ok and all(approx(p, (0.25, 0.5)) for p in got)
    check("T6 loose vertex dropped (no crash, consistent arrays)", ok,
          f"{len(got)} verts; uvs={got}")
except Exception as exc:
    check("T6 loose vertex dropped (no crash, consistent arrays)", False,
          f"raised {type(exc).__name__}: {exc}")

# ---------------------------------------------------------------------------
# Test 7: degenerate (coincident-vertex) triangle must be dropped
# ---------------------------------------------------------------------------
fresh_scene()
mesh = bpy.data.meshes.new("Degen")
# v1 and v3 share a position -> triangle (1,3,2) is zero-area
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 0, 0)], [],
                 [(0, 1, 2), (1, 3, 2)])
uv = mesh.uv_layers.new(name="UVMap")
for i, (u, v) in enumerate([(0.0, 0.0), (1.0, 0.0), (0.0, 1.0),
                            (0.5, 0.5), (0.0, 0.0), (1.0, 0.0)]):
    uv.data[i].uv = (u, v)
degen = link(bpy.data.objects.new("Degen", mesh))
select_only(degen)
doc = export_sel(uv_wrap=True)
obj = doc["objects"][0]
nv = len(obj["vertices"]) // 3
nt = len(obj["triangles"]) // 3
ok = nt == 1 and nv == 3 and all(0 <= idx < nv for idx in obj["triangles"])
check("T7 degenerate triangle dropped", ok,
      f"exported {nt} tris / {nv} verts (expect 1/3)")

# ---------------------------------------------------------------------------
print()
if failures:
    print(f"RESULT: {len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("RESULT: ALL UV CHECKS PASS")
