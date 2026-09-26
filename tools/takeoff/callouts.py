import pymupdf as fitz, json, re, math, sys

def is_black(c, tol=0.05):
    return c is not None and max(c) < tol

def prim(g, M):
    """Convert a drawing to a simplified primitive in display coordinates."""
    t = g['type']
    items = []
    for it in g['items']:
        if it[0] == 'l':
            a = fitz.Point(it[1]) * M; b = fitz.Point(it[2]) * M
            items.append(('l', (a.x, a.y), (b.x, b.y)))
        elif it[0] == 'c':
            pts = [fitz.Point(q) * M for q in it[1:5]]
            items.append(('c',) + tuple((q.x, q.y) for q in pts))
        elif it[0] == 're':
            r = fitz.Rect(it[1]) * M
            items.append(('re', (r.x0, r.y0, r.x1, r.y1)))
        elif it[0] == 'qu':
            q = it[1]
            pts = [fitz.Point(v) * M for v in (q.ul, q.ur, q.lr, q.ll)]
            items.append(('qu',) + tuple((v.x, v.y) for v in pts))
    r = fitz.Rect(g['rect']) * M
    return dict(type=t, color=g.get('color'), fill=g.get('fill'), width=g.get('width'),
                rect=(r.x0, r.y0, r.x1, r.y1), items=items, seqno=g.get('seqno'))

def load_prims(fn):
    d = fitz.open(fn); p = d[0]
    M = p.rotation_matrix
    dr = p.get_drawings()
    return [prim(g, M) for g in dr]

def is_dot(pr):
    if pr['type'] != 'f' or not is_black(pr['fill']): return False
    x0, y0, x1, y1 = pr['rect']
    w, h = x1 - x0, y1 - y0
    return 5.0 < w < 9.5 and 5.0 < h < 9.5 and all(it[0] == 'c' for it in pr['items'])

def seg_of(pr):
    if pr['type'] == 's' and len(pr['items']) == 1 and pr['items'][0][0] == 'l':
        return pr['items'][0][1], pr['items'][0][2]
    return None

if __name__ == "__main__":
    fn = sys.argv[1]
    P = load_prims(fn)
    json.dump(P, open(fn.replace('.pdf', '_prims.json'), 'w'))
    dots = [i for i, pr in enumerate(P) if is_dot(pr)]
    print(fn, "prims", len(P), "dots", len(dots), "first dot idx", dots[0] if dots else None)
