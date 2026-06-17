"""compare_fbx.py - read raw FBX binary: vertex array magnitude + Model transforms.
No importer interpretation — just the numbers stored in the file.

  python compare_fbx.py a.fbx b.fbx
"""
import struct
import sys
import zlib


def u32(data, pos):
    return struct.unpack('<I', data[pos:pos + 4])[0]


def read_prop(data, pos):
    t = chr(data[pos]); pos += 1
    if t in ('S', 'R'):
        n = u32(data, pos); pos += 4
        v = data[pos:pos + n]; pos += n
        return (v.decode('utf-8', 'replace') if t == 'S' else v), pos
    if t == 'Y': return struct.unpack('<h', data[pos:pos + 2])[0], pos + 2
    if t == 'C': return data[pos] != 0, pos + 1
    if t == 'I': return struct.unpack('<i', data[pos:pos + 4])[0], pos + 4
    if t == 'F': return struct.unpack('<f', data[pos:pos + 4])[0], pos + 4
    if t == 'D': return struct.unpack('<d', data[pos:pos + 8])[0], pos + 8
    if t == 'L': return struct.unpack('<q', data[pos:pos + 8])[0], pos + 8
    if t in ('f', 'i', 'd', 'l', 'b'):
        enc = u32(data, pos); pos += 4
        stored = u32(data, pos); pos += 4
        decomp = u32(data, pos); pos += 4
        size = {'f': 4, 'i': 4, 'd': 8, 'l': 8, 'b': 1}[t]
        blob = data[pos:pos + stored]; pos += stored
        if enc == 0:
            raw = blob
        else:
            try:
                raw = zlib.decompress(blob)
            except zlib.error:
                raw = zlib.decompress(blob, -15)        # raw deflate fallback
        count = decomp // size
        fmt = {'f': '<f', 'i': '<i', 'd': '<d', 'l': '<q', 'b': '<B'}[t]
        vals = list(struct.unpack(fmt * count, raw)) if count else []
        return ('array', vals), pos
    raise ValueError(f'bad prop type {t!r} at {pos}')


def parse_nodes(data, pos, end):
    nodes = []
    while pos + 13 <= end:
        eo = u32(data, pos)
        np_ = u32(data, pos + 4)
        pl = u32(data, pos + 8)
        nl = data[pos + 12]
        if eo == 0 and np_ == 0 and pl == 0 and nl == 0:
            break
        pos += 13
        name = data[pos:pos + nl].decode('utf-8', 'replace'); pos += nl
        props = []
        for _ in range(np_):
            v, pos = read_prop(data, pos)
            props.append(v)
        children = parse_nodes(data, pos, eo)
        pos = eo
        nodes.append((name, props, children))
    return nodes


def walk(nodes, pred, out):
    for name, props, children in nodes:
        if pred(name, props):
            out.append((name, props, children))
        walk(children, pred, out)


def analyze(path):
    data = open(path, 'rb').read()
    top = parse_nodes(data, 27, len(data))

    geos = []; walk(top, lambda nm, p: nm == 'Geometry', geos)
    mn = [1e99] * 3; mx = [-1e99] * 3; nverts = 0; ngeo = 0
    for _, _, gch in geos:
        vn = []; walk(gch, lambda nm, p: nm == 'Vertices', vn)
        for _, vp, _ in vn:
            for pr in vp:
                if isinstance(pr, tuple) and pr[0] == 'array' and len(pr[1]) >= 3:
                    vals = pr[1]
                    for i in range(0, len(vals) - 2, 3):
                        for j in range(3):
                            v = vals[i + j]
                            if v < mn[j]: mn[j] = v
                            if v > mx[j]: mx[j] = v
                        nverts += 1
                    ngeo += 1

    models = []; walk(top, lambda nm, p: nm == 'Model', models)
    print(f'--- {path} ---')
    print(f'  geos_with_verts={ngeo}  total_verts={nverts}')
    if nverts:
        print(f'  vertex min=({mn[0]:.4f},{mn[1]:.4f},{mn[2]:.4f})')
        print(f'  vertex max=({mx[0]:.4f},{mx[1]:.4f},{mx[2]:.4f})')
        print(f'  vertex SIZE=({mx[0]-mn[0]:.4f},{mx[1]-mn[1]:.4f},{mx[2]-mn[2]:.4f})')
    print(f'  models={len(models)}')
    for i, (_, mp, mch) in enumerate(models[:8]):
        name = mp[1] if len(mp) > 1 else '?'
        p70 = [c[2] for c in mch if c[0] == 'Properties70']
        p70 = p70[0] if p70 else []
        tr = sc = None
        for pn in p70:
            if pn[0] == 'P' and len(pn[1]) >= 7 and pn[1][0] in ('LclTranslation', 'LclScaling'):
                v = (pn[1][4], pn[1][5], pn[1][6])
                if pn[1][0] == 'LclTranslation': tr = v
                else: sc = v
        scs = f'({sc[0]:.4f},{sc[1]:.4f},{sc[2]:.4f})' if sc else None
        trs = f'({tr[0]:.3f},{tr[1]:.3f},{tr[2]:.3f})' if tr else None
        print(f'    [{i}] {name}  LclScaling={scs}  LclTranslation={trs}')


for p in sys.argv[1:]:
    try:
        analyze(p)
    except Exception as e:
        print(f'--- {p} --- ERROR: {e}')
