# Blender `.crtscene` Exporter

Blender add-on that exports the current scene to the Chaos Ray Tracing
`.crtscene` JSON format (validated against `../schema.json`).

## Files

| File | Purpose |
|------|---------|
| `export_crtscene.py` | The add-on (single file). |
| `test_export_crtscene.py` | Offline test with a mocked `bpy` (no Blender needed). Run: `py-venv/bin/python blender/test_export_crtscene.py` |

## Install

1. Copy `export_crtscene.py` into Blender's addons directory, e.g.
   `~/.config/blender/<version>/scripts/addons/`.
2. Enable it: Edit → Preferences → Add-ons → search "CRT Scene" → tick the box.
3. Use it: File → Export → **CRT Scene (.crtscene)**.

Requires Blender ≥ 3.6.

## Options

| Option | Default | Meaning |
|--------|---------|---------|
| Bucket Size | 24 | `settings.image_settings.bucket_size`. Must divide the render resolution. |
| Only Selected | off | Export only selected mesh/light objects. |
| Apply Modifiers | on | Bake modifiers + world transforms into the exported vertices. |
| Wrap UVs to [0,1) | on | The schema constrains `uvs` to [0,1]; wrap repeated UVs instead of clamping (off = clamp). |

## Blender → CRT mapping

| CRT section | Source in Blender |
|-------------|-------------------|
| `settings.image_settings` | Render properties (resolution × percentage). |
| `settings.background_color` | `World > Surface > Color`. |
| `camera.position` | Active camera's world translation (`scene.camera`). |
| `camera.matrix` | Transpose of the camera's world 3×3 rotation, after the Z-up→Y-up frame change. The tracer uses `world = local * M` (row-vector, see `Renderer.cpp` + `Matrix3x3::operator*`), so `M = Rᵀ`. |
| `objects[].vertices` | Evaluated mesh, world-transformed, flattened xyz. |
| `objects[].triangles` | `calc_loop_triangles()` (CCW winding, matches the tracer's `cross(edge1, edge2)` normal convention). |
| `objects[].uvs` | 3 components per vertex (the format's `uvs[i]` is a vec3). Blender stores UVs per-loop; vertices are split where UVs differ across a seam, so each side of the seam keeps its own texture coordinates. |
| `materials[].type` | Principled BSDF heuristic: transmission > 0.5 → `refractive`; emission > 0 → `constant`; metallic > 0.5 or roughness < 0.2 → `reflective`; else `diffuse`. |
| `materials[].albedo` | Deduplicated `albedo_N` texture reference from `diffuse_color`. |
| `materials[].ior` | Principled `IOR` input (only for `refractive`), clamped to ≥ 1. |
| `materials[].smooth_shading` | OR of all exported meshes' smooth faces (`polygon.use_smooth`). |
| `textures[]` | One `albedo` texture per unique albedo color. |
| `lights[]` | `LIGHT` objects → `position` = world translation, `intensity` = energy. Omitted if no lights. |

## Known limitations

- **UV seams**: handled by splitting vertices where the same Blender vertex has
  different UVs across its loops (each seam side gets its own texture
  coordinates); loops with identical UVs stay shared, so smooth shading is
  preserved. Loose vertices (not referenced by any face) are dropped from the
  output.
- **Degenerate faces**: zero-area triangles (coincident or collinear vertices)
  are dropped, because the CRT loader normalises every triangle normal and
  throws on a zero vector. Fix the source mesh in Blender (e.g. merge by
  distance) if you want those faces back.
- **One material per object**: an object's first material slot is used; faces
  assigned to other slots of the same object are ignored. Give multi-material
  meshes separate objects.
- **Sun/area lights**: exported as a point position + intensity (the format has
  no direction/type). Tune `intensity` after export.
- **Checker/edges/bitmap textures** are not generated from node graphs; only
  flat albedo textures are emitted.
- **Smooth shading is OR'd per material**: Blender's per-face smoothing can't
  be represented exactly (the CRT flag is per-material).

## Axis convention

Blender is Z-up right-handed; the CRT tracer is **Y-up right-handed** (+X
right, +Y up, camera looks down −Z, see `Renderer.cpp renderBucket`). The
exporter converts everything — mesh vertices, camera position, camera
orientation matrix, and light positions — with the frame change
`(x, y, z) → (x, z, −y)`, a −90° rotation about X (det = +1, so right-handed
and winding-preserving). Build your Blender scene with Z as up; the exported
`.crtscene` will be Y-up.
