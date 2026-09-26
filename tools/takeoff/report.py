"""Build all takeoff tables (JSON) from the traced drawings."""
import json, math, re
from collections import defaultdict, Counter
from shapely.geometry import Point
from engine import compatible, is_arch, OWN, rect_dist
from takeoff import run
from count import to_floor

SHEET_NAME = {'east': 'A06.04A (east)', 'west': 'A06.04B (west)'}
PILOT = [('east', '453'), ('east', '427'), ('east', '412'), ('east', '431'), ('west', '443'), ('west', '451')]
NO_SCHEDULE = 'Not supplied (no furniture schedule provided)'
MODEL_NA = 'Model not supplied'

def room_table(S):
    rows = {}
    lead = {t['target'][1]: t for t in S.traces if t['target'] and t['target'][0] == 'room'}
    for ri, R in enumerate(S.rooms_meta):
        n = R['number']
        m = S.room_method.get(n, '')
        area = int((S.R == ri + 1).sum()) / 9.0  # pt^2
        seed = lead[ri]['dot']['c'] if ri in lead else None
        conf = 'High' if m.startswith('enclosed') else ('Low' if 'LOW' in m or 'seed' in m else 'Medium')
        rows[n] = dict(sheet=S.fn, number=n, name=R['name'], tag_box=R['box'], tag_leader_endpoint=seed,
                       seed_method=('room-tag leader endpoint' if seed else 'room-tag position (no leader)'),
                       boundary_method=m, boundary_confidence=conf, area_sqft=round(area / 81.0, 1))
    return rows

def naive_room(S, rect):
    """Room whose tag is nearest to the label box: the 'label position' assignment a text-only catalog would make."""
    cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
    best = None
    for R in S.rooms_meta:
        b = R['box'] or R['num_bbox']
        d = math.hypot((b[0] + b[2]) / 2 - cx, (b[1] + b[3]) / 2 - cy)
        if best is None or d < best[0]: best = (d, R['number'])
    return best[1] if best else None

def build():
    out = dict(rooms={}, callouts=[], rows=[], instances=[], exceptions=[], components=[], summary={})
    all_sheets = {}
    for fn in ('east', 'west'):
        all_sheets[fn] = run(fn)
    # ------------------------------------------------------------------ per sheet
    row_n = 0
    inst_rows = {}
    exc = []
    def X(cat, sheet, room, code, ids, text, action, severity='Review'):
        exc.append(dict(category=cat, sheet=SHEET_NAME.get(sheet, sheet), room=room or '', code=code or '', related_ids=ids,
                        description=text, recommended_action=action, severity=severity))
    code_by_tag_room = defaultdict(set)   # (tag) -> set((sheet, room, code))
    for fn, (S, inst, C, G, bays, bars, res) in all_sheets.items():
        rooms = room_table(S)
        out['rooms'].update({(fn + ':' + k): v for k, v in rooms.items()})
        rname = {k: v['name'] for k, v in rooms.items()}
        by_id = {i['id']: (k, i) for k, i in enumerate(inst)}
        gp = {g['id']: g for g in G}
        # assemblies: single-letter return components attached to a D- piece
        comp_of = {}
        for k, i in enumerate(inst):
            if i['owned'] and i['tag'] in ('F', 'L') and i['piece'] is not None:
                att = []
                for k2, j in enumerate(inst):
                    if j['owned'] and j['piece'] is not None and j['piece'] != i['piece'] and j['room'] == i['room'] and j['tag'].startswith('D-'):
                        if gp[i['piece']]['poly'].distance(gp[j['piece']]['poly']) < 1.0: att.append(k2)
                if att:
                    comp_of[k] = att
        # choose the host desk for each F/L: the one that is a D-6/D-6A (not separately coded D-3)
        host = {}
        for k, att in comp_of.items():
            pref = [a for a in att if inst[a]['tag'] in ('D-6A', 'D-6')] or att
            host[k] = pref[0]
        assemblies = defaultdict(list)
        for k, h in host.items(): assemblies[h].append(k)
        asm_id = {}
        for n, h in enumerate(sorted(assemblies, key=lambda h: inst[h]['id'])):
            aid = '%s-S%02d' % (fn[0].upper(), n + 1)
            asm_id[h] = aid
            for k in assemblies[h]: asm_id[k] = aid
        def assembly_sig(h):
            return '+'.join([inst[h]['tag']] + sorted(inst[k]['tag'] for k in assemblies[h]))
        # disambiguation pass (same as count.py)
        room_tag_code = defaultdict(set)
        for r in res:
            if r['target_kind'] == 'tagged-piece' and not r.get('ambiguous'):
                room_tag_code[(r['room'], r['target_tag'])].add(r['callout']['code'])
        for r in res:
            co = r['callout']
            if r['target_kind'] == 'tagged-piece' and r.get('ambiguous'):
                cands = [tuple(c.split(':', 1)) for c in r['candidates']]
                prim = cands[0]; alts = [c for c in cands[1:] if c[1] != prim[1]]
                claimed = room_tag_code.get((r['room'], prim[1]), set()) - {co['code']}
                free = [a for a in alts if not (room_tag_code.get((r['room'], a[1]), set()) - {co['code']})]
                if claimed and free:
                    k, i = by_id[free[0][0]]
                    r['disambiguation'] = ('Endpoint lies on the shared edge of %s and %s. %s in this room is already tagged %s, '
                                           'so %s is adopted as the probable target.' % (prim[1], free[0][1], prim[1], ', '.join(sorted(claimed)), free[0][1]))
                    r['target'], r['target_tag'], r['target_k'] = i['id'], i['tag'], k
                    r['resolution'] = 'probable'
                else:
                    r['disambiguation'] = 'Endpoint lies on the shared edge of %s; no drawing evidence separates them.' % ' and '.join(sorted(set(c[1] for c in cands)))
                    r['resolution'] = 'unresolved'
                    r['alternatives'] = [c[0] for c in cands]
        # ---------------- callout catalog
        for r in res:
            co = r['callout']
            nv = naive_room(S, co['label_rect'] or co['extent'])
            out['callouts'].append(dict(
                callout_id=co['id'], sheet=SHEET_NAME[fn], code=co['code'], typ=co['typ'] or '',
                label_box_pt=[round(v, 1) for v in (co['label_rect'] or co['extent'])],
                leader_path_pt=[[round(p[0], 1), round(p[1], 1)] for p in co['path']][::-1],
                leader_bends=max(0, len(co['path']) - 2),
                endpoint_pt=[round(co['endpoint'][0], 1), round(co['endpoint'][1], 1)],
                endpoint_floor_ft=to_floor(fn, co['endpoint']),
                trace_check=('geometric chain from dot to label; segments drawn in the same annotation group as the label box'
                             + ('' if not co['trace_notes'] else '; ' + '; '.join(co['trace_notes']))),
                target_kind=r['target_kind'], target=r.get('target', ''), target_symbol=r.get('target_tag', ''),
                room=r.get('room') or '', room_name=rname.get(r.get('room'), ''), room_method=r.get('room_how', ''),
                naive_room_by_label_position=nv or '', naive_differs=(bool(r.get('room')) and nv != r.get('room')),
                notes='; '.join(r.get('notes', []) + ([r['disambiguation']] if r.get('disambiguation') else []))))
        # ---------------- rows (room x code)
        groups = defaultdict(list)
        for r in res:
            co = r['callout']
            if r['target_kind'] == 'other-sheet':
                continue
            groups[(r.get('room') or '-', co['code'])].append(r)
        claimed_inst = defaultdict(set)
        for (room, code), rs in sorted(groups.items()):
            row_n += 1
            rid = 'R%03d' % row_n
            matched = []; targets = []; ev = []; conf_pts = []; flags = []; split_flag = []
            item_class = set(); unit = set()
            for r in rs:
                co = r['callout']
                kind = r['target_kind']
                if kind == 'tagged-piece':
                    k0 = r['target_k']; t0 = inst[k0]
                    # assembly?
                    h = None
                    if k0 in host: h = host[k0]
                    elif k0 in assemblies: h = k0
                    if h is not None:
                        sig = assembly_sig(h)
                        hosts = [hh for hh in assemblies if inst[hh]['room'] == room and assembly_sig(hh) == sig and inst[hh]['owned']]
                        for hh in hosts:
                            matched.append(asm_id[hh])
                            for kk in [hh] + assemblies[hh]:
                                claimed_inst[inst[kk]['id']].add(code)
                                inst_rows[inst[kk]['id']] = (rid, code, asm_id[hh])
                        targets.append(sig + ' assembly')
                        item_class.add('multi-part assembly (%s)' % sig)
                        unit.add('assembly')
                        ev.append('%s: leader ends on %s (%s) which is part of desk assembly %s; %d assembl%s of %s in room' % (
                            co['id'], t0['tag'], t0['id'], asm_id[h], len(hosts), 'y' if len(hosts) == 1 else 'ies', sig))
                        conf_pts.append(2 if not r.get('ambiguous') else 0)
                        continue
                    same = [(k, i) for k, i in enumerate(inst) if i['owned'] and i['tag'] == t0['tag'] and i['room'] == room]
                    ok, bad = [], []
                    for k, i in same:
                        c, why = compatible(t0, i)
                        (ok if c else bad).append((k, why))
                    for k, _ in ok:
                        matched.append(inst[k]['id']); claimed_inst[inst[k]['id']].add(code)
                        inst_rows[inst[k]['id']] = (rid, code, None)
                    size = None
                    if t0['mask']:
                        size = '%.0fx%.0f pt' % (t0['mask'][2] - t0['mask'][0], t0['mask'][3] - t0['mask'][1])
                    targets.append(t0['tag'] + (' (' + size + ')' if size else ''))
                    rot = sum(1 for k, _ in ok if inst[k]['rotated'])
                    jn = sum(1 for k, _ in ok if inst[k]['joined'])
                    shared = [k for k, _ in ok if inst[k]['piece'] is not None and sum(1 for j in inst if j['piece'] == inst[k]['piece'] and is_arch(j['tag'])) > 1]
                    txt = '%s: leader%s ends %s; %d x %s found in room by in-symbol tag' % (
                        co['id'], (' (' + co['typ'] + ')' if co['typ'] else ''), r.get('notes', [''])[0], len(ok), t0['tag'])
                    if rot: txt += ' (%d rotated: size not compared)' % rot
                    if jn: txt += ' (%d from joined text strings split per tag)' % jn
                    if bad: txt += '; excluded same-tag different size: %s' % ', '.join('%s (%s)' % (inst[k]['id'], w) for k, w in bad)
                    ev.append(txt)
                    if r.get('disambiguation'): ev.append(r['disambiguation'])
                    if shared:
                        item_class.add('component of a casework run sharing one outline')
                    elif t0['tag'] == 'CC-1':
                        item_class.add('individual units (stacked group)')
                    else:
                        item_class.add('individual piece')
                    unit.add('each')
                    d = r.get('dist', 0.0) or 0.0
                    nx = r.get('next_other')
                    if r.get('ambiguous'): c = 0
                    elif 'nearest in-symbol tag' in (r.get('method') or ''): c = 1
                    elif d <= 0.6: c = 2
                    elif d <= 2.0 and (nx is None or nx > max(3.0, 3 * d)): c = 2
                    else: c = 1
                    conf_pts.append(c)
                    near_split = [inst[k]['id'] for k, _ in ok if S.split_dist(inst[k]['c']) < 10]
                    if near_split:
                        split_flag.extend(near_split)
                    if bad: flags.append('same tag different size excluded')
                elif kind == 'window-bay':
                    mb = [b for b in bays if b['owned'] and b['room'] == room]
                    for b in mb:
                        matched.append(b['id']); claimed_inst[b['id']].add(code); inst_rows[b['id']] = (rid, code, None)
                    strad = [b['id'] for b in mb if 'several' in b['room_how']]
                    targets.append('glazing bay (pane %s)' % r['target'])
                    item_class.add('window-related item at exterior glazing (count basis: glazing bays)')
                    unit.add('glazing bay')
                    ev.append('%s: leader ends on exterior glazing pane %s; %d glazing bays (panes between mullions) on this room\'s exterior wall%s' % (
                        co['id'], r['target'], len(mb), ('; bays shared with adjoining room: ' + ', '.join(strad)) if strad else ''))
                    conf_pts.append(1)
                    flags.append('unit of measure unconfirmed')
                elif kind == 'wall-accessory':
                    tb = [b for b in bars if b['id'] == r['target']][0]
                    mb = [b for b in bars if b['owned'] and b['room'] == room and abs(b['length'] - tb['length']) <= 0.15 * tb['length']]
                    for b in mb:
                        matched.append(b['id']); claimed_inst[b['id']].add(code); inst_rows[b['id']] = (rid, code, None)
                    targets.append('wall-mounted bar %.0f pt (%s)' % (tb['length'], r['target']))
                    item_class.add('wall-mounted item')
                    unit.add('each')
                    ev.append('%s: leader ends on wall %s; heavy-outlined thin symbol on the %s face (%s); %d matching symbol(s) in room' % (
                        co['id'], r['target'], room, r['room_how'], len(mb)))
                    conf_pts.append(1)
                elif kind == 'hdf-system':
                    sysk = r.get('system_tags', [])
                    sid = sysk[0] if sysk else '%s-H(untagged bank)' % fn[0].upper()
                    matched.append(sid); claimed_inst[sid].add(code); inst_rows[sid] = (rid, code, None)
                    targets.append('filing/shelving bank' + (' with F-1 tag ' + ','.join(sysk) if sysk else ' (no system tag)'))
                    item_class.add('multi-part assembly (bank of sections%s)' % ('' if sysk else '; no F-1 tag'))
                    unit.add('system (assembly)')
                    ev.append('%s: leader ends on a hexagon-pattern section; %s' % (co['id'], ('bank carries in-symbol tag F-1 (%s) - one system in room' % ','.join(sysk)) if sysk else 'no F-1 system tag in this room'))
                    conf_pts.append(1)
                    flags.append('assembly vs section count unconfirmed')
                else:
                    ev.append('%s: %s' % (co['id'], '; '.join(r.get('notes', []))))
                    conf_pts.append(0)
            qty = len(set(matched))
            conf = 'High' if min(conf_pts) == 2 else ('Medium' if min(conf_pts) == 1 else 'Low')
            rm_meta = rooms.get(room, {})
            if rm_meta.get('boundary_confidence') in ('Medium', 'Low'):
                if split_flag:
                    if conf == 'High': conf = 'Medium'
                    flags.append('counted item(s) within 10 pt of an open-plan split line: ' + ', '.join(sorted(set(split_flag))))
                    ev.append('Open-plan room: %s lie within 10 pt (about 1 ft) of the inferred split line.' % ', '.join(sorted(set(split_flag))))
                elif any(k in ('tagged-piece',) for k in [r['target_kind'] for r in rs]):
                    ev.append('Open-plan room (boundary inferred at narrowest opening); all counted items are at least 10 pt from the split line.')
            unresolved = any(r.get('resolution') == 'unresolved' for r in rs)
            probable = any(r.get('resolution') == 'probable' for r in rs)
            if unresolved:
                status = 'UNRESOLVED - endpoint ambiguous; confirm target'
            elif probable:
                status = 'REVIEW - probable target adopted by rule'
            elif conf == 'High':
                status = 'Plan count checked; awaiting model comparison'
            else:
                status = 'REVIEW - ' + '; '.join(sorted(set(flags)) or ['see evidence'])
            out['rows'].append(dict(
                row_id=rid, sheet=SHEET_NAME[fn], room_number=room, room_name=rname.get(room, ''), drawing_code=code,
                code_description=NO_SCHEDULE, item_class='; '.join(sorted(item_class)), unit='; '.join(sorted(unit)),
                plan_qty=(qty if not unresolved else qty), model_qty='', difference='', model_status=MODEL_NA,
                source_sheet=SHEET_NAME[fn], callout_ids=', '.join(r['callout']['id'] for r in rs),
                typ_on_label=', '.join(sorted(set(r['callout']['typ'] or 'no' for r in rs))),
                target_symbol='; '.join(sorted(set(targets))), counted_ids=', '.join(sorted(set(matched))),
                evidence=' | '.join(ev), confidence=conf, review_status=status, pilot=((fn, room) in PILOT)))
        # ---------------- instances
        for k, i in enumerate(inst):
            if not i['owned']: continue
            rid, code, aid = inst_rows.get(i['id'], ('', '', None))
            if not aid and k in asm_id: aid = asm_id[k]
            code_by_tag_room[i['tag']].add((fn, i['room'], code))
            out['instances'].append(dict(
                instance_id=i['id'], sheet=SHEET_NAME[fn], room_number=i['room'] or '', room_name=rname.get(i['room'], ''),
                drawing_code=code, row_id=rid, symbol_tag=i['tag'], tag_family=('architect in-symbol tag' if is_arch(i['tag']) else 'dealer component tag'),
                source_text=i['source_text'], split_from_joined_text=i['joined'],
                x_pt=round(i['c'][0], 1), y_pt=round(i['c'][1], 1), floor_x_ft=to_floor(fn, i['c'])[0], floor_y_ft=to_floor(fn, i['c'])[1],
                rotation_deg=i['angle'], footprint_pt=(('%.1fx%.1f' % (i['mask'][2] - i['mask'][0], i['mask'][3] - i['mask'][1])) if i['mask'] else ''),
                assembly_id=aid or '', room_method=i['room_how'],
                status=('counted' if rid else ('not coded in this room' if is_arch(i['tag']) else 'component tag (no leader code)')),
                model_globalid='', model_name='', model_class='', match_status=MODEL_NA))
        for b in bays:
            if not b['owned']: continue
            rid, code, _ = inst_rows.get(b['id'], ('', '', None))
            out['instances'].append(dict(
                instance_id=b['id'], sheet=SHEET_NAME[fn], room_number=b['room'] or '', room_name=rname.get(b['room'], ''),
                drawing_code=code, row_id=rid, symbol_tag='glazing bay', tag_family='glazing pane (no tag)', source_text='',
                split_from_joined_text=False, x_pt=round(b['c'][0], 1), y_pt=round(b['c'][1], 1),
                floor_x_ft=to_floor(fn, b['c'])[0], floor_y_ft=to_floor(fn, b['c'])[1], rotation_deg=(0 if b['orient'] == 'H' else 90),
                footprint_pt='%.1f long' % b['length'], assembly_id='', room_method=b['room_how'],
                status=('counted' if rid else 'window bay in room without WTR leader'),
                model_globalid='', model_name='', model_class='', match_status=MODEL_NA))
        for b in bars:
            if not b['owned'] or b['id'] not in inst_rows: continue   # only wall items identified by a leader
            rid, code, _ = inst_rows.get(b['id'], ('', '', None))
            out['instances'].append(dict(
                instance_id=b['id'], sheet=SHEET_NAME[fn], room_number=b['room'] or '', room_name=rname.get(b['room'], ''),
                drawing_code=code, row_id=rid, symbol_tag='wall-mounted bar', tag_family='untagged wall symbol', source_text='',
                split_from_joined_text=False, x_pt=round(b['c'][0], 1), y_pt=round(b['c'][1], 1),
                floor_x_ft=to_floor(fn, b['c'])[0], floor_y_ft=to_floor(fn, b['c'])[1], rotation_deg='',
                footprint_pt='%.1f long' % b['length'], assembly_id='', room_method=b['room_how'],
                status=('counted' if rid else 'not coded'), model_globalid='', model_name='', model_class='', match_status=MODEL_NA))
        # ---------------- exceptions for this sheet
        for r in res:
            co = r['callout']
            if r['target_kind'] == 'other-sheet':
                other = 'W' if fn == 'east' else 'E'
                X('Duplicate callout across match line', fn, '', co['code'], co['id'],
                  '%s (%s%s) ends at x=%.1f, beyond this sheet\'s match line; the same symbol is covered on the other sheet. Not counted on this sheet.' % (
                      co['id'], co['code'], ' TYP' if co['typ'] else '', co['endpoint'][0]),
                  'Confirm the paired callout on the other sheet (see cross-sheet check) and delete one tag on the drawings.', 'Info')
            if r.get('resolution') == 'unresolved':
                X('Unresolved leader endpoint', fn, r.get('room'), co['code'], co['id'] + ' -> ' + ', '.join(r.get('alternatives', [])),
                  r['disambiguation'] + ' Quantity reported as 1 (one piece under the dot) with the target unconfirmed.',
                  'Designer to confirm which piece the code applies to; site/photo check of the unit.', 'High')
            if r.get('resolution') == 'probable':
                X('Leader endpoint on shared edge (probable target adopted)', fn, r.get('room'), co['code'], co['id'],
                  r['disambiguation'], 'Designer to confirm; if the code applies to the chairs instead, merge with the other code or split quantities.', 'High')
            if r.get('room_conflict'):
                X('Endpoint and target in different room regions', fn, r.get('room'), co['code'], co['id'], '; '.join(r.get('notes', [])),
                  'Check room boundary at this location.', 'Review')
        # window bays without WTR leader
        wtr_rooms = set(r.get('room') for r in res if r['target_kind'] == 'window-bay')
        per_room = defaultdict(list)
        for b in bays:
            if b['owned'] and b['room'] and b['room'] not in wtr_rooms: per_room[b['room']].append(b['id'])
        for rm, ids in sorted(per_room.items()):
            X('Window bays without WTR-500 leader in room', fn, rm, 'WTR-500?', ', '.join(ids),
              '%d glazing bay(s) in %s %s have no WTR leader in this room. WTR-500 is marked TYP elsewhere, which may be intended to cover them, but no leader identifies them.' % (len(ids), rm, rname.get(rm, '')),
              'Confirm whether WTR-500 applies (schedule / designer); site check of window count.', 'Review')
        for b in bays:
            if b['owned'] and 'several' in b['room_how']:
                X('Glazing bay straddles a partition', fn, b['room'], 'WTR-500', b['id'],
                  'Pane %s spans the partition between rooms %s; counted in %s (majority side).' % (b['id'], '/'.join(sorted(b['rooms'])), b['room']),
                  'Confirm how a split bay is treated (one unit per bay or per room side).', 'Review')
            if b['owned'] and b['room'] is None:
                X('Glazing bay not adjacent to a tagged room', fn, '', 'WTR-500?', b['id'],
                  'Pane %s at (%.0f, %.0f) pt opens onto space without a room tag (circulation/unlabelled).' % (b['id'], b['c'][0], b['c'][1]),
                  'Identify the space; include or exclude from window counts.', 'Review')
        out.setdefault('_sheetdata', {})[fn] = dict(asm=asm_id, host=host)
        out.setdefault('_objs', {})[fn] = (S, inst, C, G, bays, bars, res)
    out['exceptions'] = exc
    return out

if __name__ == "__main__":
    o = build()
    print(len(o['rows']), "rows;", len(o['instances']), "instances;", len(o['callouts']), "callouts;", len(o['exceptions']), "exceptions")
    for r in o['rows'][:12]:
        print(r['row_id'], r['room_number'], r['drawing_code'], r['plan_qty'], r['unit'], r['confidence'], r['review_status'], '|', r['target_symbol'])
