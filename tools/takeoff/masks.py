"""True (clipped) white-mask polygons from the extended drawing list."""
import pymupdf as fitz, json
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

def items_to_poly(items, M):
    pts = []
    for it in items:
        if it[0] == 'l':
            a = fitz.Point(it[1]) * M; b = fitz.Point(it[2]) * M
            if not pts: pts.append((a.x, a.y))
            pts.append((b.x, b.y))
        elif it[0] == 'c':
            for q in it[1:5]:
                q = fitz.Point(q) * M; pts.append((q.x, q.y))
        elif it[0] == 're':
            r = fitz.Rect(it[1]) * M
            return box(r.x0, r.y0, r.x1, r.y1)
        elif it[0] == 'qu':
            q = it[1]
            return Polygon([tuple(fitz.Point(v) * M) for v in (q.ul, q.ur, q.lr, q.ll)])
    if len(pts) >= 3:
        P = Polygon(pts)
        if not P.is_valid: P = P.buffer(0)
        return P
    return None

def extract_masks(fn):
    d = fitz.open(f"{fn}.pdf"); p = d[0]; M = p.rotation_matrix
    dx = p.get_drawings(extended=True)
    out = []
    clip_stack = {}  # level -> polygon
    for g in dx:
        lvl = g.get('level', 0)
        # drop deeper clips when a shallower item appears
        for k in [k for k in clip_stack if k >= lvl]:
            del clip_stack[k]
        if g['type'] == 'clip':
            poly = items_to_poly(g['items'], M)
            clip_stack[lvl] = poly
            continue
        if g['type'] == 'f' and g.get('fill') and min(g['fill']) > 0.99:
            r = fitz.Rect(g['rect']) * M
            shape = box(r.x0, r.y0, r.x1, r.y1)
            for k in sorted(clip_stack):
                c = clip_stack[k]
                if c is not None and c.area < 1e6:
                    shape = shape.intersection(c)
            out.append(dict(seqno=g.get('seqno'), rect=[r.x0, r.y0, r.x1, r.y1], wkt=shape.wkt, area=shape.area))
    return out

if __name__ == "__main__":
    for fn in ("east", "west"):
        ms = extract_masks(fn)
        json.dump(ms, open(f"{fn}_masks.json", "w"))
        import numpy as np
        ratios = [m['area'] / max((m['rect'][2]-m['rect'][0])*(m['rect'][3]-m['rect'][1]), 1e-9) for m in ms]
        print(fn, len(ms), "masks; clipped (area < 97% of bbox):", sum(1 for r in ratios if r < 0.97))
