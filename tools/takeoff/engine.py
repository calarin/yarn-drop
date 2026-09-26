"""Plan takeoff engine: pieces, callout targets, room assignment, instance matching."""
import json, math, re
import numpy as np
from collections import defaultdict, Counter
from callouts import seg_of, is_black

Z = 3
OWN = {'east': lambda x: x > 150.5, 'west': lambda x: x < 1576.4}
MATCH_X = {'east': 150.5, 'west': 1576.4}
# west -> east display coordinates (match line x and grid line B.1 y)
def w2e(pt): return (pt[0] - 1425.9, pt[1] + 12.7)
def e2w(pt): return (pt[0] + 1425.9, pt[1] - 12.7)

def rect_contains(r, p, tol=0.0):
    return r[0] - tol <= p[0] <= r[2] + tol and r[1] - tol <= p[1] <= r[3] + tol

def rect_dist(r, p):
    dx = max(r[0] - p[0], 0, p[0] - r[2]); dy = max(r[1] - p[1], 0, p[1] - r[3])
    return math.hypot(dx, dy)

def inset_dist(r, p):
    """distance from p to the nearest edge of r when inside (0 when outside)"""
    if not rect_contains(r, p): return 0.0
    return min(p[0] - r[0], r[2] - p[0], p[1] - r[1], r[3] - p[1])

class Sheet:
    def __init__(self, fn):
        self.fn = fn
        self.P = json.load(open(f"{fn}_prims.json"))
        self.tags = json.load(open(f"{fn}_tags.json"))
        T = json.load(open("traces.json"))[fn]
        self.labels, self.rooms_meta, self.dots, self.traces = T['labels'], T['rooms'], T['dots'], T['traces']
        self.R = np.load(f"{fn}_rooms.npy")
        self.gray = np.load(f"{fn}_gray_z3.npy")
        self.room_method = json.load(open(f"{fn}_room_method.json"))
        self.annot_lo = min(t['dot']['idx'] for t in self.traces if t['dot']['kind'] == 'big') - 300
        self.room_numbers = [r['number'] for r in self.rooms_meta]
        self._split = None
        from shapely import wkt as _wkt
        seq2idx = {pr['seqno']: i for i, pr in enumerate(self.P)}
        self.masks = []
        for m in json.load(open(f"{fn}_masks.json")):
            i = seq2idx.get(m['seqno'])
            if i is None or i >= self.annot_lo: continue
            poly = _wkt.loads(m['wkt'])
            if poly.is_empty or poly.area < 0.5: continue
            b = poly.bounds
            self.masks.append(dict(idx=i, rect=[b[0], b[1], b[2], b[3]], poly=poly, area=poly.area))
        self.panes = []
        for i, pr in enumerate(self.P):
            if pr['type'] == 'f' and pr['fill'] and abs(pr['fill'][0] - 0.83) < 0.01 and [it[0] for it in pr['items']] == ['re']:
                x0, y0, x1, y1 = pr['rect']; w, h = x1 - x0, y1 - y0
                if min(w, h) < 1.6 and max(w, h) > 15:
                    self.panes.append(dict(idx=i, rect=pr['rect'], orient='H' if w > h else 'V'))

    # ---------------- rooms ----------------
    def split_dist(self, pt):
        if self._split is None:
            from scipy import ndimage as ndi
            R = self.R
            mx = ndi.maximum_filter(R, size=3); mn = ndi.minimum_filter(np.where(R == 0, 10 ** 6, R), size=3)
            contact = (R > 0) & (mx != mn) & (mn < 10 ** 6)
            self._split = ndi.distance_transform_edt(~contact) / Z
        x, y = int(round(pt[0] * Z)), int(round(pt[1] * Z))
        if 0 <= y < self._split.shape[0] and 0 <= x < self._split.shape[1]:
            return float(self._split[y, x])
        return 1e9
    def room_at(self, pt):
        x, y = int(round(pt[0] * Z)), int(round(pt[1] * Z))
        if 0 <= y < self.R.shape[0] and 0 <= x < self.R.shape[1]:
            k = int(self.R[y, x])
            if k: return self.room_numbers[k - 1]
        return None

    def room_probe(self, pt, radii=(1.5, 3, 4.5, 6, 8, 10, 12, 15), nang=24):
        """rooms found around a point (used when the point lies on a wall/window)."""
        found = Counter()
        for r in radii:
            for k in range(nang):
                a = 2 * math.pi * k / nang
                rm = self.room_at((pt[0] + r * math.cos(a), pt[1] + r * math.sin(a)))
                if rm: found[rm] += 1
            if found: return found, r
        return found, None

    def room_for_point(self, pt):
        rm = self.room_at(pt)
        if rm: return rm, 'point inside room region', []
        found, r = self.room_probe(pt)
        if not found: return None, 'no room region within 15 pt', []
        if len(found) == 1:
            return list(found)[0], 'point on wall/barrier; single adjacent room within %.1f pt' % r, []
        ranked = found.most_common()
        return ranked[0][0], 'point on wall/barrier; adjacent rooms %s within %.1f pt' % (dict(found), r), [k for k, _ in ranked]

    def room_for_poly(self, poly, offset=2.0, n=36):
        ring = poly.buffer(offset).exterior if poly.buffer(offset).geom_type == 'Polygon' else poly.buffer(offset).convex_hull.exterior
        votes = Counter()
        for k in range(n):
            q = ring.interpolate(k / n, normalized=True)
            rm = self.room_at((q.x, q.y))
            if rm: votes[rm] += 1
        if not votes: return None, votes
        return votes.most_common(1)[0][0], votes

    def room_for_rect(self, r):
        pts = [((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)]
        ins = 1.0
        if r[2] - r[0] > 2 * ins and r[3] - r[1] > 2 * ins:
            pts += [(r[0] + ins, r[1] + ins), (r[2] - ins, r[1] + ins), (r[0] + ins, r[3] - ins), (r[2] - ins, r[3] - ins)]
        rooms = Counter(self.room_at(p) for p in pts)
        return rooms

    # ---------------- pieces ----------------
    def smallest_mask(self, pt, tol=0.3):
        from shapely.geometry import Point
        P_ = Point(pt)
        c = [m for m in self.masks if rect_contains(m['rect'], pt, tol) and m['poly'].distance(P_) <= tol]
        c.sort(key=lambda m: m['area'])
        return c

    def build_instances(self):
        inst = []
        for k, t in enumerate(self.tags):
            ms = self.smallest_mask(t['c'])
            mask = ms[0] if ms else None
            angle = t['angle']
            rot = min(abs(((angle + 360) % 90)), 90 - abs(((angle + 360) % 90)))
            fp = mask['rect'] if mask else None
            rm, how, alts = self.room_for_point(t['c'])
            straddle = None
            if fp:
                rr = self.room_for_rect(fp)
                rs = [x for x in rr if x]
                if len(set(rs)) > 1: straddle = sorted(set(rs))
            owned = OWN[self.fn](t['c'][0])
            family = 'architect' if '-' in t['tag'] or t['tag'] in ('F', 'L') else 'dealer-component'
            inst.append(dict(sheet=self.fn, tag=t['tag'], joined=t['joined'], source_text=t['source_text'], c=t['c'], angle=angle,
                             rotated=rot > 3, mask=fp, mask_idx=(mask['idx'] if mask else None), mask_poly=(mask['poly'] if mask else None),
                             mask_area=(mask['area'] if mask else None), room=rm, room_how=how,
                             room_alts=alts, straddle=straddle, owned=owned, family=family))
        return inst

def size_key(i):
    if not i['mask']: return None
    w = i['mask'][2] - i['mask'][0]; h = i['mask'][3] - i['mask'][1]
    return max(w, h)

def compatible(a, b, tol=0.15):
    """same tag assumed; compare longest mask side unless either is rotated or unmasked."""
    if a['rotated'] or b['rotated']: return True, 'rotated instance: size not compared'
    sa, sb = size_key(a), size_key(b)
    if sa is None or sb is None: return True, 'no mask: size not compared'
    if abs(sa - sb) <= max(1.0, tol * max(sa, sb)): return True, 'size match'
    return False, 'size differs (%.1f vs %.1f pt)' % (sa, sb)

# ---------------- callouts ----------------
def callouts(S):
    out = []
    n = 0
    order = sorted([t for t in S.traces if t['target'] and t['target'][0] == 'label'],
                   key=lambda t: (S.labels[t['target'][1]]['extent'][1], S.labels[t['target'][1]]['extent'][0]))
    for t in order:
        L = S.labels[t['target'][1]]
        n += 1
        out.append(dict(id='%s-C%02d' % (S.fn[0].upper(), n), sheet=S.fn, code=L['code'], typ=L['typ'],
                        label_rect=L['box'], extent=L['extent'], text_bbox=L['text_bbox'],
                        path=t['path'], endpoint=t['dot']['c'], dot_idx=t['dot']['idx'], seg_ids=t['seg_ids'],
                        trace_notes=t['notes'], order_ok=t.get('order_ok')))
    return out

def is_arch(tag):
    return ('-' in tag) or tag in ('F', 'L')

def resolve_target(S, inst, co, pieces, tag_piece):
    """Identify the tagged symbol at a leader endpoint.
    pieces: grouped mask pieces; tag_piece: instance index -> piece id."""
    from shapely.geometry import Point
    e = co['endpoint']; E = Point(e)
    res = dict(kind=None, inst=[], notes=[], ambiguous=False, candidates=[], method=None)
    piece_tags = defaultdict(list)
    for k, pid in tag_piece.items():
        if inst[k]['owned']: piece_tags[pid].append(k)
    rows = []
    for g in pieces:
        d = g['poly'].distance(E)
        if d < 2.0:
            inside = g['poly'].contains(E)
            edge = g['poly'].boundary.distance(E)
            rows.append(dict(pid=g['id'], d=(0.0 if inside else d), inside=inside, edge=edge, area=g['area'], ks=piece_tags.get(g['id'], [])))
    def pick(ks):
        arch = [k for k in ks if is_arch(inst[k]['tag'])]
        pool = sorted(arch or ks, key=lambda k: math.hypot(inst[k]['c'][0] - e[0], inst[k]['c'][1] - e[1]))
        return pool[0] if pool else None
    tagged = [r for r in rows if r['ks']]
    ins = sorted([r for r in tagged if r['inside']], key=lambda r: r['area'])
    if ins:
        b = ins[0]; k0 = pick(b['ks'])
        res.update(kind='tagged-piece', inst=[k0], method='endpoint inside mask of tagged piece', dist=0.0)
        res['notes'].append('inside %s piece outline (%.1f pt from edge)' % (inst[k0]['tag'], b['edge']))
        others = sorted(set(inst[k]['tag'] for k in b['ks'] if is_arch(inst[k]['tag'])) - {inst[k0]['tag']})
        if others: res['notes'].append('same mask also carries %s; nearest tag used' % others)
        if b['edge'] < 0.6:
            alt = [r for r in tagged if r['pid'] != b['pid'] and (r['edge'] < 0.6 or r['d'] < 0.6)
                   and not (r['inside'] and r['area'] > 1.5 * b['area'])]
            at = sorted(set(inst[pick(r['ks'])]['tag'] for r in alt) - {inst[k0]['tag']})
            if at:
                res['ambiguous'] = True; res['candidates'] = [k0] + [pick(r['ks']) for r in alt]
                res['notes'].append('endpoint on shared edge with %s piece' % at)
        return res
    near = sorted(tagged, key=lambda r: r['d'])
    if near:
        b = near[0]; k0 = pick(b['ks'])
        res.update(kind='tagged-piece', inst=[k0], method='endpoint on/near outline of tagged piece', dist=b['d'])
        nxt = [r for r in near[1:] if not set(inst[k]['tag'] for k in r['ks']) <= {inst[k0]['tag']}]
        res['next_other'] = nxt[0]['d'] if nxt else None
        res['notes'].append('%.1f pt from %s piece mask' % (b['d'], inst[k0]['tag']))
        alt = [r for r in near[1:] if r['d'] - b['d'] < 0.6]
        at = sorted(set(inst[pick(r['ks'])]['tag'] for r in alt) - {inst[k0]['tag']})
        if at:
            res['ambiguous'] = True; res['candidates'] = [k0] + [pick(r['ks']) for r in alt]
            res['notes'].append('equally close to %s piece' % at)
        return res
    # fallback: nearest owned architect tag within 10 pt, ratio test
    cand = sorted((math.hypot(i['c'][0] - e[0], i['c'][1] - e[1]), k) for k, i in enumerate(inst) if i['owned'] and is_arch(i['tag']))
    cand = [(d, k) for d, k in cand if d < 12]
    if cand:
        d0, k0 = cand[0]
        diff = [(d, k) for d, k in cand[1:] if inst[k]['tag'] != inst[k0]['tag']]
        if not diff or diff[0][0] > 1.5 * d0:
            res.update(kind='tagged-piece', inst=[k0], method='nearest in-symbol tag (piece has no usable mask)', dist=d0)
            res['notes'].append('no tagged mask at endpoint; nearest in-symbol tag %s at %.1f pt' % (inst[k0]['tag'], d0))
            if diff: res['notes'].append('next different tag %s at %.1f pt' % (inst[diff[0][1]]['tag'], diff[0][0]))
            return res
        res.update(kind='tagged-piece', inst=[k0], method='nearest in-symbol tag (ambiguous)', ambiguous=True,
                   candidates=[k0, diff[0][1]])
        res['notes'].append('nearest tags %s (%.1f pt) and %s (%.1f pt) similarly close' % (inst[k0]['tag'], d0, inst[diff[0][1]]['tag'], diff[0][0]))
        return res
    res['kind'] = 'untagged'
    return res
