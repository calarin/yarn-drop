"""Room x code takeoff from traced callouts, tagged instances, window bays and wall accessories."""
import json, math
from collections import defaultdict, Counter
from engine import Sheet, callouts, resolve_target, compatible, is_arch, OWN, w2e, e2w, rect_dist
from pieces import build_pieces
from windows import window_bays, pane_at

def side_room(S, rect):
    """Room on the open face of a thin wall-mounted symbol: the face that clears the wall poche first."""
    from engine import Z
    x0, y0, x1, y1 = rect
    horiz = (x1 - x0) > (y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    def px(sgn, d, f):
        return ((cx + f * (x1 - x0), cy + sgn * d) if horiz else (cx + sgn * d, cy + f * (y1 - y0)))
    clear = {}
    for sgn in (1, -1):
        for d in [0.25 * k for k in range(2, 40)]:
            vals = []
            for f in (-0.4, -0.2, 0.2, 0.4):
                x, y = px(sgn, d, f)
                vals.append(int(S.gray[int(round(y * Z)), int(round(x * Z))]))
            if sum(1 for v in vals if v == 255) >= 2:
                clear[sgn] = d; break
    if not clear: return None, 'no open face found next to symbol', []
    order = sorted(clear.items(), key=lambda kv: kv[1])
    sgn, dclear = order[0]
    ambiguous = len(order) > 1 and abs(order[0][1] - order[1][1]) < 0.6
    # walk into the room on the open face, skipping fixtures, until a room region is met
    room = None
    for d in [dclear + 0.5 * k for k in range(0, 80)]:
        votes = Counter()
        for f in (-0.4, -0.2, 0, 0.2, 0.4):
            rm = S.room_at(px(sgn, d, f))
            if rm: votes[rm] += 1
        if votes:
            room = votes.most_common(1)[0][0]; break
    how = 'drawn on wall face; open side %s clears wall at %.1f pt; first room region on that side' % (
        {1: '+y' if horiz else '+x', -1: '-y' if horiz else '-x'}[sgn], dclear)
    alts = []
    if ambiguous:
        how += '; BOTH faces open at similar distance (side uncertain)'
        alts = [room]
    return room, how, alts

def wall_bars(S):
    bars = []
    for m in S.masks:
        x0, y0, x1, y1 = m['rect']; w, h = x1 - x0, y1 - y0
        if min(w, h) < 0.8 and 4 < max(w, h) < 80:
            nblk = 0
            for pr in S.P:
                if pr['type'] == 's' and pr['color'] and max(pr['color']) < 0.05 and abs(pr['width'] - 0.96) < 0.02:
                    r = pr['rect']
                    if r[0] <= x1 + 0.5 and r[2] >= x0 - 0.5 and r[1] <= y1 + 0.5 and r[3] >= y0 - 0.5: nblk += 1
            if nblk >= 3:
                rm, how, alts = side_room(S, m['rect'])
                bars.append(dict(mask_idx=m['idx'], rect=m['rect'], length=max(w, h), room=rm, room_how=how, alts=alts,
                                 c=((x0 + x1) / 2, (y0 + y1) / 2), owned=OWN[S.fn]((x0 + x1) / 2)))
    return bars

def run(fn):
    S = Sheet(fn)
    inst = S.build_instances()
    C = callouts(S)
    G, TM = build_pieces(S)
    mask2piece = {mi: g['id'] for g in G for mi in g['masks']}
    tag_piece = {k: mask2piece[TM[k]] for k in TM}
    for k, i in enumerate(inst):
        i['id'] = '%s-T%03d' % (fn[0].upper(), k + 1)
        i['piece'] = tag_piece.get(k)
    bays = window_bays(S)
    for b in bays: b['id'] = '%s-W%02d' % (fn[0].upper(), b['k'] + 1)
    bars = wall_bars(S)
    for n, b in enumerate(bars): b['id'] = '%s-A%02d' % (fn[0].upper(), n + 1)
    f1 = [k for k, i in enumerate(inst) if i['tag'] == 'F-1' and i['owned']]
    results = []
    for co in C:
        e = co['endpoint']
        r = dict(callout=co, sheet=fn)
        fam = co['code'].split('-')[0]
        r['endpoint_owned'] = OWN[fn](e[0])
        if not r['endpoint_owned']:
            r.update(target_kind='other-sheet', status='DUPLICATE/OTHER SHEET',
                     notes=['leader endpoint lies beyond the match line (x=%.1f); symbol belongs to the other sheet' % ({'east': 150.5, 'west': 1576.4}[fn])])
            results.append(r); continue
        if fam == 'WTR':
            b, d = pane_at(S, bays, e)
            if b is not None and d > 2.5:
                r0 = b['rect']
                along_ok = (r0[0] - 1 <= e[0] <= r0[2] + 1) if b['orient'] == 'H' else (r0[1] - 1 <= e[1] <= r0[3] + 1)
                if along_ok and d <= 6.0:
                    d = d  # accepted: endpoint on inner facade line opposite this pane
                else:
                    b = None
            if b is None:
                r.update(target_kind='window', status='UNRESOLVED', notes=['no glazing pane within 2.5 pt of endpoint'])
            else:
                r.update(target_kind='window-bay', target=b['id'], room=b['room'], room_how='interior side of glazing pane (' + b['room_how'] + ')',
                         notes=['leader ends on exterior glazing (%.1f pt from pane %s)' % (d, b['id'])])
            results.append(r); continue
        if fam == 'RR':
            best = sorted((rect_dist(b['rect'], e), n) for n, b in enumerate(bars))
            if best and best[0][0] < 2.0:
                b = bars[best[0][1]]
                r.update(target_kind='wall-accessory', target=b['id'], room=b['room'], room_how=b['room_how'],
                         notes=['leader ends on wall-mounted bar symbol %s (%.1f pt long, heavy outline)' % (b['id'], b['length'])])
            else:
                r.update(target_kind='wall-accessory', status='UNRESOLVED', notes=['no wall-mounted symbol within 2 pt'])
            results.append(r); continue
        t = resolve_target(S, inst, co, G, tag_piece)
        if t['kind'] == 'untagged' and fam == 'HDF':
            rm, how, alts = S.room_for_point(e)
            sysk = [k for k in f1 if inst[k]['room'] == rm]
            r.update(target_kind='hdf-system', room=rm, room_how=how, system_tags=[inst[k]['id'] for k in sysk],
                     notes=['leader ends on a hexagon-pattern section of a filing/shelving bank'])
            results.append(r); continue
        if t['kind'] == 'untagged':
            r.update(target_kind='untagged', status='UNRESOLVED', notes=['no tagged symbol at endpoint'])
            results.append(r); continue
        k0 = t['inst'][0]
        r.update(target_kind='tagged-piece', target=inst[k0]['id'], target_tag=inst[k0]['tag'], target_k=k0,
                 room=inst[k0]['room'], room_how='room of target symbol tag (' + inst[k0]['room_how'] + ')',
                 method=t['method'], notes=t['notes'], ambiguous=t['ambiguous'],
                 candidates=[inst[k]['id'] + ':' + inst[k]['tag'] for k in t['candidates']])
        er = S.room_at(e)
        if er and er != inst[k0]['room']:
            r['notes'] = r['notes'] + ['endpoint pixel lies in %s but target tag lies in %s' % (er, inst[k0]['room'])]
            r['room_conflict'] = True
        results.append(r)
    return S, inst, C, G, bays, bars, results

if __name__ == "__main__":
    for fn in ("east", "west"):
        S, inst, C, G, bays, bars, res = run(fn)
        print("=====", fn)
        for r in res:
            co = r['callout']
            print("%s %-10s %-4s %-15s room=%-5s tgt=%-9s %-7s %s" % (co['id'], co['code'], co['typ'] or '', r['target_kind'], r.get('room'),
                  r.get('target_tag', r.get('target', '')), 'AMB' if r.get('ambiguous') else (r.get('status') or ''), ' | '.join(r.get('notes', []))[:150]))
        print("bars:", [(b['id'], round(b['length'], 1), b['room'], b['room_how']) for b in bars])
