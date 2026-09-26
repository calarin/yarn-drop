import json, re, math, sys
from callouts import is_dot, seg_of, is_black

CODE_RE = re.compile(r'^[A-Z]{2,4}-\d{3}(\.\d+)?[A-Z]*$')
ROOMNUM_RE = re.compile(r'^\d{3}[A-Z]?$')

def d2(a, b): return math.hypot(a[0]-b[0], a[1]-b[1])

def rect_dist(pt, r):
    x, y = pt; x0, y0, x1, y1 = r
    dx = max(x0 - x, 0, x - x1); dy = max(y0 - y, 0, y - y1)
    return math.hypot(dx, dy)

def on_rect_boundary(pt, r, tol):
    x, y = pt; x0, y0, x1, y1 = r
    inside_exp = (x0 - tol <= x <= x1 + tol) and (y0 - tol <= y <= y1 + tol)
    inside_shr = (x0 + tol < x < x1 - tol) and (y0 + tol < y < y1 - tol)
    return inside_exp and not inside_shr

def lines_in(P, lo, width=None):
    out = []
    for i in range(lo, len(P)):
        pr = P[i]; s = seg_of(pr)
        if s and is_black(pr['color']) and (width is None or abs(pr['width'] - width) < 0.02):
            out.append((i, tuple(s[0]), tuple(s[1])))
    return out

def find_rect_around(bbox, lines, maxgap=(20, 12)):
    bx0, by0, bx1, by1 = bbox
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
    L = R = T = B = None
    for i, a, b in lines:
        if abs(a[0] - b[0]) < 0.2:
            ylo, yhi = min(a[1], b[1]), max(a[1], b[1])
            if ylo - 0.5 <= cy <= yhi + 0.5 and (yhi - ylo) < 30:
                if a[0] < bx0 + 0.5 and bx0 - a[0] < maxgap[0]:
                    if L is None or a[0] > L[0]: L = (a[0], i)
                if a[0] > bx1 - 0.5 and a[0] - bx1 < maxgap[0]:
                    if R is None or a[0] < R[0]: R = (a[0], i)
        elif abs(a[1] - b[1]) < 0.2:
            xlo, xhi = min(a[0], b[0]), max(a[0], b[0])
            if xlo - 0.5 <= cx <= xhi + 0.5 and (xhi - xlo) < 120:
                if a[1] < by0 + 0.5 and by0 - a[1] < maxgap[1]:
                    if T is None or a[1] > T[0]: T = (a[1], i)
                if a[1] > by1 - 0.5 and a[1] - by1 < maxgap[1]:
                    if B is None or a[1] < B[0]: B = (a[1], i)
    if L and R and T and B:
        return (L[0], T[0], R[0], B[0]), sorted({L[1], R[1], T[1], B[1]})
    return None, []

def analyse(fn, prefix):
    P = json.load(open(f"{fn}_prims.json"))
    spans = json.load(open(f"{fn}_spans.json"))
    big_dots = [i for i, pr in enumerate(P) if is_dot(pr)]
    lo = big_dots[0] - 300
    allk = lines_in(P, lo)
    # ---------- code labels ----------
    code_spans = [s for s in spans if 7.5 < s['size'] < 9 and CODE_RE.match(s['text'].strip())]
    typ_spans = [s for s in spans if 7.5 < s['size'] < 9 and s['text'].strip().rstrip('.') == 'TYP']
    labels = []
    for s in code_spans:
        rect, edges = find_rect_around(s['bbox'], allk)
        typ = None; ext = rect or s['bbox']
        for t in typ_spans:
            tx0, ty0, tx1, ty1 = t['bbox']
            if abs((ty0 + ty1) / 2 - (ext[1] + ext[3]) / 2) < 3 and -1 <= tx0 - ext[2] < 14:
                typ = t; break
        extent = list(ext)
        if typ:
            extent[2] = max(extent[2], typ['bbox'][2])
        labels.append(dict(code=s['text'].strip(), text_bbox=s['bbox'], box=rect, box_edges=edges,
                           typ=(typ['text'].strip() if typ else None), typ_bbox=(typ['bbox'] if typ else None),
                           extent=extent))
    edge_set = set(j for l in labels for j in l['box_edges'])
    # ---------- room tags ----------
    room_spans = [s for s in spans if 8.30 < s['size'] < 8.40 and ROOMNUM_RE.match(s['text'].strip())]
    allk_page = lines_in(P, 0)
    k036 = lines_in(P, 0, 0.36)
    rooms = []
    for s in room_spans:
        rect, edges = find_rect_around(s['bbox'], allk_page, maxgap=(14, 6))
        # name lines: 8.34pt text spans directly above within 35pt, horizontally overlapping
        bx0, by0, bx1, by1 = rect or s['bbox']
        cx = (bx0 + bx1) / 2
        names = [t for t in spans if 8.30 < t['size'] < 8.40 and not ROOMNUM_RE.match(t['text'].strip())
                 and t['bbox'][3] <= by0 + 1 and by0 - t['bbox'][3] < 40 and abs((t['bbox'][0] + t['bbox'][2]) / 2 - cx) < 16]
        names.sort(key=lambda t: t['bbox'][1])
        # keep contiguous block ending right above
        block = []
        ybot = by0
        for t in sorted(names, key=lambda t: -t['bbox'][1]):
            if ybot - t['bbox'][3] < 4:
                block.insert(0, t); ybot = t['bbox'][1]
        rooms.append(dict(number=s['text'].strip(), num_bbox=s['bbox'], box=rect, box_edges=edges,
                          name=" ".join(t['text'].strip() for t in block), name_bboxes=[t['bbox'] for t in block]))
    for r in rooms: edge_set.update(r['box_edges'])
    # ---------- dots ----------
    dots = []
    for i, pr in enumerate(P):
        if pr['type'] == 'f' and is_black(pr['fill']) and pr['items'] and all(it[0] == 'c' for it in pr['items']):
            w = pr['rect'][2] - pr['rect'][0]
            if 4.0 < w < 9.5:
                x0, y0, x1, y1 = pr['rect']
                dots.append(dict(idx=i, c=((x0 + x1) / 2, (y0 + y1) / 2), r=w / 2, kind=('big' if w > 5 else 'small')))
    # dedupe dots drawn twice at same spot
    ded = []
    for d in dots:
        if any(d2(d['c'], e['c']) < 0.3 and abs(d['r'] - e['r']) < 0.3 for e in ded): continue
        ded.append(d)
    dots = ded
    # ---------- leader segments ----------
    segs = []
    for i, a, b in lines_in(P, 0, 0.36):
        if i in edge_set: continue
        # skip duplicates lying on label/room boxes
        skip = False
        for L in labels + rooms:
            r = L.get('box')
            if r and on_rect_boundary(a, r, 0.3) and on_rect_boundary(b, r, 0.3) and (abs(a[0]-b[0]) < 0.2 or abs(a[1]-b[1]) < 0.2):
                if (abs(a[0]-b[0]) < 0.2 and min(abs(a[0]-r[0]), abs(a[0]-r[2])) < 0.3) or (abs(a[1]-b[1]) < 0.2 and min(abs(a[1]-r[1]), abs(a[1]-r[3])) < 0.3):
                    skip = True; break
        if not skip: segs.append(dict(idx=i, a=a, b=b))
    return P, spans, labels, rooms, dots, segs

def follow(dot, segs, tol=0.8):
    """Follow leader chain from a dot center to its free end."""
    cur = dot['c']; path = [cur]; used = []; notes = []
    # first segment: an endpoint at the dot center
    while True:
        cands = []
        for j, s in enumerate(segs):
            if j in used: continue
            if d2(s['a'], cur) < (tol if used else max(tol, dot['r'] * 0.5)): cands.append((j, s['b']))
            elif d2(s['b'], cur) < (tol if used else max(tol, dot['r'] * 0.5)): cands.append((j, s['a']))
        if not cands: break
        if len(cands) > 1:
            last = segs[used[-1]]['idx'] if used else dot['idx']
            cands.sort(key=lambda t: abs(segs[t[0]]['idx'] - last))
            notes.append('junction at (%.1f,%.1f) with %d continuations; followed drawing-order neighbour' % (cur[0], cur[1], len(cands)))
        j, nxt = cands[0]
        used.append(j); path.append(nxt); cur = nxt
    return path, used, notes

def run_traces(verbose=False):
    out = {}
    for fn, prefix in (("east", "E"), ("west", "W")):
        P, spans, labels, rooms, dots, segs = analyse(fn, prefix)
        # trace from every dot
        traces = []
        for d in dots:
            path, used, notes = follow(d, segs)
            end = path[-1]
            # which label/room box does the free end touch?
            best = None
            for li, L in enumerate(labels):
                dist = rect_dist(end, L['extent'])
                if dist < 2.0 and (best is None or dist < best[0]): best = (dist, 'label', li)
            if d['kind'] == 'small' and len(path) > 1:
                for ri, R in enumerate(rooms):
                    if R['box']:
                        ext = list(R['box'])
                        for nb in R['name_bboxes']:
                            ext = [min(ext[0], nb[0]), min(ext[1], nb[1]), max(ext[2], nb[2]), max(ext[3], nb[3])]
                        dist = rect_dist(end, ext)
                        if dist < 15.0 and (best is None or best[1] == 'room' and dist < best[0]): best = (dist, 'room', ri)
            traces.append(dict(dot=d, path=path, seg_ids=[segs[j]['idx'] for j in used], notes=notes,
                               target=(best[1], best[2]) if best else None, gap=(best[0] if best else None)))
        # drawing-order association check for label targets
        for t in traces:
            if t['target'] and t['target'][0] == 'label':
                L = labels[t['target'][1]]
                t['order_ok'] = bool(L['box_edges']) and 0 < min(L['box_edges']) - t['dot']['idx'] < 40
        # summaries
        lab_hits = {}
        for ti, t in enumerate(traces):
            if t['target']: lab_hits.setdefault(t['target'], []).append(ti)
        (print if verbose else (lambda *a, **k: None))("=====", fn, "labels", len(labels), "rooms", len(rooms), "dots", len(dots), "segs", len(segs))
        for li, L in enumerate(labels):
            hits = lab_hits.get(('label', li), [])
            if len(hits) != 1:
                (print if verbose else (lambda *a, **k: None))("  LABEL with %d leaders:" % len(hits), L['code'], L['typ'], [round(v, 1) for v in L['text_bbox']])
        for ri, R in enumerate(rooms):
            hits = lab_hits.get(('room', ri), [])
            (print if verbose else (lambda *a, **k: None))("  ROOM %-5s %-35s box=%s leaders=%d %s" % (R['number'], R['name'], [round(v, 1) for v in R['box']] if R['box'] else None, len(hits),
                  [tuple(round(v, 1) for v in traces[h]['dot']['c']) for h in hits]))
        for ti, t in enumerate(traces):
            if not t['target']:
                (print if verbose else (lambda *a, **k: None))("  DOT without label:", t['dot']['kind'], tuple(round(v, 1) for v in t['dot']['c']), 'path', [tuple(round(v, 1) for v in p) for p in t['path']])
            if t['notes']: (print if verbose else (lambda *a, **k: None))("  NOTE", t['notes'])
            if t['target'] and t['target'][0] == 'label' and not t.get('order_ok'):
                (print if verbose else (lambda *a, **k: None))("  ORDER MISMATCH", labels[t['target'][1]]['code'], t['dot']['idx'], labels[t['target'][1]]['box_edges'])
        out[fn] = dict(labels=labels, rooms=rooms, dots=dots, traces=traces)
    json.dump(out, open("traces.json", "w"), indent=0)


if __name__ == "__main__":
    run_traces(verbose=True)
