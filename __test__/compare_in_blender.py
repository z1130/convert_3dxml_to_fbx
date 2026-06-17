"""compare_in_blender.py - import two FBX files into Blender and print raw
vertex magnitude + per-node scale. Uses Blender's own (correct) FBX parser.

  blender --background --factory-startup --python compare_in_blender.py -- a.fbx b.fbx
"""
import sys
import bpy

argv = sys.argv
files = argv[argv.index('--') + 1:] if '--' in argv else []


def clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for m in list(bpy.data.meshes):
        bpy.data.meshes.remove(m)
    for c in list(bpy.data.collections):
        for o in list(c.objects):
            c.objects.unlink(o)


def show(o, d=0):
    ws = o.matrix_world.to_scale()
    bs = o.scale
    extra = ''
    if o.type == 'MESH':
        bb = [o.matrix_world @ __import__('mathutils').Vector(c) for c in o.bound_box]
        # local bbox size
        mn = [min(v[i] for v in o.data.vertices.co) if False else 0 for i in range(3)]
    print('  ' * d + f'- {o.name}[{o.type}] '
          f'basis_scale=({bs.x:.4f},{bs.y:.4f},{bs.z:.4f}) '
          f'world_scale=({ws.x:.4f},{ws.y:.4f},{ws.z:.4f})')
    for c in o.children:
        show(c, d + 1)


for path in files:
    clear()
    bpy.ops.import_scene.fbx(filepath=path)
    us = bpy.context.scene.unit_settings
    print(f'=== {path} ===')
    print(f'  scene scale_length={us.scale_length} system={us.system} length_unit={us.length_unit}')

    mins = [1e99] * 3
    maxs = [-1e99] * 3
    n = 0
    for o in bpy.data.objects:
        if o.type == 'MESH':
            for v in o.data.vertices:
                for i in range(3):
                    if v.co[i] < mins[i]:
                        mins[i] = v.co[i]
                    if v.co[i] > maxs[i]:
                        maxs[i] = v.co[i]
                n += 1
    if n:
        print(f'  total_verts={n}')
        print(f'  RAW vertex min=({mins[0]:.4f},{mins[1]:.4f},{mins[2]:.4f})')
        print(f'  RAW vertex max=({maxs[0]:.4f},{maxs[1]:.4f},{maxs[2]:.4f})')
        print(f'  RAW vertex SIZE=({maxs[0]-mins[0]:.4f},{maxs[1]-mins[1]:.4f},{maxs[2]-mins[2]:.4f})')

    roots = [o for o in bpy.data.objects if o.parent is None]
    for r in roots:
        show(r)
