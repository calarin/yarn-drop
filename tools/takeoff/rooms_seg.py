import json, numpy as np
from scipy import ndimage as ndi
from PIL import Image, ImageDraw, ImageFont

Z = 3
def seeds_for(fn):
    T = json.load(open("traces.json"))[fn]
    rooms = T['rooms']
    seeds = {}
    lead = {}
    for t in T['traces']:
        if t['target'] and t['target'][0] == 'room':
            lead[t['target'][1]] = t['dot']['c']
    for ri, R in enumerate(rooms):
        if ri in lead:
            seeds[R['number']] = (lead[ri], 'tag leader endpoint')
        else:
            b = R['box'] or R['num_bbox']
            seeds[R['number']] = (((b[0]+b[2])/2, (b[1]+b[3])/2), 'tag centre (no leader)')
    return rooms, seeds

def barrier(fn, dil=1):
    a = np.load(f"{fn}_gray_z3.npy")
    bar = (a == 212) | (a == 170)
    if dil: bar = ndi.binary_dilation(bar, iterations=dil)
    return a, bar

if __name__ == "__main__":
    import sys
    for fn in ("east", "west"):
        a, bar = barrier(fn, dil=1)
        free = ~bar
        lab, n = ndi.label(free)
        rooms, seeds = seeds_for(fn)
        comp = {}
        for num, (pt, how) in seeds.items():
            x, y = int(round(pt[0]*Z)), int(round(pt[1]*Z))
            l = lab[y, x]
            if l == 0:
                # nudge to nearest free pixel
                ys, xs = np.nonzero(lab[max(0,y-15):y+16, max(0,x-15):x+16])
                if len(ys):
                    k = np.argmin((ys-15)**2 + (xs-15)**2)
                    l = lab[max(0,y-15)+ys[k], max(0,x-15)+xs[k]]
            comp.setdefault(l, []).append(num)
        sizes = ndi.sum(np.ones_like(lab), lab, index=list(comp.keys()))
        print("=====", fn, "components", n)
        for (l, nums), s in zip(comp.items(), sizes):
            print("  comp %6d area_px=%9d  rooms=%s" % (l, s, nums))
        np.save(f"{fn}_lab.npy", lab)
        json.dump({str(k): v for k, v in comp.items()}, open(f"{fn}_comp.json", "w"))
