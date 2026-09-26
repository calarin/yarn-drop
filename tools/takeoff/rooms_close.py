import json, numpy as np, sys
from scipy import ndimage as ndi
from rooms_seg import seeds_for, Z

def disk(r):
    y, x = np.ogrid[-r:r+1, -r:r+1]
    return x*x + y*y <= r*r

def run(fn, r, verbose=True):
    a = np.load(f"{fn}_gray_z3.npy")
    bar = (a == 212) | (a == 170)
    bar = ndi.binary_dilation(bar, iterations=1)
    if r > 0:
        barc = ndi.binary_closing(bar, structure=disk(r))
    else:
        barc = bar
    free = ~barc
    lab, n = ndi.label(free)
    rooms, seeds = seeds_for(fn)
    comp = {}
    for num, (pt, how) in seeds.items():
        x, y = int(round(pt[0]*Z)), int(round(pt[1]*Z))
        l = lab[y, x]
        if l == 0:
            win = 30
            sub = lab[max(0,y-win):y+win+1, max(0,x-win):x+win+1]
            ys, xs = np.nonzero(sub)
            if len(ys):
                k = np.argmin((ys-win)**2 + (xs-win)**2)
                l = sub[ys[k], xs[k]]
        comp.setdefault(int(l), []).append(num)
    merged = {l: v for l, v in comp.items() if len(v) > 1 or l == 0}
    if verbose:
        print(fn, "r=%d" % r, "merged groups:", merged)
    return lab, comp, barc

if __name__ == "__main__":
    for fn in ("east", "west"):
        for r in (8, 16, 24, 32, 40, 48):
            run(fn, r)
