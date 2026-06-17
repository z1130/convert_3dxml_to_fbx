"""verify_export_scale.py - build lzh.3dxml once, export under 4 unit-scale
configs, patch each to USF=100, re-import to report root scale + vertex SIZE.

Goal: find the export config that yields root scale=(1,1,1) with meter-scale
vertices (matching the modeller's reference), proving the fix does NOT shrink
geometry 100x. Read-only experiment - writes only to the system temp dir.
"""
import os
import sys
import zipfile
import tempfile
import xml.etree.ElementTree as ET
from mathutils import Matrix

import bpy
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)  # project root: convert_3dxml_to_fbx + diagnose_fbx_units live there
sys.path.insert(0, _ROOT)
import convert_3dxml_to_fbx as C
import diagnose_fbx_units as D

IN = os.path.join(_ROOT, 'lzh.3dxml')
REF = os.path.join(_ROOT, '3L氮气瓶的安装GU2291010-000-001.fbx')

BASE = dict(use_selection=False, object_types={'EMPTY', 'MESH'},
            mesh_smooth_type='FACE', use_mesh_modifiers=True, bake_anim=False,
            add_leaf_bones=False, use_metadata=False,
            axis_forward='-Z', axis_up='Y')

CONFIGS = [
    ('A_u1.0_ausF_gs1.0',   1.0,  dict(apply_unit_scale=False, global_scale=1.0)),
    ('E_u0.01_ausF_gs1.0',  0.01, dict(apply_unit_scale=False, global_scale=1.0)),
    ('F_u0.01_ausT_gs1.0',  0.01, dict(apply_unit_scale=True,  global_scale=1.0)),
    ('G_u0.01_ausT_gs0.01', 0.01, dict(apply_unit_scale=True,  global_scale=0.01)),
    ('H_u1.0_ausT_gs0.01',  1.0,  dict(apply_unit_scale=True,  global_scale=0.01)),
]


def build_scene():
    C.TMPDIR = tempfile.mkdtemp(prefix='ver_')
    with zipfile.ZipFile(IN) as z:
        z.extractall(C.TMPDIR)
    manifest = ET.parse(os.path.join(C.TMPDIR, 'Manifest.xml')).getroot()
    main_file = 'test.3dxml'
    for el in manifest:
        if C.lname(el.tag) == 'Root':
            main_file = el.text.strip()
            break
    C.clear_scene()
    C.NODE_COUNT = 0
    root_ref, C.REFERENCES, C.INSTANCES = C.parse_structure(
        os.path.join(C.TMPDIR, main_file))
    root_obj = bpy.data.objects.new(
        C.REFERENCES.get(root_ref, {}).get('name', 'Root'), None)
    C.link_obj(root_obj)
    tops = [i for i in C.INSTANCES if i['agg'] == root_ref]
    for top in tops:
        C.expand(top, root_obj, 0)
    if not tops:
        info = C.REFERENCES.get(root_ref)
        if info and info['rep_file']:
            mesh = C.build_object_mesh(info['rep_file'])
            if mesh:
                part = bpy.data.objects.new(info.get('name') or 'Part', mesh)
                C.link_obj(part)
                part.parent = root_obj
                part.matrix_parent_inverse = Matrix.Identity(4)


def clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for m in list(bpy.data.meshes):
        bpy.data.meshes.remove(m)


def inspect(path):
    clear()
    bpy.ops.import_scene.fbx(filepath=path)
    roots = [o for o in bpy.data.objects if o.parent is None]
    rs = roots[0].scale if roots else None
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
    size = (maxs[0] - mins[0], maxs[1] - mins[1], maxs[2] - mins[2]) if n else None
    return rs, size


def fmt(rs, size):
    rss = f'({rs.x:.4f},{rs.y:.4f},{rs.z:.4f})' if rs else 'None'
    szs = f'({size[0]:.4f},{size[1]:.4f},{size[2]:.4f})' if size else 'empty'
    return f'root_scale={rss}  vertSIZE={szs}'


build_scene()
us = bpy.context.scene.unit_settings

print('\n=== export phase (scene unchanged by export) ===')
outs = {}
for name, unit_scale, cfg in CONFIGS:
    us.scale_length = unit_scale
    out = os.path.join(tempfile.gettempdir(), f'ver_{name}.fbx')
    try:
        bpy.ops.export_scene.fbx(filepath=out, **dict(BASE, **cfg))
        outs[name] = out
        print(f'  exported {name}  (scene scale_length={unit_scale})')
    except Exception as e:
        print(f'  {name} EXPORT FAIL {e}')

print('\n=== inspect (all patched USF=100) ===')
for name, path in outs.items():
    try:
        D.patch(path, path)
        rs, size = inspect(path)
        print(f'{name:22} {fmt(rs, size)}')
    except Exception as e:
        print(f'{name:22} INSPECT FAIL {e}')
rs, size = inspect(REF)
print(f'{"REFERENCE":22} {fmt(rs, size)}  <- target')
