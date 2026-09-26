"""Review overlays: room boundaries, traced leaders + endpoints, numbered counted symbols, exceptions."""
import json, math, colorsys, re
import numpy as np, cv2
import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFont
from engine import Z, OWN, MATCH_X

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONTB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def code_colors(codes):
    codes = sorted(codes)
    cols = {}
    for n, c in enumerate(codes):
        h = (n * 0.61803398875) % 1.0
        r, g, b = colorsys.hsv_to_rgb(h, 0.85, 0.80)
        cols[c] = (int(r * 255), int(g * 255), int(b * 255))
    return cols

def room_polygons(S):
    polys = {}
    for k, num in enumerate(S.room_numbers):
        m = (S.R == k + 1).astype(np.uint8)
        if not m.any(): continue
        cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        out = []
        for c in cs:
            if cv2.contourArea(c) < 30: continue
            c = cv2.approxPolyDP(c, 2.0, True)
            out.append([(float(p[0][0]) / Z, float(p[0][1]) / Z) for p in c])
        polys[num] = out
    return polys

def render(o, fn, out_png, out_pdf=None, dpi=200, crop=None, scale_font=1.0):
    S, inst, C, G, bays, bars, res = o['_objs'][fn]
    sheet_label = 'A06.04A (east)' if fn == 'east' else 'A06.04B (west)'
    doc = fitz.open(f"{fn}.pdf"); page = doc[0]
    s = dpi / 72.0
    clip = fitz.Rect(crop) if crop else page.rect
    pix = page.get_pixmap(dpi=dpi, clip=clip)
    base = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    # fade the drawing so markup reads clearly
    base = Image.blend(base, Image.new("RGB", base.size, "white"), 0.35)
    ov = Image.new("RGBA", base.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    ox, oy = clip.x0, clip.y0
    P = lambda p: ((p[0] - ox) * s, (p[1] - oy) * s)
    f = lambda sz: ImageFont.truetype(FONT, max(8, int(sz * s / 2.78 * scale_font)))
    fb = lambda sz: ImageFont.truetype(FONTB, max(8, int(sz * s / 2.78 * scale_font)))
    rows = [r for r in o['rows'] if r['sheet'] == sheet_label]
    cols = code_colors(set(r['drawing_code'] for r in o['rows']))
    # ---- other-sheet side of match line
    mx = MATCH_X[fn]
    if fn == 'east':
        d.rectangle([P((0, 0)), P((mx, page.rect.height))], fill=(120, 120, 120, 40))
        d.text(P((mx - 48, 110)), "counted on\nA06.04B", fill=(90, 90, 90, 255), font=fb(7))
    else:
        d.rectangle([P((mx, 0)), P((page.rect.width, page.rect.height))], fill=(120, 120, 120, 40))
        d.text(P((mx + 6, 110)), "counted on\nA06.04A", fill=(90, 90, 90, 255), font=fb(7))
    # ---- rooms
    polys = room_polygons(S)
    for n, (num, pl) in enumerate(sorted(polys.items())):
        h = (n * 0.37) % 1.0
        r_, g_, b_ = [int(v * 255) for v in colorsys.hsv_to_rgb(h, 0.35, 0.95)]
        meta = o['rooms'].get(fn + ':' + num, {})
        dashed = not meta.get('boundary_method', '').startswith('enclosed')
        for poly in pl:
            pts = [P(p) for p in poly]
            d.polygon(pts, fill=(r_, g_, b_, 38))
            col = (40, 120, 200, 255) if not dashed else (230, 120, 0, 255)
            d.line(pts + [pts[0]], fill=col, width=max(2, int(0.9 * s)))
        # room id at centroid of largest polygon
        if pl:
            big = max(pl, key=lambda q: abs(cv2.contourArea(np.array(q, np.float32))))
            cx = sum(p[0] for p in big) / len(big); cy = sum(p[1] for p in big) / len(big)
            m = cv2.moments(np.array(big, np.float32))
            if m['m00']: cx, cy = m['m10'] / m['m00'], m['m01'] / m['m00']
            label = num + (' *' if dashed else '')
            d.text(P((cx - 8, cy - 4)), label, fill=(20, 80, 170, 230) if not dashed else (200, 90, 0, 230), font=fb(9))
    # ---- counted instances
    inst_by_id = {i['id']: i for i in inst}
    bay_by_id = {b['id']: b for b in bays}
    bar_by_id = {b['id']: b for b in bars}
    asm = o['_sheetdata'][fn]['asm']
    marked = set()
    for r in rows:
        col = cols[r['drawing_code']] + (255,)
        ids = [x for x in r['counted_ids'].split(', ') if x]
        for iid in ids:
            if iid in inst_by_id:
                i = inst_by_id[iid]; c = P(i['c']); rr = 5.5 * s
                d.ellipse([c[0] - rr, c[1] - rr, c[0] + rr, c[1] + rr], outline=col, width=max(2, int(0.7 * s)))
                d.text((c[0] + rr * 0.8, c[1] - rr * 1.25), iid.split('-')[1], fill=col, font=fb(4.2))
                marked.add(iid)
            elif iid in bay_by_id:
                b = bay_by_id[iid]; x0, y0, x1, y1 = b['rect']
                d.rectangle([P((x0 - 0.8, y0 - 0.8)), P((x1 + 0.8, y1 + 0.8))], outline=col, width=max(3, int(1.1 * s)))
                c = P(b['c']); d.text((c[0] - 8, c[1] + 3), iid.split('-')[1], fill=col, font=fb(4.2))
            elif iid in bar_by_id:
                b = bar_by_id[iid]; x0, y0, x1, y1 = b['rect']
                d.rectangle([P((x0 - 1.2, y0 - 1.2)), P((x1 + 1.2, y1 + 1.2))], outline=col, width=max(3, int(1.0 * s)))
                c = P(b['c']); d.text((c[0] + 6, c[1] + 3), iid.split('-')[1], fill=col, font=fb(4.5))
            elif re.match(r'^[EW]-S\d+$', iid):
                comp = [inst[k] for k, a in asm.items() if a == iid]
                for i in comp:
                    c = P(i['c']); rr = 5.5 * s
                    d.ellipse([c[0] - rr, c[1] - rr, c[0] + rr, c[1] + rr], outline=col, width=max(2, int(0.7 * s)))
                    d.text((c[0] + rr * 0.8, c[1] - rr * 1.25), i['id'].split('-')[1], fill=col, font=fb(4.2))
                    marked.add(i['id'])
                if comp:
                    xs = [i['c'][0] for i in comp]; ys = [i['c'][1] for i in comp]
                    d.rectangle([P((min(xs) - 12, min(ys) - 12)), P((max(xs) + 12, max(ys) + 12))], outline=col, width=max(2, int(0.6 * s)))
                    d.text(P((min(xs) - 12, max(ys) + 13)), iid.split('-')[1], fill=col, font=fb(5))
            elif iid.startswith(fn[0].upper() + '-T') or iid.startswith(fn[0].upper() + '-H'):
                pass
        # HDF system outline
        if 'filing/shelving bank' in r['target_symbol']:
            from hdf import bank_sections
            for rr_ in [x for x in res if x['callout']['id'] in r['callout_ids'].split(', ')]:
                b = bank_sections(S, rr_['callout']['endpoint'], G)
                if b:
                    x0, y0, x1, y1 = b['bbox']
                    for k in range(0, 4):
                        pass
                    d.rectangle([P((x0 - 2, y0 - 2)), P((x1 + 2, y1 + 2))], outline=col, width=max(3, int(1.0 * s)))
                    d.text(P((x0, y0 - 9)), 'HDF system (%s)' % (r['counted_ids']), fill=col, font=fb(5))
    # ---- uncoded architect instances (exceptions)
    for i in inst:
        if i['owned'] and i['id'] not in marked and ('-' in i['tag'] or i['tag'] in ('F', 'L')) and i['tag'] != 'F-1':
            c = P(i['c']); rr = 5.5 * s
            d.rectangle([c[0] - rr, c[1] - rr, c[0] + rr, c[1] + rr], outline=(255, 110, 0, 255), width=max(2, int(0.7 * s)))
            d.text((c[0] + rr, c[1] - rr * 1.3), i['id'].split('-')[1] + ' uncoded', fill=(230, 90, 0, 255), font=fb(4.2))
    # ---- exceptions with a location
    for e in o['exceptions']:
        if e['sheet'] != sheet_label: continue
        m = re.match(r'\((\d+), (\d+)\) pt, (\d+) x (\d+) pt', e['related_ids'])
        if m:
            cx, cy, w, h = map(float, m.groups())
            x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
            # dashed rectangle
            for (a, b) in [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]:
                L = math.hypot(b[0] - a[0], b[1] - a[1]); n = max(1, int(L / 3))
                for k in range(0, n, 2):
                    p0 = (a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
                    p1 = (a[0] + (b[0] - a[0]) * min(k + 1, n) / n, a[1] + (b[1] - a[1]) * min(k + 1, n) / n)
                    d.line([P(p0), P(p1)], fill=(255, 110, 0, 255), width=max(2, int(0.8 * s)))
            d.text(P((x0, y0 - 7)), e['exception_id'], fill=(230, 90, 0, 255), font=fb(5))
    # ---- leaders + endpoints + callout ids
    for r in res:
        co = r['callout']
        col = cols.get(co['code'], (200, 0, 150)) + (255,)
        pts = [P(p) for p in co['path']]
        d.line(pts, fill=(220, 0, 160, 230), width=max(2, int(0.9 * s)))
        e = P(co['endpoint']); rr = 4.2 * s
        d.ellipse([e[0] - rr, e[1] - rr, e[0] + rr, e[1] + rr], outline=(220, 0, 160, 255), width=max(3, int(1.2 * s)))
        d.text((e[0] + rr, e[1] + rr * 0.2), co['id'].split('-')[1], fill=(200, 0, 140, 255), font=fb(5))
        lb = co['label_rect'] or co['extent']
        d.rectangle([P((lb[0] - 1, lb[1] - 1)), P((lb[2] + 1, lb[3] + 1))], outline=(220, 0, 160, 255), width=max(2, int(0.7 * s)))
        d.text(P((lb[0], lb[1] - 7.5)), co['id'].split('-')[1], fill=(200, 0, 140, 255), font=fb(5.5))
    img = Image.alpha_composite(base.convert("RGBA"), ov).convert("RGB")
    # legend
    if not crop:
        L = ImageDraw.Draw(img)
        lx, ly = 18 * s, 18 * s
        lines = [("Sheet %s - review overlay (plan takeoff)" % sheet_label, (0, 0, 0)),
                 ("magenta: traced leader, endpoint ring = symbol identified, Cnn = callout id", (200, 0, 140)),
                 ("blue outline = room boundary (walls/doors); orange outline + '*' = open-plan / inferred boundary", (40, 120, 200)),
                 ("coloured ring + Tnnn = counted tagged symbol (colour = drawing code); Wnn = glazing bay; Ann = wall item; Snn = assembly", (60, 60, 60)),
                 ("orange square = tagged symbol with no code in its room; orange dashed box + Xnnn = exception", (230, 90, 0)),
                 ("grey band = beyond match line (counted on the other sheet)", (90, 90, 90))]
        for t, c in lines:
            L.text((lx, ly), t, fill=c, font=ImageFont.truetype(FONTB if t.startswith('Sheet') else FONT, int(5.5 * s)))
            ly += 7.5 * s
    img.save(out_png, optimize=True)
    if out_pdf:
        img.save(out_pdf, "PDF", resolution=dpi)
    return img.size

if __name__ == "__main__":
    from report2 import build_all
    o = build_all()
    print(render(o, 'east', 'ov_east.png', 'ov_east.pdf', dpi=200))
    print(render(o, 'west', 'ov_west.png', 'ov_west.pdf', dpi=200))
