"""Count outlined sections in filing/shelving banks (component detail for HDF-900)."""
import numpy as np, json
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

def bank_sections(S, pt, G, max_extent=160):
    """Sections = cells enclosed by black 0.96 outlines within the connected bank around pt."""
    from shapely.geometry import Point
    # bank region: untagged/tagged pieces containing or touching pt, grown through touching pieces with hexagon hatch
    P0 = Point(pt)
    start = [g for g in G if g['poly'].distance(P0) < 1.0]
    if not start: return None
    region = start[0]['poly']
    changed = True
    while changed:
        changed = False
        for g in G:
            if g['poly'].distance(region) < 0.8 and not g['poly'].within(region):
                b = g['poly'].bounds
                if b[2] - b[0] < max_extent * 2 and b[3] - b[1] < max_extent * 2:
                    u = region.union(g['poly'])
                    if u.area > region.area + 1:
                        region = u; changed = True
    x0, y0, x1, y1 = region.bounds
    Zl = 4
    W, H = int((x1 - x0) * Zl) + 8, int((y1 - y0) * Zl) + 8
    im = Image.new("L", (W, H), 0); d = ImageDraw.Draw(im)
    for pr in S.P:
        if pr['type'] == 's' and pr['color'] and max(pr['color']) < 0.05 and abs(pr['width'] - 0.96) < 0.02:
            r = pr['rect']
            if r[2] < x0 - 1 or r[0] > x1 + 1 or r[3] < y0 - 1 or r[1] > y1 + 1: continue
            for it in pr['items']:
                if it[0] == 'l':
                    d.line([((it[1][0] - x0) * Zl + 4, (it[1][1] - y0) * Zl + 4), ((it[2][0] - x0) * Zl + 4, (it[2][1] - y0) * Zl + 4)], fill=255, width=3)
    a = np.array(im) > 0
    lab, n = ndi.label(~a)
    sizes = ndi.sum(np.ones_like(lab), lab, index=range(1, n + 1)) / (Zl * Zl)
    cells = [k + 1 for k, s_ in enumerate(sizes) if 120 < s_ < 2500]
    # drop the outside region (touches border)
    border = set(np.unique(np.concatenate([lab[0, :], lab[-1, :], lab[:, 0], lab[:, -1]])))
    cells = [c for c in cells if c not in border]
    return dict(bbox=[x0, y0, x1, y1], sections=len(cells))

if __name__ == "__main__":
    from takeoff import run
    for fn in ("east", "west"):
        S, inst, C, G, bays, bars, res = run(fn)
        for r in res:
            if r['target_kind'] == 'hdf-system':
                b = bank_sections(S, r['callout']['endpoint'], G)
                print(fn, r['callout']['id'], r['room'], b)
