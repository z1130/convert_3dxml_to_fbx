"""
convert_3dxml_to_fbx.py
=======================
3DXML (Dassault CATIA V5, zip) -> FBX converter.

Output is engineered for compatibility with three.js THREE.FBXLoader:
  - binary FBX 7.4, Y-up / -Z forward
  - assembly tree preserved (Empty -> three.js Group)
  - instance tree expanded (FBXLoader has no instancing)
  - per-face RGBA color -> multi-material mesh
  - pure triangulated meshes, no animation/bones

Run inside Blender (headless):
  blender --background --python convert_3dxml_to_fbx.py -- input.3dxml output.fbx
"""
import os
import sys
import zipfile
import tempfile
import traceback
import xml.etree.ElementTree as ET
from mathutils import Matrix, Vector

try:
    import bpy
except ImportError:
    raise SystemExit("This script must be run inside Blender (no 'bpy' module).")

XSI_TYPE = '{http://www.w3.org/2001/XMLSchema-instance}type'
MM_TO_M = 0.001  # 3DXML geometry/translation are in mm; export in meters so FBX root scale=1


# --------------------------------------------------------------------------- #
# XML helpers (namespace-agnostic: match on local tag name)
# --------------------------------------------------------------------------- #
def lname(tag):
    return tag.rsplit('}', 1)[-1] if '}' in tag else tag


def child(el, name):
    for c in el:
        if lname(c.tag) == name:
            return c
    return None


def children(el, name):
    return [c for c in el if lname(c.tag) == name]


def text_of(el, name):
    c = child(el, name)
    return c.text.strip() if (c is not None and c.text) else None


def parse_vec3s(s):
    """'x y z,x y z,...' -> [(x,y,z), ...]"""
    out = []
    for tok in s.split(','):
        tok = tok.strip()
        if not tok:
            continue
        p = tok.split()
        if len(p) >= 3:
            out.append((float(p[0]), float(p[1]), float(p[2])))
    return out


# --------------------------------------------------------------------------- #
# 3DRep geometry parsing
# --------------------------------------------------------------------------- #
def face_color(face):
    sa = child(face, 'SurfaceAttributes')
    col = child(sa, 'Color') if sa is not None else None
    if col is None:
        return (0.8, 0.8, 0.8, 1.0)
    return (float(col.get('red', '0.8')),
            float(col.get('green', '0.8')),
            float(col.get('blue', '0.8')),
            float(col.get('alpha', '1')))


def expand_face(face, base):
    """Turn a <Face triangles/strips/fans> into absolute (a,b,c) triangles.

    `base` is the vertex offset of the owning PolygonalRepType inside the
    merged vertex array.
    """
    tris = []
    t = face.get('triangles')
    if t:
        idx = [int(x) for x in t.split()]
        for i in range(0, len(idx) - 2, 3):
            tris.append((idx[i] + base, idx[i + 1] + base, idx[i + 2] + base))
    s = face.get('strips')
    if s:
        for strip in s.split(','):
            v = [int(x) for x in strip.split()]
            for i in range(len(v) - 2):
                a, b, c = v[i] + base, v[i + 1] + base, v[i + 2] + base
                if i % 2 == 1:  # flip winding on odd triangles for consistent normals
                    a, b = b, a
                tris.append((a, b, c))
    f = face.get('fans')
    if f:
        for fan in f.split(','):
            v = [int(x) for x in fan.split()]
            if len(v) < 3:
                continue
            center = v[0] + base
            for i in range(1, len(v) - 1):
                tris.append((center, v[i] + base, v[i + 1] + base))
    return tris


def parse_rep_file(path):
    """Parse one .3DRep -> (verts, norms, tris).

    All PolygonalRepType entries in the file are merged into a single mesh
    (one part = one mesh). `tris` items are (a, b, c, rgba).
    """
    root = ET.parse(path).getroot()
    verts, norms, tris = [], [], []
    polys = [el for el in root.iter()
             if lname(el.tag) == 'Rep' and el.get(XSI_TYPE) == 'PolygonalRepType']
    for rep in polys:
        vb = child(rep, 'VertexBuffer')
        if vb is None:
            continue
        pos = parse_vec3s(text_of(vb, 'Positions') or '')
        if not pos:
            continue
        nor = parse_vec3s(text_of(vb, 'Normals') or '')
        base = len(verts)
        verts.extend((p[0] * MM_TO_M, p[1] * MM_TO_M, p[2] * MM_TO_M) for p in pos)
        norms.extend(nor if len(nor) == len(pos)
                     else [(0.0, 0.0, 1.0)] * len(pos))

        # Prefer the direct <Faces> (full precision); fall back to the
        # smallest-accuracy <PolygonalLOD>.
        faces_el = child(rep, 'Faces')
        if faces_el is None:
            lods = children(rep, 'PolygonalLOD')
            if lods:
                lods.sort(key=lambda l: float(l.get('accuracy', '1e9')))
                faces_el = child(lods[0], 'Faces')
        if faces_el is None:
            continue
        for face in faces_el:
            rgba = face_color(face)
            for a, b, c in expand_face(face, base):
                tris.append((a, b, c, rgba))
    return verts, norms, tris


# --------------------------------------------------------------------------- #
# Blender mesh / material construction
# --------------------------------------------------------------------------- #
def make_material(name, rgba):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = None
    for n in mat.node_tree.nodes:
        if n.type == 'BSDF_PRINCIPLED':
            bsdf = n
            break
    if bsdf is not None:
        bsdf.inputs['Base Color'].default_value = (rgba[0], rgba[1], rgba[2], 1.0)
        if 'Roughness' in bsdf.inputs:
            bsdf.inputs['Roughness'].default_value = 0.5
        if 'Metallic' in bsdf.inputs:
            bsdf.inputs['Metallic'].default_value = 0.0
    if rgba[3] < 1.0:
        try:
            mat.blend_method = 'BLEND'
        except Exception:
            pass
    return mat


def build_mesh_data(name, verts, tris):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], [(a, b, c) for (a, b, c, _) in tris])
    mesh.update()

    color_to_idx = {}
    for (_, _, _, rgba) in tris:
        if rgba not in color_to_idx:
            color_to_idx[rgba] = len(color_to_idx)
    for rgba, idx in sorted(color_to_idx.items(), key=lambda kv: kv[1]):
        mesh.materials.append(make_material(f"{name}_{idx}", rgba))
    for poly, (_, _, _, rgba) in zip(mesh.polygons, tris):
        poly.material_index = color_to_idx[rgba]
        poly.use_smooth = True
    return mesh


# --------------------------------------------------------------------------- #
# Product structure (assembly tree)
# --------------------------------------------------------------------------- #
def parse_structure(main_path):
    root = ET.parse(main_path).getroot()
    ps = None
    for el in root.iter():
        if lname(el.tag) == 'ProductStructure':
            ps = el
            break
    root_ref = ps.get('root')
    references = {}
    instances = []
    for el in ps:
        ln = lname(el.tag)
        if ln == 'Reference3D':
            references[el.get('id')] = {'name': el.get('name'), 'rep_file': None}
        elif ln == 'Instance3D':
            instances.append({
                'id': el.get('id'),
                'name': el.get('name'),
                'agg': text_of(el, 'IsAggregatedBy'),
                'inst': text_of(el, 'IsInstanceOf'),
                'matrix': text_of(el, 'RelativeMatrix'),
            })
    # ReferenceRep.id -> geometry file
    repref_file = {}
    for el in ps:
        if lname(el.tag) == 'ReferenceRep':
            af = (el.get('associatedFile', '') or '')
            repref_file[el.get('id')] = af.split(':')[-1] if af else None
    # InstanceRep bridges Reference3D <-> ReferenceRep:
    #   IsAggregatedBy = owning Reference3D id, IsInstanceOf = ReferenceRep id
    for el in ps:
        if lname(el.tag) == 'InstanceRep':
            ref_id = text_of(el, 'IsAggregatedBy')
            repref_id = text_of(el, 'IsInstanceOf')
            if ref_id in references and repref_id in repref_file:
                references[ref_id]['rep_file'] = repref_file[repref_id]
    return root_ref, references, instances


def relmatrix_to_mat4(text):
    """12 floats -> Blender Matrix.

    3DXML RelativeMatrix: first 9 = rotation, last 3 = translation. The
    rotation is stored in COLUMN-major (OpenGL/GLC_lib) order, so the values
    fill the matrix by column. Translation maps local->parent coordinates,
    matching Blender's matrix_local (with identity parent_inverse).
    """
    v = [float(x) for x in text.split()]
    return Matrix((
        (v[0], v[3], v[6], v[9] * MM_TO_M),
        (v[1], v[4], v[7], v[10] * MM_TO_M),
        (v[2], v[5], v[8], v[11] * MM_TO_M),
        (0.0, 0.0, 0.0, 1.0),
    ))


# --------------------------------------------------------------------------- #
# Scene assembly (globals hold parsed structure for the recursive expander)
# --------------------------------------------------------------------------- #
TMPDIR = None
REFERENCES = None
INSTANCES = None
PARSE_CACHE = {}
NODE_COUNT = 0
MESH_COUNT = 0


def link_obj(obj):
    bpy.context.scene.collection.objects.link(obj)


def parse_cached(rep_file):
    """Cache the raw parse result (XML parsing is the slow part)."""
    if rep_file in PARSE_CACHE:
        return PARSE_CACHE[rep_file]
    path = os.path.join(TMPDIR, rep_file)
    if not os.path.exists(path):
        PARSE_CACHE[rep_file] = None
        return None
    verts, norms, tris = parse_rep_file(path)
    print(f"  [rep] {rep_file}: verts={len(verts)} tris={len(tris)}")
    res = (verts, norms, tris) if tris else None
    PARSE_CACHE[rep_file] = res
    return res


def build_object_mesh(rep_file):
    """Build a NEW mesh data per call. Sharing one mesh across multiple FBX
    objects confuses Blender's FBX exporter (material-index warnings) and can
    make THREE.FBXLoader drop materials, so each instance gets its own copy."""
    global MESH_COUNT
    if rep_file is None:
        return None
    res = parse_cached(rep_file)
    if res is None:
        return None
    verts, _norms, tris = res
    MESH_COUNT += 1
    return build_mesh_data(
        f"{rep_file.replace('.3DRep', '')}_{MESH_COUNT}", verts, tris)


def expand(inst, parent_obj, depth):
    global NODE_COUNT
    ref = REFERENCES.get(inst['inst'])
    name = inst['name'] or (ref['name'] if ref else 'node')
    mesh = build_object_mesh(ref['rep_file']) if ref else None
    children = [c for c in INSTANCES if c['agg'] == inst['inst']]
    # Skip geometry-less leaf nodes (e.g. standard parts whose .3DRep is empty)
    if mesh is None and not children:
        return
    obj = bpy.data.objects.new(name, mesh)  # mesh=None -> Empty (FBX Null)
    link_obj(obj)
    NODE_COUNT += 1
    if parent_obj is not None:
        obj.parent = parent_obj
        obj.matrix_parent_inverse = Matrix.Identity(4)
    if inst['matrix']:
        obj.matrix_basis = relmatrix_to_mat4(inst['matrix'])
    for ch in children:
        expand(ch, obj, depth + 1)


# --------------------------------------------------------------------------- #
# Scene reset & FBX export
# --------------------------------------------------------------------------- #
def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for col in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras,
                bpy.data.lights, bpy.data.images):
        for item in list(col):
            col.remove(item)


def world_bbox():
    """World-space bounding box ([min],[max]) over all mesh objects."""
    mins = [1e99, 1e99, 1e99]
    maxs = [-1e99, -1e99, -1e99]
    found = False
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        found = True
        for corner in obj.bound_box:
            wc = obj.matrix_world @ Vector(corner)
            for i in range(3):
                if wc[i] < mins[i]:
                    mins[i] = wc[i]
                if wc[i] > maxs[i]:
                    maxs[i] = wc[i]
    return (mins, maxs) if found else (None, None)


def export_fbx(filepath):
    """Export with FBXLoader-friendly options. Tolerates Blender 4.x/5.0
    parameter drift by falling back to a minimal kwarg set."""
    full = dict(
        filepath=filepath,
        use_selection=False,
        object_types={'EMPTY', 'MESH'},
        mesh_smooth_type='FACE',
        use_mesh_modifiers=True,
        bake_anim=False,
        add_leaf_bones=False,
        use_metadata=False,
        axis_forward='-Z',
        axis_up='Y',
        apply_unit_scale=True,
        global_scale=0.01,
    )
    try:
        bpy.ops.export_scene.fbx(**full)
        return True
    except (TypeError, KeyError) as e:
        print(f"[warn] full export kwargs rejected ({e}); retry minimal set")
    minimal = dict(filepath=filepath, use_selection=False,
                   object_types={'EMPTY', 'MESH'}, bake_anim=False)
    bpy.ops.export_scene.fbx(**minimal)
    return True


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    global TMPDIR, REFERENCES, INSTANCES, NODE_COUNT
    argv = sys.argv
    if '--' in argv:
        argv = argv[argv.index('--') + 1:]
    else:
        argv = []
    in_path = os.path.abspath(argv[0] if len(argv) > 0 else 'lzh.3dxml')
    out_path = os.path.abspath(argv[1] if len(argv) > 1 else 'out.fbx')

    print(f"[info] blender  = {bpy.app.version_string}")
    print(f"[info] input    = {in_path}")
    print(f"[info] output   = {out_path}")

    TMPDIR = tempfile.mkdtemp(prefix='3dxml_')
    with zipfile.ZipFile(in_path) as z:
        z.extractall(TMPDIR)

    manifest = ET.parse(os.path.join(TMPDIR, 'Manifest.xml')).getroot()
    main_file = 'test.3dxml'
    for el in manifest:
        if lname(el.tag) == 'Root':
            main_file = el.text.strip()
            break
    print(f"[info] structure= {main_file}")

    clear_scene()
    root_ref, REFERENCES, INSTANCES = parse_structure(os.path.join(TMPDIR, main_file))
    print(f"[info] references={len(REFERENCES)} instances={len(INSTANCES)} root_ref={root_ref}")

    root_obj = bpy.data.objects.new(
        REFERENCES.get(root_ref, {}).get('name', 'Root'), None)
    link_obj(root_obj)
    for top in [i for i in INSTANCES if i['agg'] == root_ref]:
        expand(top, root_obj, 0)

    # Lift the bounding-box center onto the root node: root.position = bbox center,
    # top-level children offset by -C. World coordinates stay identical (rendering
    # unchanged), but the root now carries a meaningful non-zero position so callers
    # can locate the model via root.position.
    bpy.context.view_layer.update()
    mins, maxs = world_bbox()
    if mins is not None:
        C = Vector(((mins[0] + maxs[0]) / 2.0,
                    (mins[1] + maxs[1]) / 2.0,
                    (mins[2] + maxs[2]) / 2.0))
        root_obj.location = C
        for top_obj in list(root_obj.children):
            m = top_obj.matrix_basis.copy()
            m.translation -= C
            top_obj.matrix_basis = m
        print(f"[info] root pivot @ bbox center: "
              f"({C.x:.4f},{C.y:.4f},{C.z:.4f})")

    mesh_objs = [o for o in bpy.data.objects if o.type == 'MESH']
    total_v = sum(len(o.data.vertices) for o in mesh_objs)
    total_f = sum(len(o.data.polygons) for o in mesh_objs)
    print(f"[info] nodes={NODE_COUNT} mesh_objects={len(mesh_objs)} "
          f"verts={total_v} faces={total_f}")

    export_fbx(out_path)
    if os.path.exists(out_path):
        print(f"[ok] FBX written: {out_path} ({os.path.getsize(out_path)} bytes)")
    else:
        print("[error] FBX not written")
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
