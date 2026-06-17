"""test_split_11.py - SPLIT-mesh experiment on 11.3dxml (does NOT touch the
main converter). Builds one mesh per PolygonalRepType solid under the root
Reference3D, exports with the same unit recipe, for comparison against the
current merged output and the modeller's reference.

  blender --background --factory-startup --python __test__/test_split_11.py
"""
import os
import sys
import zipfile
import tempfile
import xml.etree.ElementTree as ET
from mathutils import Matrix, Vector

import bpy
ROOT = r'f:\3dxml-converter'
sys.path.insert(0, ROOT)
import convert_3dxml_to_fbx as C

IN = os.path.join(ROOT, 'resources', '11.3dxml')
OUT = os.path.join(ROOT, '11_split.fbx')


def parse_rep_solids(path):
    """Return [(name, verts, tris)], one entry per PolygonalRepType solid.
    Each solid has its own vertex array (base=0), so no cross-solid offset."""
    root = ET.parse(path).getroot()
    solids = []
    polys = [el for el in root.iter()
             if C.lname(el.tag) == 'Rep' and el.get(C.XSI_TYPE) == 'PolygonalRepType']
    for i, rep in enumerate(polys):
        vb = C.child(rep, 'VertexBuffer')
        if vb is None:
            continue
        pos = C.parse_vec3s(C.text_of(vb, 'Positions') or '')
        if not pos:
            continue
        verts = [(p[0] * C.MM_TO_M, p[1] * C.MM_TO_M, p[2] * C.MM_TO_M) for p in pos]
        faces_el = C.child(rep, 'Faces')
        if faces_el is None:
            lods = C.children(rep, 'PolygonalLOD')
            if lods:
                lods.sort(key=lambda l: float(l.get('accuracy', '1e9')))
                faces_el = C.child(lods[0], 'Faces')
        if faces_el is None:
            continue
        tris = []
        for face in faces_el:
            rgba = C.face_color(face)
            for a, b, c in C.expand_face(face, 0):  # base=0: independent verts
                tris.append((a, b, c, rgba))
        if tris:
            sid = rep.get('id', str(i))
            solids.append((f'solid_{sid}', verts, tris))
            print(f'  [solid] id={sid} verts={len(verts)} tris={len(tris)}')
    return solids


# --- build scene (single-part: root Reference3D carries rep_file) ---
C.TMPDIR = tempfile.mkdtemp(prefix='split_')
with zipfile.ZipFile(IN) as z:
    z.extractall(C.TMPDIR)
manifest = ET.parse(os.path.join(C.TMPDIR, 'Manifest.xml')).getroot()
main_file = 'test.3dxml'
for el in manifest:
    if C.lname(el.tag) == 'Root':
        main_file = el.text.strip()
        break

C.clear_scene()  # sets scene unit scale_length=0.01
C.NODE_COUNT = 0
C.MESH_COUNT = 0
root_ref, C.REFERENCES, C.INSTANCES = C.parse_structure(
    os.path.join(C.TMPDIR, main_file))
root_info = C.REFERENCES.get(root_ref)
root_obj = bpy.data.objects.new(
    (root_info or {}).get('name', 'Root'), None)
C.link_obj(root_obj)

rep_file = (root_info or {}).get('rep_file')
solids = parse_rep_solids(os.path.join(C.TMPDIR, rep_file)) if rep_file else []
print(f'[info] {rep_file}: {len(solids)} solids parsed')
base = rep_file.replace('.3DRep', '') if rep_file else 'part'
for name, verts, tris in solids:
    C.MESH_COUNT += 1
    mesh = C.build_mesh_data(f'{base}_{name}_{C.MESH_COUNT}', verts, tris)
    obj = bpy.data.objects.new(name, mesh)
    C.link_obj(obj)
    obj.parent = root_obj
    obj.matrix_parent_inverse = Matrix.Identity(4)
    C.NODE_COUNT += 1

# bbox-center pivot (same as main)
bpy.context.view_layer.update()
mins, maxs = C.world_bbox()
if mins is not None:
    cen = Vector(((mins[0] + maxs[0]) / 2, (mins[1] + maxs[1]) / 2,
                  (mins[2] + maxs[2]) / 2))
    root_obj.location = cen
    for top in list(root_obj.children):
        m = top.matrix_basis.copy()
        m.translation -= cen
        top.matrix_basis = m

C.export_fbx(OUT)
mesh_objs = [o for o in bpy.data.objects if o.type == 'MESH']
tv = sum(len(o.data.vertices) for o in mesh_objs)
tf = sum(len(o.data.polygons) for o in mesh_objs)
print(f'[ok] {OUT} ({os.path.getsize(OUT)}B)')
print(f'[ok] nodes={C.NODE_COUNT} mesh_objects={len(mesh_objs)} '
      f'verts={tv} faces={tf}')
