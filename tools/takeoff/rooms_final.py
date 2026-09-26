import json, numpy as np
from scipy import ndimage as ndi
from skimage.segmentation import watershed
from rooms_viz import segment, assign_seeds
from rooms_seg import Z
from rooms_close import disk

def seed_px(pt):
    return int(round(pt[1] * Z)), int(round(pt[0] * Z))

def final_rooms(fn, r=24, walls=(), radii=(32, 40, 48, 56, 64, 72, 80)):
    a, bar, lab = segment(fn, r=r, extra_walls=walls)
    base_bar = bar
    rooms, seeds, comp, seed_lab = assign_seeds(fn, lab)
    nums = [R['number'] for R in rooms]
    idx = {n: i + 1 for i, n in enumerate(nums)}
    out = np.zeros(lab.shape, np.int32)
    method = {}
    # un-closed barrier for escalation
    a0 = a
    raw = ndi.binary_dilation((a0 == 212) | (a0 == 170), iterations=1)
    for l, members in comp.items():
        if l == 0:
            for n in members: method[n] = 'seed on barrier (no region)'
            continue
        if l == 1:
            for n in members: method[n] = 'seed in exterior/background region (no enclosed room found)'
            continue
        m = lab == l
        if len(members) == 1:
            out[m] = idx[members[0]]
            method[members[0]] = 'enclosed by walls/doors after closing gaps < %d px (%.0f pt)' % (2 * r, 2 * r / Z)
            continue
        ys, xs = np.nonzero(m)
        pad = 100
        y0, y1 = max(ys.min() - pad, 0), min(ys.max() + 1 + pad, lab.shape[0])
        x0, x1 = max(xs.min() - pad, 0), min(xs.max() + 1 + pad, lab.shape[1])
        subm = m[y0:y1, x0:x1]
        # rebuild the local barrier including match line/extra walls from base (unclosed)
        loc_raw = base_bar[y0:y1, x0:x1] if False else None
        cores = {}
        core_r = {}
        pending = set(members)
        for rr in radii:
            if not pending: break
            # local closing of the same raw barrier plus extra walls used in segment()
            a_loc, bar_loc, lab_loc = None, None, None
            b = ndi.binary_closing(raw[y0:y1, x0:x1] | ~subm, structure=disk(rr))
            ll, nn = ndi.label(~b)
            where = {}
            for n in members:
                yy, xx = seed_px(seeds[n][0]); yy -= y0; xx -= x0
                v = ll[yy, xx] if (0 <= yy < ll.shape[0] and 0 <= xx < ll.shape[1]) else 0
                where.setdefault(int(v), []).append(n)
            for v, ns in where.items():
                if v == 0: continue
                if len(ns) == 1 and ns[0] in pending:
                    cores[ns[0]] = (ll == v) & subm
                    core_r[ns[0]] = rr
                    pending.discard(ns[0])
        markers = np.zeros(subm.shape, np.int32)
        for n in members:
            if n in cores:
                markers[cores[n]] = idx[n]
        for n in pending:
            yy, xx = seed_px(seeds[n][0]); yy -= y0; xx -= x0
            Y, X = np.ogrid[:subm.shape[0], :subm.shape[1]]
            markers[((Y - yy) ** 2 + (X - xx) ** 2 <= 64) & subm] = idx[n]
        ws = watershed(np.zeros(subm.shape, np.uint8), markers, mask=subm)
        reg = out[y0:y1, x0:x1]
        reg[subm] = ws[subm]
        for n in members:
            if n in cores:
                method[n] = 'open to %s; core isolated by closing gaps < %d px (%.0f pt), extended to opening by geodesic split' % (
                    ",".join(x for x in members if x != n), 2 * core_r[n], 2 * core_r[n] / Z)
            else:
                method[n] = 'open to %s; no isolating closing radius found - geodesic split from tag point (LOW CONFIDENCE)' % ",".join(x for x in members if x != n)
    return a, out, rooms, seeds, method

if __name__ == "__main__":
    for fn in ("east", "west"):
        a, out, rooms, seeds, method = final_rooms(fn)
        np.save(f"{fn}_rooms.npy", out)
        json.dump(method, open(f"{fn}_room_method.json", "w"), indent=1)
        for i, R in enumerate(rooms):
            n = R['number']
            area = int((out == i + 1).sum())
            if 'open' in method.get(n, '') or 'seed' in method.get(n, ''):
                print(fn, n, R['name'], area, method.get(n))
