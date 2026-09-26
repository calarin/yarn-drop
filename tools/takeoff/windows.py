"""Glazing panes (window bays) and the room on their interior side."""
import math
from collections import Counter

def pane_room(S, pane, depth=(3, 5, 8, 12, 16, 20)):
    x0, y0, x1, y1 = pane['rect']
    res = {}
    for frac in (0.2, 0.5, 0.8):
        if pane['orient'] == 'H':
            px, py = x0 + frac * (x1 - x0), (y0 + y1) / 2
            dirs = [(0, 1), (0, -1)]
        else:
            px, py = (x0 + x1) / 2, y0 + frac * (y1 - y0)
            dirs = [(1, 0), (-1, 0)]
        for dx, dy in dirs:
            for dd in depth:
                rm = S.room_at((px + dx * dd, py + dy * dd))
                if rm:
                    res.setdefault((dx, dy), Counter())[rm] += 1
                    break
    # interior side = side where rooms were found
    sides = {k: v for k, v in res.items() if v}
    rooms = Counter()
    for v in sides.values(): rooms.update(v)
    if not rooms: return None, 'no room found on either side', rooms
    if len(rooms) == 1: return list(rooms)[0], 'single room on interior side', rooms
    return rooms.most_common(1)[0][0], 'pane spans/adjoins several rooms %s' % dict(rooms), rooms

def window_bays(S):
    out = []
    for k, p in enumerate(S.panes):
        c = ((p['rect'][0] + p['rect'][2]) / 2, (p['rect'][1] + p['rect'][3]) / 2)
        rm, how, rooms = pane_room(S, p)
        L = max(p['rect'][2] - p['rect'][0], p['rect'][3] - p['rect'][1])
        out.append(dict(k=k, rect=p['rect'], c=c, length=L, orient=p['orient'], room=rm, room_how=how, rooms=dict(rooms),
                        owned=S_owned(S, c)))
    return out

def S_owned(S, c):
    from engine import OWN
    return OWN[S.fn](c[0])

def pane_at(S, bays, pt, tol=2.0):
    best = None
    for b in bays:
        r = b['rect']
        dx = max(r[0] - pt[0], 0, pt[0] - r[2]); dy = max(r[1] - pt[1], 0, pt[1] - r[3])
        d = math.hypot(dx, dy)
        if best is None or d < best[0]: best = (d, b)
    if best and best[0] <= tol: return best[1], best[0]
    return (best[1], best[0]) if best else (None, None)

if __name__ == "__main__":
    from engine import Sheet
    for fn in ("east", "west"):
        S = Sheet(fn)
        B = window_bays(S)
        c = Counter((b['room'] if b['owned'] else 'other-sheet') for b in B)
        print(fn, len(B), sorted(c.items(), key=lambda kv: str(kv[0])))
        for b in B:
            if 'several' in b['room_how'] or b['room'] is None:
                print("   ", [round(v, 1) for v in b['rect']], b['room_how'])
