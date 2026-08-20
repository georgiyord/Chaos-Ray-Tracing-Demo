# SPDX-License-Identifier: MIT
"""
Chaos Ray Tracing (.crtscene) exporter for Blender.

Exports the current scene to the JSON format consumed by the CRT raytracer
(schema.json in the repo root). Blender must have a scene camera and at
least one mesh object.

Install: place this file in Blender's addons directory
(Edit -> Preferences -> File Paths -> Script Directories, or
~/.config/blender/<version>/scripts/addons/), enable "Export: CRT Scene"
under File -> Export, then File -> Export -> CRT Scene (.crtscene).
"""

bl_info = {
    "name": "Export CRT Scene",
    "author": "Chaos Ray Tracing",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "File > Export > CRT Scene (.crtscene)",
    "description": "Export the scene to the CRT .crtscene JSON format",
    "category": "Import-Export",
}

import bpy
import json
import math
from bpy_extras.io_utils import ExportHelper
from bpy.props import BoolProperty, IntProperty, StringProperty
from bpy.types import Operator

# ---------------------------------------------------------------------------
# Schema-mandated constants (mirror schema.json)
# ---------------------------------------------------------------------------

TEXTURE_TYPE_ALBEDO = "albedo"
MATERIAL_DEFAULT_ALBEDO = (0.5, 0.5, 0.5)

# Blender is Z-up right-handed; the CRT tracer is Y-up right-handed
# (Renderer.cpp renderBucket: +X right, +Y up, camera looks down -Z).
# The conversion (x, y, z) -> (x, z, -y) is a -90° rotation about X
# (det = +1), so it preserves right-handedness and triangle winding.
ZUP_TO_YUP = (
    (1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0),
    (0.0, -1.0, 0.0),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp01(v):
    return max(0.0, min(1.0, v))


def _to_yup(xyz):
    """Convert a Blender Z-up vector to the tracer's Y-up frame.

    (x, y, z) -> (x, z, -y), i.e. rotate -90° about the X axis.
    """
    x, y, z = (float(c) for c in xyz)
    return (x, z, -y)


def _mat3_mul(a, b):
    """3x3 matrix product a*b (a, b as row-major tuples of 3 tuples)."""
    return tuple(
        tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3))
        for i in range(3)
    )


def _wrap01(v):
    """Wrap a value into [0, 1) so repeated UVs stay schema-valid.

    Values already in [0, 1] are kept as-is (the schema allows 1.0); only
    out-of-range values are wrapped, so standard UV maps keep their edges at
    exactly 1.0 instead of collapsing them to 0.0.
    """
    if 0.0 <= v <= 1.0:
        return v
    return v - math.floor(v)


def _color3(color):
    """Any Blender color (RGBA tuple or Color) -> 3 floats in [0,1]."""
    return (float(color[0]), float(color[1]), float(color[2]))


def _find_principled(material):
    """Return the Principled BSDF node of a material, or None."""
    if material is None or not material.use_nodes or material.node_tree is None:
        return None
    for node in material.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            return node
    return None


def _node_input(node, name, default):
    if node is None:
        return default
    inp = node.inputs.get(name)
    if inp is None:
        return default
    try:
        return inp.default_value
    except Exception:
        return default


def _classify_material(material):
    """Map a Blender material to (type, ior).

    transmission > 0.5 -> refractive (ior from the node, min 1.0)
    emission > 0        -> constant
    metallic > 0.5 or roughness < 0.2 -> reflective
    otherwise           -> diffuse
    """
    principled = _find_principled(material)
    transmission = _node_input(principled, "Transmission", 0.0)
    emission = _node_input(principled, "Emission Strength", 0.0)
    metallic = _node_input(principled, "Metallic", 0.0)
    roughness = _node_input(principled, "Roughness", 0.5)
    ior = _node_input(principled, "IOR", 1.45)

    if float(transmission) > 0.5:
        return "refractive", max(1.0, float(ior))
    if float(emission) > 0.0:
        return "constant", None
    if float(metallic) > 0.5 or float(roughness) < 0.2:
        return "reflective", None
    return "diffuse", None


def _texture_name_for_albedo(albedo, textures_by_color):
    """Deduplicate albedo textures by color; return the texture name."""
    key = tuple(round(c, 6) for c in albedo)
    name = textures_by_color.get(key)
    if name is None:
        name = f"albedo_{len(textures_by_color)}"
        textures_by_color[key] = name
    return name


def _object_material(obj):
    """First usable material slot of a mesh object, else None."""
    for slot in obj.material_slots:
        if slot.material is not None:
            return slot.material
    return None


# ---------------------------------------------------------------------------
# Scene collection
# ---------------------------------------------------------------------------

def _collect_settings(context, bucket_size):
    scene = context.scene
    render = scene.render
    width = int(render.resolution_x * render.resolution_percentage / 100.0)
    height = int(render.resolution_y * render.resolution_percentage / 100.0)
    background = [0.0, 0.0, 0.0]
    if scene.world is not None:
        background = list(_color3(scene.world.color))
    return {
        "background_color": [_clamp01(c) for c in background],
        "image_settings": {
            "width": max(1, width),
            "height": max(1, height),
            "bucket_size": max(1, bucket_size),
        },
    }


def _collect_camera(context):
    scene = context.scene
    cam_obj = scene.camera
    if cam_obj is None:
        return None
    # Tracer convention: world = local * M (row-vector multiply, see
    # Renderer.cpp renderBucket + Matrix3x3 operator*). Blender's
    # matrix_world.to_3x3() maps local->world by columns, so store M = R^T.
    r = cam_obj.matrix_world.to_3x3()
    r_plain = tuple(tuple(r[i][j] for j in range(3)) for i in range(3))
    # Convert the whole frame Z-up -> Y-up: world' = C * world, so
    # R' = C * R and M' = (C*R)^T = R^T * C^T.
    r_yup = _mat3_mul(ZUP_TO_YUP, r_plain)
    m = tuple(tuple(r_yup[j][i] for j in range(3)) for i in range(3))
    matrix = [m[i][j] for i in range(3) for j in range(3)]
    position = list(_to_yup(cam_obj.matrix_world.translation))
    return {"matrix": matrix, "position": position}


def _collect_objects(context, only_selected, apply_modifiers, uv_wrap):
    """Evaluate mesh objects, triangulate, and flatten to CRT arrays.

    Returns (objects, materials) where `materials` is a list of Blender
    materials aligned 1:1 with `objects` (None = no material slot).
    """
    depsgraph = context.evaluated_depsgraph_get()
    candidates = context.selected_objects if only_selected else context.scene.objects
    crt_objects = []
    crt_materials = []

    for obj in candidates:
        if obj.type != "MESH":
            continue
        if not only_selected and obj.hide_get():
            continue

        if apply_modifiers:
            eval_obj = obj.evaluated_get(depsgraph)
            mesh = eval_obj.to_mesh()
        else:
            mesh = obj.data

        try:
            # Bake the world transform into vertices (the CRT format has no
            # per-object transform), then convert Blender's Z-up frame to the
            # tracer's Y-up frame.
            world = obj.matrix_world

            # Triangulate. calc_loop_triangles() -> CCW winding with outward
            # normals (right-hand rule), matching the tracer's
            # cross(edge1, edge2) normal convention.
            mesh.calc_loop_triangles()
            triangles = mesh.loop_triangles

            uv_layer = None
            if mesh.uv_layers:
                uv_layer = mesh.uv_layers.active.data

            if uv_layer is not None:
                # CRT uvs are one 3-component value PER VERTEX, while Blender
                # stores UVs per loop (per face corner). Emit one vertex per
                # distinct (vertex, UV) pair: loops of the same vertex with the
                # same UV stay shared (smooth shading preserved), loops of the
                # same vertex with different UVs split into separate vertices,
                # so UV seams keep each side's own texture coordinates instead
                # of collapsing to a single (wrong) value. Vertices not
                # referenced by any face (loose vertices) are dropped.
                split_verts = []
                split_uvs = []
                key_to_new = {}
                triangles_out = []
                for tri in triangles:
                    corners = []
                    for corner in range(3):
                        vert_idx = tri.vertices[corner]
                        loop_idx = tri.loops[corner]
                        uv = uv_layer[loop_idx].uv
                        u = uv[0] if not uv_wrap else _wrap01(uv[0])
                        v = uv[1] if not uv_wrap else _wrap01(uv[1])
                        corners.append((
                            vert_idx,
                            _to_yup(world @ mesh.vertices[vert_idx].co),
                            round(u, 6), round(v, 6),
                            _clamp01(u), _clamp01(v),
                        ))
                    # Skip zero-area triangles (coincident/collinear vertices):
                    # the CRT loader normalises every triangle normal and
                    # throws on a zero vector, crashing the whole scene load.
                    p0, p1, p2 = (c[1] for c in corners)
                    e1 = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
                    e2 = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
                    cr = (e1[1] * e2[2] - e1[2] * e2[1],
                          e1[2] * e2[0] - e1[0] * e2[2],
                          e1[0] * e2[1] - e1[1] * e2[0])
                    if cr[0] * cr[0] + cr[1] * cr[1] + cr[2] * cr[2] < 1e-12:
                        continue
                    tri_out = []
                    for (vert_idx, pos, u6, v6, u, v) in corners:
                        key = (vert_idx, u6, v6)
                        new_idx = key_to_new.get(key)
                        if new_idx is None:
                            new_idx = len(split_verts)
                            key_to_new[key] = new_idx
                            split_verts.append(pos)
                            split_uvs.append((u, v, 0.0))
                        tri_out.append(new_idx)
                    triangles_out.append(tri_out)
                if len(split_verts) < 3 or not triangles_out:
                    continue
                verts = split_verts
                uvs = split_uvs
            else:
                # No UV layer: keep the original vertices with zero UVs.
                verts = [_to_yup(world @ v.co) for v in mesh.vertices]
                uvs = [(0.0, 0.0, 0.0) for _ in verts]
                triangles_out = []
                for tri in triangles:
                    i0, i1, i2 = tri.vertices
                    p0, p1, p2 = verts[i0], verts[i1], verts[i2]
                    e1 = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
                    e2 = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
                    cr = (e1[1] * e2[2] - e1[2] * e2[1],
                          e1[2] * e2[0] - e1[0] * e2[2],
                          e1[0] * e2[1] - e1[1] * e2[0])
                    if cr[0] * cr[0] + cr[1] * cr[1] + cr[2] * cr[2] < 1e-12:
                        continue
                    triangles_out.append([i0, i1, i2])
                if len(verts) < 3 or not triangles_out:
                    continue

            crt_objects.append({
                "vertices": [c for v in verts for c in v],
                "triangles": [idx for tri in triangles_out for idx in tri],
                "uvs": [c for uv in uvs for c in uv],
            })
            crt_materials.append(_object_material(obj))
        finally:
            if apply_modifiers:
                eval_obj.to_mesh_clear()

    return crt_objects, crt_materials


def _collect_materials(crt_objects, crt_materials, smooth_flags):
    """Build textures + materials arrays from the exported mesh objects.

    Returns (textures, materials, material_indices) where material_indices is
    aligned 1:1 with crt_objects.
    """
    textures_by_color = {}
    material_entries = {}  # Blender material name -> index into materials
    textures = []
    materials = []
    material_indices = []

    for obj, material, smooth in zip(crt_objects, crt_materials, smooth_flags):
        albedo = MATERIAL_DEFAULT_ALBEDO
        if material is not None and material.diffuse_color is not None:
            albedo = tuple(_clamp01(c) for c in _color3(material.diffuse_color))

        key = material.name if material is not None else "__default__"
        if key not in material_entries:
            tex_name = _texture_name_for_albedo(albedo, textures_by_color)
            if not any(t["name"] == tex_name for t in textures):
                textures.append({"name": tex_name, "type": TEXTURE_TYPE_ALBEDO,
                                 "albedo": list(albedo)})
            mat_type, ior = _classify_material(material)
            entry = {
                "type": mat_type,
                "albedo": tex_name,
                "smooth_shading": False,
            }
            if mat_type == "refractive":
                entry["ior"] = ior
            material_entries[key] = len(materials)
            materials.append(entry)
        material_indices.append(material_entries[key])
        # The CRT smooth_shading flag is per-material; if any mesh using this
        # material has smooth faces, set it (one material may be shared).
        if smooth:
            materials[material_entries[key]]["smooth_shading"] = True

    return textures, materials, material_indices


def _collect_lights(context, only_selected):
    candidates = context.selected_objects if only_selected else context.scene.objects
    lights = []
    for obj in candidates:
        if obj.type != "LIGHT":
            continue
        if not only_selected and obj.hide_get():
            continue
        pos = list(_to_yup(obj.matrix_world.translation))
        lights.append({"position": pos, "intensity": float(obj.data.energy)})
    return lights


def _build_crtscene(context, bucket_size, only_selected, apply_modifiers, uv_wrap):
    camera = _collect_camera(context)
    if camera is None:
        raise RuntimeError("The scene has no active camera (Scene > Camera).")

    raw_objects, crt_materials = _collect_objects(
        context, only_selected, apply_modifiers, uv_wrap)
    if not raw_objects:
        raise RuntimeError("No mesh objects to export "
                           "(or none selected, if 'Only Selected' is on).")

    # Smooth shading is a per-material flag in the CRT format but per-face in
    # Blender: OR each mesh's smoothing into the material it uses.
    smooth_by_material = _collect_smooth_by_material(context, only_selected, apply_modifiers)

    textures, materials, material_indices = _collect_materials(
        raw_objects, crt_materials,
        [smooth_by_material.get(m.name if m is not None else "__default__", False)
         for m in crt_materials])

    for obj, mi in zip(raw_objects, material_indices):
        obj["material_index"] = mi

    doc = {
        "settings": _collect_settings(context, bucket_size),
        "camera": camera,
        "textures": textures,
        "materials": materials,
        "objects": raw_objects,
    }
    lights = _collect_lights(context, only_selected)
    if lights:
        doc["lights"] = lights
    return doc


def _collect_smooth_by_material(context, only_selected, apply_modifiers):
    """Map Blender material name -> True if any mesh using it has a smooth face."""
    depsgraph = context.evaluated_depsgraph_get()
    candidates = context.selected_objects if only_selected else context.scene.objects
    result = {}
    for obj in candidates:
        if obj.type != "MESH":
            continue
        if not only_selected and obj.hide_get():
            continue
        mesh = obj.data
        any_smooth = any(p.use_smooth for p in mesh.polygons)
        if not any_smooth:
            continue
        material = _object_material(obj)
        key = material.name if material is not None else "__default__"
        result[key] = True
    return result


# ---------------------------------------------------------------------------
# Operator
# ---------------------------------------------------------------------------

class ExportCRTScene(Operator, ExportHelper):
    bl_idname = "export_scene.crtscene"
    bl_label = "Export CRT Scene"
    bl_description = "Export the scene to the CRT .crtscene JSON format"
    filename_ext = ".crtscene"
    filter_glob: StringProperty(default="*.crtscene", options={"HIDDEN"})

    bucket_size: IntProperty(
        name="Bucket Size", description="Render bucket size (must divide image size)",
        default=24, min=1, max=256,
    )
    only_selected: BoolProperty(
        name="Only Selected", description="Export only selected mesh/light objects",
        default=False,
    )
    apply_modifiers: BoolProperty(
        name="Apply Modifiers", description="Bake modifiers and world transforms",
        default=True,
    )
    uv_wrap: BoolProperty(
        name="Wrap UVs to [0,1)", description=(
            "The CRT schema constrains uvs to [0,1]; wrap repeated UVs "
            "instead of clamping"),
        default=True,
    )

    def execute(self, context):
        try:
            doc = _build_crtscene(
                context,
                bucket_size=self.bucket_size,
                only_selected=self.only_selected,
                apply_modifiers=self.apply_modifiers,
                uv_wrap=self.uv_wrap,
            )
        except RuntimeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)
        self.report({"INFO"}, f"Exported {len(doc['objects'])} object(s) to "
                              f"{self.filepath}")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def menu_func_export(self, context):
    self.layout.operator(ExportCRTScene.bl_idname, text="CRT Scene (.crtscene)")


def register():
    bpy.utils.register_class(ExportCRTScene)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.utils.unregister_class(ExportCRTScene)


if __name__ == "__main__":
    register()
