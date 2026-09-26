"""Group white-mask fills into pieces (one block instance each) and attach tags."""
import math
from shapely.geometry import Point
from shapely.ops import unary_union

def build_pieces(S, tol_tag=0.8, seq_gap=4, touch=0.6):
    ms = sorted(S.masks, key=lambda m: S.P[m['idx']]['seqno'])
    # tags per mask (smallest containing mask)
    tag_mask = {}
    for k, t in enumerate(S.tags):
        P_ = Point(t['c'])
        c = [m for m in ms if m['rect'][0] - tol_tag <= t['c'][0] <= m['rect'][2] + tol_tag and
             m['rect'][1] - tol_tag <= t['c'][1] <= m['rect'][3] + tol_tag and m['poly'].distance(P_) <= tol_tag]
        if c:
            c.sort(key=lambda m: (0 if m['poly'].contains(P_) else 1, m['area']))
            tag_mask[k] = c[0]['idx']
    arch = lambda k: ('-' in S.tags[k]['tag']) or S.tags[k]['tag'] in ('F', 'L')
    mask_tags = {}
    for k, mi in tag_mask.items(): mask_tags.setdefault(mi, []).append(k)
    groups = []
    for m in ms:
        seq = S.P[m['idx']]['seqno']
        mt = mask_tags.get(m['idx'], [])
        if groups:
            g = groups[-1]
            if seq - g['last_seq'] <= seq_gap and g['poly'].distance(m['poly']) < touch:
                n_arch = sum(1 for k in g['tags'] + mt if arch(k))
                if n_arch <= 1:
                    g['masks'].append(m['idx']); g['poly'] = unary_union([g['poly'], m['poly']]); g['last_seq'] = seq
                    g['tags'] += mt
                    continue
        groups.append(dict(masks=[m['idx']], poly=m['poly'], last_seq=seq, tags=list(mt)))
    for gi, g in enumerate(groups):
        b = g['poly'].bounds
        g['rect'] = [b[0], b[1], b[2], b[3]]; g['area'] = g['poly'].area; g['id'] = gi
    # tags not in any mask: nearest piece within 2.5pt (dealer tags usually have no mask)
    return groups, tag_mask

if __name__ == "__main__":
    from engine import Sheet
    for fn in ("east", "west"):
        S = Sheet(fn)
        G, TM = build_pieces(S)
        arch_no_piece = [S.tags[k]['tag'] for k in range(len(S.tags)) if k not in TM and ('-' in S.tags[k]['tag'] or S.tags[k]['tag'] in ('F','L'))]
        multi = [(g['id'], [S.tags[k]['tag'] for k in g['tags']]) for g in G if sum(1 for k in g['tags'] if '-' in S.tags[k]['tag']) > 1]
        print(fn, "masks", len(S.masks), "pieces", len(G), "untagged pieces", sum(1 for g in G if not g['tags']))
        print("   architect tags without a mask piece:", arch_no_piece)
        print("   pieces with >1 architect tag (single mask holding several):", multi[:20])
