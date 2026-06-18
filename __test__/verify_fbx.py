"""verify_fbx.py - round-trip check: import the generated FBX and report
structure / geometry / materials / bounding box.

  blender --background --python verify_fbx.py -- output.fbx
"""
import sys
import bpy
from mathutils import Vector

argv = sys.argv
argv = argv[argv.index('--') + 1:] if '--' in argv else []
fbx = argv[0] if argv else 'output.fbx'

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

bpy.ops.import_scene.fbx(filepath=fbx)

mesh_objs = [o for o in bpy.data.objects if o.type == 'MESH']
empty_objs = [o for o in bpy.data.objects if o.type == 'EMPTY']
mats = list(bpy.data.materials)
total_v = sum(len(o.data.vertices) for o in mesh_objs)
total_f = sum(len(o.data.polygons) for o in mesh_objs)

print(f"[verify] objects={len(bpy.data.objects)} mesh={len(mesh_objs)} "
      f"empty={len(empty_objs)} materials={len(mats)}")
print(f"[verify] total_verts={total_v} total_faces={total_f}")


def show(o, d=0):
    extra = f" verts={len(o.data.vertices)} mats={len(o.data.materials)}" \
            if o.type == 'MESH' else ""
    print("  " * d + f"- {o.name} [{o.type}]{extra}")
    for c in o.children:
        show(c, d + 1)


for r in [o for o in bpy.data.objects if o.parent is None]:
    show(r)

print("[verify] material samples:")
for m in mats[:10]:
    c = None
    if m.use_nodes:
        bsdf = m.node_tree.nodes.get('Principled BSDF')
        if bsdf:
            c = bsdf.inputs['Base Color'].default_value
    print(f"  {m.name}: rgb=({c[0]:.3f},{c[1]:.3f},{c[2]:.3f})" if c else f"  {m.name}: (no bsdf)")

if mesh_objs:
    mins = [1e9] * 3
    maxs = [-1e9] * 3
    for o in mesh_objs:
        for corner in o.bound_box:
            wc = o.matrix_world @ Vector(corner)
            for i in range(3):
                mins[i] = min(mins[i], wc[i])
                maxs[i] = max(maxs[i], wc[i])
    print(f"[verify] world bbox min=({mins[0]:.1f},{mins[1]:.1f},{mins[2]:.1f}) "
          f"max=({maxs[0]:.1f},{maxs[1]:.1f},{maxs[2]:.1f})")
    print(f"[verify] size=({maxs[0]-mins[0]:.1f},"
          f"{maxs[1]-mins[1]:.1f},{maxs[2]-mins[2]:.1f})")
