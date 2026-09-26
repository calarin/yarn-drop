import pymupdf as fitz, json, math

def load(fn):
    d = fitz.open(fn); p = d[0]
    M = p.rotation_matrix
    return d, p, M

def tp(pt, M):
    q = fitz.Point(pt) * M
    return (q.x, q.y)

def trect(r, M):
    rr = fitz.Rect(r) * M
    return (rr.x0, rr.y0, rr.x1, rr.y1)

def spans(fn):
    d, p, M = load(fn)
    out = []
    blocks = p.get_text("rawdict")
    for bi, b in enumerate(blocks['blocks']):
        for li, l in enumerate(b.get('lines', [])):
            dx, dy = l['dir']
            # rotate direction vector
            ddx = M.a*dx + M.c*dy
            ddy = M.b*dx + M.d*dy
            for si, s in enumerate(l['spans']):
                text = "".join(ch['c'] for ch in s['chars'])
                bb = trect(s['bbox'], M)
                origin = tp(s['origin'], M)
                out.append(dict(text=text, bbox=bb, origin=origin, dir=(round(ddx,3), round(ddy,3)),
                                size=round(s['size'],2), font=s['font'], block=bi, line=li, span=si))
    return out

if __name__ == "__main__":
    import sys
    for fn in ["east.pdf", "west.pdf"]:
        sp = spans(fn)
        json.dump(sp, open(fn.replace(".pdf", "_spans.json"), "w"), indent=0)
        vis = [s for s in sp if s['size'] >= 1]
        hid = [s for s in sp if s['size'] < 1]
        print(fn, "visible spans", len(vis), "hidden spans", len(hid))
