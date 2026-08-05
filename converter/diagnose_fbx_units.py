"""diagnose_fbx_units.py - read & patch FBX binary GlobalSettings unit metadata.

Why: Blender's io_scene_fbx hardcodes UnitScaleFactor=1.0. Unity reads it and
scales the model by USF/100, so a Blender-exported FBX appears 100x too small
in Unity (while Three.js ignores USF and looks fine). The fix is to rewrite
the UnitScaleFactor / OriginalUnitScaleFactor doubles to 100.0 in-place.

Usage:
  python diagnose_fbx_units.py a.fbx b.fbx                 # report
  python diagnose_fbx_units.py --patch in.fbx out.fbx      # patch USF -> 100
"""
import struct
import sys

DOUBLE_100 = struct.pack('<d', 100.0)
TARGET_KEYS = ('UnitScaleFactor', 'OriginalUnitScaleFactor')


def _read_prop(data, pos):
    """Return (value, new_pos, data_start). data_start is the byte right after
    the type char — for scalar types it is exactly where the value bytes begin."""
    t = chr(data[pos]); pos += 1
    data_start = pos
    if t in ('S', 'R'):
        n = struct.unpack('<I', data[pos:pos + 4])[0]; pos += 4
        v = data[pos:pos + n]; pos += n
        return (v.decode('utf-8', 'replace') if t == 'S' else v), pos, data_start
    if t == 'Y':
        return struct.unpack('<h', data[pos:pos + 2])[0], pos + 2, data_start
    if t == 'C':
        return data[pos] != 0, pos + 1, data_start
    if t == 'I':
        return struct.unpack('<i', data[pos:pos + 4])[0], pos + 4, data_start
    if t == 'F':
        return struct.unpack('<f', data[pos:pos + 4])[0], pos + 4, data_start
    if t == 'D':
        return struct.unpack('<d', data[pos:pos + 8])[0], pos + 8, data_start
    if t == 'L':
        return struct.unpack('<q', data[pos:pos + 8])[0], pos + 8, data_start
    if t in ('f', 'i', 'd', 'l', 'b'):
        pos += 4
        pos += 4
        comp = struct.unpack('<I', data[pos:pos + 4])[0]; pos += 4
        pos += comp
        return '[array]', pos, data_start
    raise ValueError(f'unknown prop type {t!r} at {pos}')


def _parse_nodes(data, pos, end):
    nodes = []
    while pos + 13 <= end:
        end_offset = struct.unpack('<I', data[pos:pos + 4])[0]
        num_props = struct.unpack('<I', data[pos + 4:pos + 8])[0]
        prop_len = struct.unpack('<I', data[pos + 8:pos + 12])[0]
        name_len = data[pos + 12]
        if end_offset == 0 and num_props == 0 and prop_len == 0 and name_len == 0:
            break
        pos += 13
        name = data[pos:pos + name_len].decode('utf-8', 'replace'); pos += name_len
        props = []
        for _ in range(num_props):
            v, pos, vstart = _read_prop(data, pos)
            props.append((v, vstart))
        children = _parse_nodes(data, pos, end_offset)
        pos = end_offset
        nodes.append((name, props, children))
    return nodes


def _find(nodes, target):
    for name, props, children in nodes:
        if name == target:
            return props, children
        r = _find(children, target)
        if r:
            return r
    return None


def _collect_usf_offsets(nodes, out):
    """Walk Properties70 -> P nodes, record double offset for target keys."""
    for name, props, children in nodes:
        if name == 'P' and props and props[0][0] in TARGET_KEYS:
            # P layout: name, type, subtype, "", value  -> value is props[4]
            if len(props) >= 5:
                val, vstart = props[4]
                key = props[0][0]
                out[key] = (vstart, val)
        _collect_usf_offsets(children, out)


def read_unit_metadata(path):
    with open(path, 'rb') as f:
        data = f.read()
    assert data[:18] == b'Kaydara FBX Binary', 'not a binary FBX'
    version = struct.unpack('<I', data[23:27])[0]
    top = _parse_nodes(data, 27, len(data))
    gs = _find(top, 'GlobalSettings')
    offsets = {}
    if gs:
        _, children = gs
        p70 = _find(children, 'Properties70')
        if p70:
            _, pchildren = p70
            _collect_usf_offsets(pchildren, offsets)
    return data, version, offsets


def report(path):
    _, version, offsets = read_unit_metadata(path)
    print(f'--- {path}  (FBX {version}) ---')
    if not offsets:
        print('  (no UnitScaleFactor found)')
        return
    for k in TARGET_KEYS:
        if k in offsets:
            _, val = offsets[k]
            print(f'  {k} = {val}')


def patch(in_path, out_path):
    data, version, offsets = read_unit_metadata(in_path)
    buf = bytearray(data)
    changed = []
    for k in TARGET_KEYS:
        if k in offsets:
            vstart, _ = offsets[k]
            current = struct.unpack('<d', buf[vstart:vstart + 8])[0]
            buf[vstart:vstart + 8] = DOUBLE_100
            changed.append(f'{k}: {current} -> 100.0')
        else:
            print(f'[warn] {k} not found, skipped')
    with open(out_path, 'wb') as f:
        f.write(buf)
    print(f'[patch] {in_path} -> {out_path}  (FBX {version})')
    for c in changed:
        print(f'  {c}')


def main():
    args = sys.argv[1:]
    if args and args[0] == '--patch':
        patch(args[1], args[2])
    else:
        for p in args:
            report(p)


if __name__ == '__main__':
    main()
