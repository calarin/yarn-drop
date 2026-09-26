"""In-symbol tag extraction with character-level splitting of joined strings."""
import pymupdf as fitz, json, re, math

SUF = r'(?:[A-Z](?![A-Z0-9-]))?'
TAG_RE = re.compile(r'([A-Z]{1,3}-\d+' + SUF + r'(?:\.\d+' + SUF + r')?|(?:CAB|[BDFPO])\d+' + SUF + r')')
SINGLE = {'F', 'L'}
CODE_RE = re.compile(r'^[A-Z]{2,4}-\d{3}(\.\d+)?[A-Z]*$')

def extract(fn):
    d = fitz.open(f"{fn}.pdf"); p = d[0]; M = p.rotation_matrix
    raw = p.get_text("rawdict")
    out = []
    for b in raw['blocks']:
        for l in b.get('lines', []):
            dx, dy = l['dir']
            ddx, ddy = M.a*dx + M.c*dy, M.b*dx + M.d*dy
            for s in l['spans']:
                size = s['size']
                if not (5.0 < size < 7.0 or 8.2 < size < 8.3): continue
                chars = s['chars']
                text = "".join(c['c'] for c in chars)
                if 8.2 < size < 8.3 and (CODE_RE.match(text.strip()) or text.strip().rstrip('.') == 'TYP'): continue
                # tokenise; keep char index spans
                if text.strip() in SINGLE:
                    ms = [re.search(re.escape(text.strip()), text)]
                else:
                    ms = list(TAG_RE.finditer(text))
                for m in ms:
                    tok = m.group(0)
                    cs = chars[m.start():m.end()]
                    boxes = [fitz.Rect(c['bbox']) * M for c in cs]
                    x0 = min(r.x0 for r in boxes); y0 = min(r.y0 for r in boxes)
                    x1 = max(r.x1 for r in boxes); y1 = max(r.y1 for r in boxes)
                    ang = math.degrees(math.atan2(ddy, ddx))
                    out.append(dict(tag=tok, joined=(text.strip() != tok), source_text=text.strip(),
                                    bbox=[x0, y0, x1, y1], c=[(x0+x1)/2, (y0+y1)/2], size=round(size, 2), angle=round(ang, 1)))
    return out

if __name__ == "__main__":
    for fn in ("east", "west"):
        L = extract(fn)
        json.dump(L, open(f"{fn}_tags.json", "w"), indent=0)
        import collections
        c = collections.Counter(x['tag'] for x in L)
        print(fn, len(L), sorted(c.items()))
        print("  joined:", sorted(set(x['source_text'] for x in L if x['joined'])))
