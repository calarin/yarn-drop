"""Additional exception categories, component table and summary on top of report.build()."""
import json, math
from collections import defaultdict, Counter
from shapely.geometry import Point, box
from report import build, SHEET_NAME
from engine import is_arch, OWN

def untagged_pieces(S, inst, G, bars, res):
    """Mask pieces with no tag that are not annotation backgrounds, sub-parts of tagged pieces or wall bars."""
    tagged_ids = set(i['piece'] for i in inst if i['piece'] is not None)
    tagged_polys = [g['poly'] for g in G if g['id'] in tagged_ids]
    bar_masks = set(b['mask_idx'] for b in bars)
    ann = []
    for R in S.rooms_meta:
        for bb in ([R['box']] if R['box'] else []) + R['name_bboxes']:
            ann.append(box(bb[0] - 1, bb[1] - 1, bb[2] + 1, bb[3] + 1))
    for L in S.labels:
        e = L['extent']; ann.append(box(e[0] - 1, e[1] - 1, e[2] + 1, e[3] + 1))
    hdf_pts = [Point(r['callout']['endpoint']) for r in res if r['target_kind'] == 'hdf-system']
    out = []
    for g in G:
        if g['id'] in tagged_ids or any(mi in bar_masks for mi in g['masks']): continue
        c = g['poly'].centroid
        if not OWN[S.fn](c.x): continue
        x0, y0, x1, y1 = g['rect']
        if g['area'] < 60 or min(x1 - x0, y1 - y0) < 2.0: continue
        if g['area'] / max((x1 - x0) * (y1 - y0), 1e-6) < 0.15: continue   # scattered slivers, not an object
        if any(g['poly'].intersection(a).area > 0.5 * g['area'] for a in ann): continue
        if any(g['poly'].contains(a.centroid) for a in ann): continue          # background behind a tag/label
        if any(not is_arch(i['tag']) and g['poly'].distance(Point(i['c'])) < 3.0 for i in inst): continue   # dealer component outline
        if any(g['poly'].distance(tp) < 0.6 for tp in tagged_polys): continue
        rm, how, alts = S.room_for_point((c.x, c.y))
        if rm is None:
            rm = S.room_for_poly(g['poly'])[0]
        if rm is None: continue
        hdf = any(g['poly'].distance(h) < 1.0 for h in hdf_pts)
        # graphic description from linework inside the piece
        hatch = 0; fixture = 0
        for pr in S.P:
            if pr['type'] != 's' or not pr['color']: continue
            r0 = pr['rect']
            if r0[0] < x0 - 0.5 or r0[2] > x1 + 0.5 or r0[1] < y0 - 0.5 or r0[3] > y1 + 0.5: continue
            col = round(pr['color'][0], 2)
            if col in (0.62, 0.63, 0.67):
                its = pr['items']
                if len(its) == 1 and its[0][0] == 'l':
                    (ax, ay), (bx, by) = its[0][1], its[0][2]
                    if abs(ax - bx) > 1 and abs(ay - by) > 1: hatch += 1
            if col in (0.71, 0.83): fixture += 1
        w, h = x1 - x0, y1 - y0
        near_dealer = sorted(set(i['tag'] for i in inst if not is_arch(i['tag']) and g['poly'].distance(Point(i['c'])) < 8.0))
        if min(w, h) < 7 and max(w, h) > 60:
            desc = 'thin masked strip along a wall' + ((' (next to component tags %s; may belong to them)' % '/'.join(near_dealer)) if near_dealer else '')
        elif hatch >= 2: desc = 'gray diagonal-hatched item'
        elif fixture >= 3: desc = 'counter/fixture area with plumbing-fixture linework'
        else: desc = 'masked item'
        out.append(dict(rect=g['rect'], c=(c.x, c.y), area=g['area'], room=rm, hdf=hdf, desc=desc))
    return out

def build_all():
    o = build()
    exc = o['exceptions']
    def X(cat, sheet, room, code, ids, text, action, severity='Review', site=False):
        exc.append(dict(category=cat, sheet=SHEET_NAME.get(sheet, sheet), room=room or '', code=code or '', related_ids=ids,
                        description=text, recommended_action=action, severity=severity, site_check=('Yes' if site else '')))
    for e in exc: e.setdefault('site_check', '')
    rows = o['rows']
    # tag -> codes (rows)
    tag_codes = defaultdict(set)
    for r in rows:
        for t in r['target_symbol'].split('; '):
            tag = t.split(' (')[0].replace(' assembly', '')
            if r['drawing_code']: tag_codes[tag].add((r['drawing_code'], r['sheet'].split(' ')[0], r['room_number']))
    # ---------------- uncoded architect-tag instances
    unc = defaultdict(list)
    for i in o['instances']:
        if i['status'] == 'not coded in this room':
            unc[(i['sheet'], i['room_number'], i['symbol_tag'])].append(i['instance_id'])
    for (sh, rm, tag), ids in sorted(unc.items()):
        hint = sorted(set(c for c, _, _ in tag_codes.get(tag, set())))
        where = sorted(set('%s' % r for _, _, r in tag_codes.get(tag, set())))
        sheet_key = 'east' if sh.startswith('A06.04A') else 'west'
        room_name = o['rooms'].get(sheet_key + ':' + rm, {}).get('name', '')
        X('Tagged symbol with no leader code in room', sheet_key, rm, ('/'.join(hint) + '?') if hint else '', ', '.join(ids),
          '%d x %s in %s %s %s no code leader in this room.%s Not included in coded quantities.' % (
              len(ids), tag, rm, room_name, 'carries' if len(ids) == 1 else 'carry',
              (' The same in-symbol tag is coded %s in room(s) %s.' % (' / '.join(hint), ', '.join(where))) if hint else ' The tag is not coded anywhere on these sheets.'),
          'Designer to confirm the code (a TYP elsewhere may be intended to cover these); add a leader or schedule entry.', 'Review')
    # ---------------- same tag, different codes across rooms
    for tag, s in sorted(tag_codes.items()):
        codes = sorted(set(c for c, _, _ in s))
        if len(codes) > 1:
            detail = '; '.join('%s in %s' % (c, ', '.join(sorted(set(r for cc, _, r in s if cc == c)))) for c in codes)
            X('Same in-symbol tag carries different codes', '', '', ', '.join(codes), tag,
              'Symbol tag %s is coded differently by room: %s. Counts are kept per room as drawn; this may be an intended substitution or a tagging inconsistency.' % (tag, detail),
              'Confirm against the furniture schedule.', 'Review')
    # ---------------- no TYP but repeats counted
    for r in rows:
        if r['typ_on_label'] == 'no' and isinstance(r['plan_qty'], int) and r['plan_qty'] > 1 and 'glazing' not in r['unit']:
            X('Code label without TYP; repeated symbols counted', r['sheet'].split(' ')[0].lower() if False else ('east' if r['sheet'].startswith('A06.04A') else 'west'),
              r['room_number'], r['drawing_code'], r['row_id'] + ': ' + r['counted_ids'],
              'The label has no TYP, but %d matching %s symbols are shown in the room; all are counted per the counting rule.' % (r['plan_qty'], r['target_symbol']),
              'Confirm the untagged repeats are the same item.', 'Info')
    # ---------------- untagged pieces, boundaries, other notices
    comp_rows = []
    for fn in ('east', 'west'):
        S, inst, C, G, bays, bars, res = o['_objs'][fn]
        for u in untagged_pieces(S, inst, G, bars, res):
            if u['hdf']: continue
            X('Untagged item (no in-symbol tag, no code)', fn, u['room'], '', '(%.0f, %.0f) pt, %.0f x %.0f pt' % (
                u['c'][0], u['c'][1], u['rect'][2] - u['rect'][0], u['rect'][3] - u['rect'][1]),
              '%s with no tag and no leader in %s at (%.0f, %.0f) pt (%.0f x %.0f pt). No legend is supplied to say whether it is millwork, existing/relocated furniture, equipment or by others; it is not counted.' % (
                  u['desc'][0].upper() + u['desc'][1:], u['room'], u['c'][0], u['c'][1], u['rect'][2] - u['rect'][0], u['rect'][3] - u['rect'][1]),
              'Identify from the schedule or a site/photo check.', 'Review', site=True)
        # tag-bearing pieces far larger than the usual piece for that tag -> probable untagged item holding smaller items' tags
        by_piece = defaultdict(list)
        for i in inst:
            if i['owned'] and i['piece'] is not None and is_arch(i['tag']):
                by_piece[i['piece']].append(i)
        gpid = {g['id']: g for g in G}
        for pid, lst in by_piece.items():
            g = gpid[pid]
            for tag in set(i['tag'] for i in lst):
                same = [i for i in lst if i['tag'] == tag]
                if len(same) >= 3 and all(g['poly'].boundary.distance(Point(i['c'])) < 3.0 for i in same):
                    x0, y0, x1, y1 = g['rect']
                    rm = S.room_for_poly(g['poly'])[0]
                    X('Untagged item (no in-symbol tag, no code)', fn, rm, '', '(%.0f, %.0f) pt, %.0f x %.0f pt' % ((x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0),
                      'Large masked item (%.0f x %.0f pt) in %s whose outline overlaps %s tags of adjoining smaller pieces (for example the chairs tucked under it); the item itself has no tag or leader and is not counted.' % (
                          x1 - x0, y1 - y0, rm, tag),
                      'Identify from the schedule or a site/photo check.', 'Review', site=True)
        # room boundary notices
        for n, m in S.room_method.items():
            if m.startswith('enclosed'): continue
            X('Room boundary inferred (open plan / no door)', fn, n, '', '', 'Boundary of %s: %s.' % (n, m),
              'Check the boundary drawn on the overlay; items near the line are flagged on their rows.', 'Info' if 'LOW' not in m else 'Review')
        # component tags (dealer) table
        cnt = Counter()
        ids = defaultdict(list)
        for i in inst:
            if i['owned'] and not is_arch(i['tag']):
                cnt[(i['room'], i['tag'])] += 1; ids[(i['room'], i['tag'])].append(i['id'])
        for (rm, tag), n in sorted(cnt.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
            comp_rows.append(dict(sheet=SHEET_NAME[fn], room_number=rm or '', room_name=o['rooms'].get(fn + ':' + str(rm), {}).get('name', ''),
                                  component_tag=tag, qty_shown=n, instance_ids=', '.join(ids[(rm, tag)]),
                                  note='Component tag inside workstation/casework linework; no leader code on these sheets. Listed for completeness, not reconciled to a code.'))
    # specific drawing notices (from visual review of the sheets)
    X('Room tag leader ends at a wall', 'east', '404', '', 'room tag 404',
      'The ELEC CLOSET 404 tag sits west of the match line and its leader ends at (183.1, 642.7) pt, on the corridor side of the closet wall; the room region used is the small pocket at that point.',
      'Confirm the extent of room 404 (no furniture is shown in it).', 'Review')
    X('Revision cloud / delta tags', 'west', '435', '', 'cloud around 435; deltas 5 and 6',
      'A revision cloud with delta 6 surrounds CLEANING CLOSET 435; delta 5 triangles appear in 443 and near 447. A circle tag "C07" with an arrow points to the B1 unit in 435. These are revision or keynote marks, not furniture codes.',
      'Confirm the plan revision used for the model matches this issue.', 'Info')
    X('Curved facade glazing not counted', 'east', '413-417', 'WTR-500?', 'curved exterior wall',
      'The curved exterior wall of ADMIN 413, E/O 414-416 and CHIEF ETHICS OFFICER 417 is drawn as arcs without individual glazing panes, '
      'and no WTR leader points to it; window bays there were not counted.',
      'Confirm whether WTR-500 applies to the curved facade and how many units (schedule / site check).', 'Review', site=True)
    X('Non-furniture tag', 'west', '446', '', '"602" circle tag',
      'A circle tag "602" with an arrow points at the D3 worksurface in FLAG REP 446. It is not in the furniture code format and was not counted.',
      'Confirm meaning (keynote/equipment tag).', 'Info')
    X('Hidden CAD attribute text in PDF', '', '', '', 'both sheets',
      'Both PDFs contain 0.1 pt invisible text at many symbol insertion points (dealer block attributes such as product-style strings). They were NOT used to fill descriptions, manufacturers or model numbers. They were only used to confirm the drawing scale.',
      'Obtain the furniture schedule / product data for specifications.', 'Info')
    X('Inputs not supplied', '', '', '', 'IFC model; tag catalog; furniture schedule',
      'The fourth-floor model objects, the existing tag catalog and any furniture schedule were not included with the request. Model quantities, differences, GlobalIds and code descriptions are therefore blank; room links were re-derived from the drawings instead of re-checked against the catalog.',
      'Provide the IFC (or export) and the catalog; run tools/ifc_inventory.py and tools/compare_model.py.', 'High')
    X('Drawing scale inferred', '', '', '', 'both sheets',
      'No scale is shown on the supplied crops. Standard object sizes (3 ft doors = 27 pt; 30x48 in desks = 22.4x36 pt) are consistent with 1/8" = 1\'-0" (9 pt per ft). Floor coordinates (ft from grid 4 / B.1) use this and are approximate.',
      'Confirm the plot scale before using coordinates for model matching.', 'Info')
    # renumber exceptions
    for n, e in enumerate(exc): e['exception_id'] = 'X%03d' % (n + 1)
    o['components'] = comp_rows
    return o

if __name__ == "__main__":
    o = build_all()
    c = Counter(e['category'] for e in o['exceptions'])
    for k, v in c.most_common(): print(v, k)
    print("components rows", len(o['components']))
