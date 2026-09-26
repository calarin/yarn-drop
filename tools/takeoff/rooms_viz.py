import json, numpy as np, colorsys, sys
from scipy import ndimage as ndi
from PIL import Image, ImageDraw, ImageFont
from rooms_seg import seeds_for, Z
from rooms_close import disk

MATCH_X = {"east": 150.5, "west": 1576.4}

def segment(fn, r=24, extra_walls=(), match=True):
    a = np.load(f"{fn}_gray_z3.npy")
    bar = (a == 212) | (a == 170)
    bar = ndi.binary_dilation(bar, iterations=1)
    im = Image.fromarray((bar * 255).astype(np.uint8))
    dr = ImageDraw.Draw(im)
    if match:
        x = MATCH_X[fn] * Z
        dr.line([(x, 0), (x, a.shape[0])], fill=255, width=3)
    for (x0, y0, x1, y1) in extra_walls:
        dr.line([(x0*Z, y0*Z), (x1*Z, y1*Z)], fill=255, width=4)
    bar = np.array(im) > 0
    if r > 0:
        bar = ndi.binary_closing(bar, structure=disk(r))
    lab, n = ndi.label(~bar)
    return a, bar, lab

def assign_seeds(fn, lab):
    rooms, seeds = seeds_for(fn)
    comp = {}
    seed_lab = {}
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
        seed_lab[num] = int(l)
    return rooms, seeds, comp, seed_lab

def viz(fn, a, lab, comp, seeds, out, crop=None, scale=0.5):
    h, w = a.shape
    rgb = np.stack([a, a, a], axis=-1).astype(np.float32)
    rng = np.random.default_rng(1)
    overlay = np.zeros_like(rgb)
    mask = np.zeros(a.shape, bool)
    for l, nums in comp.items():
        if l in (0, 1): continue
        hue = rng.random()
        col = np.array(colorsys.hsv_to_rgb(hue, 0.55 if len(nums) == 1 else 1.0, 1.0)) * 255
        m = lab == l
        overlay[m] = col
        mask |= m
    rgb[mask] = rgb[mask] * 0.45 + overlay[mask] * 0.55
    img = Image.fromarray(rgb.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
    except Exception:
        font = ImageFont.load_default()
    for num, (pt, how) in seeds.items():
        x, y = pt[0]*Z, pt[1]*Z
        d.ellipse([x-10, y-10, x+10, y+10], fill=(255, 0, 0))
        d.text((x+12, y-20), num, fill=(200, 0, 0), font=font)
    if crop:
        img = img.crop(tuple(int(v*Z) for v in crop))
    img = img.resize((int(img.width*scale), int(img.height*scale)))
    img.save(out)

if __name__ == "__main__":
    for fn, crop in (("east", (95, 330, 1420, 900)), ("west", (850, 320, 1600, 950))):
        a, bar, lab = segment(fn, r=24)
        rooms, seeds, comp, seed_lab = assign_seeds(fn, lab)
        print(fn, {l: v for l, v in comp.items() if len(v) > 1 or l in (0, 1)})
        viz(fn, a, lab, comp, seeds, f"seg_{fn}.png", crop=crop, scale=0.4)
