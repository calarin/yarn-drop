#!/usr/bin/env python3
"""Read-only inventory of fourth-floor modelled objects from an IFC file.

The model is opened read-only and never written. For each candidate object the
script reports: GlobalId, IFC class, predefined/object type, Name, Tag, type name,
spatial container (storey / space), room number and name, global location and any
code-like values found in property sets (e.g. MFN-400). Pset values are read only.

Usage:
    python tools/ifc_inventory.py MODEL.ifc --storey "Level 4" -o deliverables/model_inventory.csv
    python tools/ifc_inventory.py MODEL.ifc --list-storeys
"""
import argparse, csv, re, sys

CODE_RE = re.compile(r'\b[A-Z]{2,4}-\d{3}(?:\.\d+)?[A-Z]*\b')
DEFAULT_CLASSES = ['IfcFurnishingElement', 'IfcSystemFurnitureElement', 'IfcFlowTerminal', 'IfcShadingDevice',
                   'IfcBuildingElementProxy', 'IfcDiscreteAccessory', 'IfcCovering']

def storeys(model):
    return sorted(model.by_type('IfcBuildingStorey'), key=lambda s: (s.Elevation if s.Elevation is not None else 0.0))

def pick_storey(model, spec):
    ss = storeys(model)
    if spec is None:
        cand = [s for s in ss if re.search(r'(^|[^0-9])(4|04|four|fourth)([^0-9]|$)', (s.Name or '') + ' ' + (s.LongName or ''), re.I)]
        if len(cand) == 1: return cand[0]
        raise SystemExit('Cannot pick the fourth-floor storey automatically; use --storey. Storeys: %s' %
                         ', '.join(repr(s.Name) for s in ss))
    for s in ss:
        if spec in (s.Name, s.LongName, s.GlobalId): return s
    raise SystemExit('Storey %r not found. Storeys: %s' % (spec, ', '.join(repr(s.Name) for s in ss)))

def decomposed_spaces(storey):
    out = []
    for rel in getattr(storey, 'IsDecomposedBy', []) or []:
        for o in rel.RelatedObjects:
            if o.is_a('IfcSpace'): out.append(o)
    return out

def container_of(el):
    for rel in getattr(el, 'ContainedInStructure', []) or []:
        return rel.RelatingStructure
    return None

def referenced_spaces(el):
    out = []
    for rel in getattr(el, 'ReferencedInStructures', []) or []:
        if rel.RelatingStructure.is_a('IfcSpace'): out.append(rel.RelatingStructure)
    return out

def storey_of(obj):
    seen = 0
    while obj is not None and seen < 10:
        if obj.is_a('IfcBuildingStorey'): return obj
        parent = None
        for rel in getattr(obj, 'Decomposes', []) or []:
            parent = rel.RelatingObject
        if parent is None:
            c = container_of(obj) if not obj.is_a('IfcSpatialStructureElement') else None
            parent = c
        obj = parent; seen += 1
    return None

def location(el, unit_scale=1.0):
    """Global placement origin in metres (project length unit x unit_scale)."""
    import ifcopenshell.util.placement as up
    if el.ObjectPlacement is None: return (None, None, None)
    m = up.get_local_placement(el.ObjectPlacement)
    return tuple(round(float(m[k][3]) * unit_scale, 4) for k in range(3))

def psets_flat(el):
    import ifcopenshell.util.element as ue
    flat = {}
    for pset, props in (ue.get_psets(el) or {}).items():
        for k, v in props.items():
            if k == 'id': continue
            flat['%s.%s' % (pset, k)] = v
    t = ue.get_type(el)
    if t is not None:
        for pset, props in (ue.get_psets(t) or {}).items():
            for k, v in props.items():
                if k == 'id': continue
                flat.setdefault('type:%s.%s' % (pset, k), v)
    return flat

def code_candidates(el, flat):
    vals = []
    for src, v in [('Name', el.Name), ('ObjectType', getattr(el, 'ObjectType', None)), ('Tag', getattr(el, 'Tag', None)),
                   ('Description', el.Description)] + sorted(flat.items()):
        if isinstance(v, str):
            for m in CODE_RE.findall(v):
                vals.append((m, src))
    return vals

def space_footprints(model, spaces):
    """XY polygons of spaces (requires ifcopenshell.geom); used only when elements are not related to a space."""
    import ifcopenshell.geom as geom
    from shapely.geometry import MultiPoint
    settings = geom.settings(); settings.set(settings.USE_WORLD_COORDS, True)
    out = {}
    for sp in spaces:
        try:
            sh = geom.create_shape(settings, sp)
            v = sh.geometry.verts
            pts = [(v[i], v[i + 1]) for i in range(0, len(v), 3)]
            out[sp.GlobalId] = MultiPoint(pts).convex_hull
        except Exception:
            pass
    return out

def inventory(path, storey_spec=None, classes=None, space_geometry=False):
    import ifcopenshell
    import ifcopenshell.util.unit as uu
    model = ifcopenshell.open(path)           # read-only use; the file is never written
    unit_scale = uu.calculate_unit_scale(model)   # project length unit -> metres
    st = pick_storey(model, storey_spec)
    spaces = decomposed_spaces(st)
    space_ids = {s.id() for s in spaces}
    fps = space_footprints(model, spaces) if space_geometry else {}
    rows = []
    classes = classes or DEFAULT_CLASSES
    seen = set()
    for cls in classes:
        for el in model.by_type(cls):
            if el.id() in seen: continue
            seen.add(el.id())
            cont = container_of(el)
            if cont is None: continue
            if not (cont.id() == st.id() or cont.id() in space_ids or storey_of(cont) == st):
                continue
            space = cont if cont.is_a('IfcSpace') else None
            how = 'contained in IfcSpace' if space else 'contained in storey'
            if space is None:
                refs = referenced_spaces(el)
                if refs: space, how = refs[0], 'referenced in IfcSpace'
            x, y, z = location(el, unit_scale)
            if space is None and fps and x is not None:
                from shapely.geometry import Point
                hit = [s for s in spaces if s.GlobalId in fps and fps[s.GlobalId].contains(Point(x, y))]
                if len(hit) == 1: space, how = hit[0], 'inside IfcSpace footprint (geometry test)'
                elif len(hit) > 1: how = 'inside several space footprints: ' + ','.join(h.Name or '' for h in hit)
            flat = psets_flat(el)
            codes = code_candidates(el, flat)
            import ifcopenshell.util.element as ue
            t = ue.get_type(el)
            rows.append(dict(
                global_id=el.GlobalId, ifc_class=el.is_a(), predefined_type=getattr(el, 'PredefinedType', '') or '',
                name=el.Name or '', object_type=getattr(el, 'ObjectType', '') or '', tag=getattr(el, 'Tag', '') or '',
                type_name=(t.Name if t is not None else ''), storey=st.Name or '',
                container=(cont.is_a() + ':' + (cont.Name or '')), room_number=(space.Name if space else ''),
                room_name=((space.LongName or '') if space else ''), room_method=how,
                x=x, y=y, z=z, location_unit='m',
                code_candidates='; '.join('%s (%s)' % c for c in codes),
                code=(codes[0][0] if len(set(c[0] for c in codes)) == 1 else ''),
                code_status=('single code' if len(set(c[0] for c in codes)) == 1 else ('conflicting codes' if codes else 'no code found')),
                psets_readonly='; '.join('%s=%s' % (k, v) for k, v in sorted(flat.items()) if v not in (None, ''))[:2000]))
    return st, rows

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('ifc')
    ap.add_argument('--storey', help='storey Name/LongName/GlobalId of the fourth floor')
    ap.add_argument('--list-storeys', action='store_true')
    ap.add_argument('--classes', help='comma separated IFC classes (default: furnishing, system furniture, flow terminals, shading, proxies, accessories, coverings)')
    ap.add_argument('--space-geometry', action='store_true', help='assign rooms by space footprint when an object is only contained in the storey')
    ap.add_argument('-o', '--out', default='model_inventory.csv')
    a = ap.parse_args(argv)
    if a.list_storeys:
        import ifcopenshell
        for s in storeys(ifcopenshell.open(a.ifc)):
            print('%-30s %-30s elev=%s  %s' % (s.Name, s.LongName, s.Elevation, s.GlobalId))
        return 0
    st, rows = inventory(a.ifc, a.storey, a.classes.split(',') if a.classes else None, a.space_geometry)
    fields = list(rows[0].keys()) if rows else ['global_id']
    with open(a.out, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    print('%d objects on storey %r -> %s' % (len(rows), st.Name, a.out))
    return 0

if __name__ == '__main__':
    sys.exit(main())
