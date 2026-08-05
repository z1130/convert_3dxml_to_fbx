"""verify_fbx.py - round-trip check: import the generated FBX and report
structure / geometry / materials / bounding box.

运行方式：
  python converter/verify_fbx.py output.fbx      （系统 Python 3.13 + ./vendor/bpy）
或被 convert.py 在进程内调用：verify_fbx.verify(path)。
"""
import os
import sys

# 允许在系统 Python（3.13）下直接运行：把项目根目录 ./vendor 加入 sys.path 以加载 bpy。
_PIP_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'vendor'))
if os.path.isdir(_PIP_DIR) and _PIP_DIR not in sys.path:
    sys.path.insert(0, _PIP_DIR)

import bpy
from mathutils import Vector


def verify(fbx):
    """Import the FBX into a clean scene and print structure / geometry /
    materials / world bounding box."""
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


def main():
    argv = sys.argv[1:]
    fbx = argv[0] if argv else 'output.fbx'
    verify(fbx)


if __name__ == '__main__':
    main()
