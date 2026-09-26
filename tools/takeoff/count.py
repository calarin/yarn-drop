"""Aggregate room x code quantities, instance list and exceptions."""
import json, math
from collections import defaultdict, Counter
from engine import compatible, is_arch, OWN
from takeoff import run

PT_PER_FT = 9.0                     # inferred 1/8" = 1'-0" (not stated on supplied crops)
GRID4_X_EAST = 1104.8 - 1425.9      # grid 4 in east-sheet frame
GRIDB1_Y_EAST = 654.5
def to_floor(sheet, pt):
    x, y = pt
    if sheet == 'west': x, y = x - 1425.9, y + 12.6
    return (round((x - GRID4_X_EAST) / PT_PER_FT, 2), round((GRIDB1_Y_EAST - y) / PT_PER_FT, 2))

SPECIAL_UNITS = {'WTR': 'window bay (glazing pane between mullions)', 'RR': 'wall-mounted item', 'HDF': 'system (assembly)'}

def aggregate():
    sheets = {}
    for fn in ('east', 'west'):
        sheets[fn] = run(fn)
    rows = {}
    claims = defaultdict(set)          # (sheet, instance id) -> codes
    exceptions = []
    for fn, (S, inst, C, G, bays, bars, res) in sheets.items():
        by_id = {i['id']: (k, i) for k, i in enumerate(inst)}
        # pass 1: primary symbol types for unambiguous callouts
        room_tag_code = defaultdict(set)
        for r in res:
            if r['target_kind'] == 'tagged-piece' and not r.get('ambiguous'):
                room_tag_code[(r['room'], r['target_tag'])].add(r['callout']['code'])
        for r in res:
            co = r['callout']
            if r['target_kind'] == 'tagged-piece' and r.get('ambiguous'):
                cands = []
                for c in r['candidates']:
                    iid, tag = c.split(':', 1)
                    cands.append((iid, tag))
                prim = cands[0]
                alts = [c for c in cands[1:] if c[1] != prim[1]]
                claimed_prim = room_tag_code.get((r['room'], prim[1]), set()) - {co['code']}
                free_alts = [a for a in alts if not (room_tag_code.get((r['room'], a[1]), set()) - {co['code']})]
                if claimed_prim and free_alts:
                    k, i = by_id[free_alts[0][0]]
                    r['disambiguation'] = ('endpoint on shared edge of %s and %s; %s in this room is already tagged %s, '
                                           'so %s adopted as the probable target (REVIEW)') % (prim[1], free_alts[0][1], prim[1], sorted(claimed_prim), free_alts[0][1])
                    r['target'] = i['id']; r['target_tag'] = i['tag']; r['target_k'] = k
                    r['resolved_by_rule'] = True
                else:
                    r['disambiguation'] = 'endpoint on shared edge of %s; no rule separates them (UNRESOLVED)' % ' / '.join(sorted(set(c[1] for c in cands)))
                    r['unresolved_alternatives'] = sorted(set(c[1] for c in cands))
        # pass 2: matched instances per callout
        for r in res:
            co = r['callout']
            fam = co['code'].split('-')[0]
            r['matched'] = []
            if r['target_kind'] == 'tagged-piece':
                k0 = r['target_k']; t0 = inst[k0]
                same = [(k, i) for k, i in enumerate(inst) if i['owned'] and i['tag'] == t0['tag'] and i['room'] == r['room']]
                ok, bad = [], []
                for k, i in same:
                    c, why = compatible(t0, i)
                    (ok if c else bad).append((k, why))
                r['matched'] = [inst[k]['id'] for k, _ in ok]
                r['size_excluded'] = [(inst[k]['id'], why) for k, why in bad]
                r['rotated_in_set'] = sum(1 for k, _ in ok if inst[k]['rotated'])
                r['joined_in_set'] = sum(1 for k, _ in ok if inst[k]['joined'])
                r['unit'] = 'each (tagged symbol instance)'
            elif r['target_kind'] == 'window-bay':
                r['matched'] = [b['id'] for b in bays if b['owned'] and b['room'] == r['room']]
                r['straddling'] = [b['id'] for b in bays if b['owned'] and b['room'] == r['room'] and 'several' in b['room_how']]
                r['unit'] = SPECIAL_UNITS['WTR']
            elif r['target_kind'] == 'wall-accessory' and r.get('target'):
                tb = [b for b in bars if b['id'] == r['target']][0]
                r['matched'] = [b['id'] for b in bars if b['owned'] and b['room'] == r['room'] and abs(b['length'] - tb['length']) <= 0.15 * tb['length']]
                r['unit'] = 'each (wall-mounted symbol)'
            elif r['target_kind'] == 'hdf-system':
                sysk = r.get('system_tags', [])
                r['matched'] = sysk if sysk else ['(untagged bank)']
                r['unit'] = SPECIAL_UNITS['HDF']
            for m in r['matched']:
                claims[(fn, m)].add((r['room'], co['code']))
        # aggregate by room x code
        for r in res:
            co = r['callout']
            if r['target_kind'] in ('other-sheet',) or r.get('status') == 'UNRESOLVED':
                key = (fn, r.get('room') or '-', co['code'])
            else:
                key = (fn, r['room'], co['code'])
            row = rows.setdefault(key, dict(sheet=fn, room=key[1], code=co['code'], callouts=[], typ=[], targets=set(), matched=set(),
                                            kinds=set(), notes=[], results=[]))
            row['callouts'].append(co['id']); row['typ'].append(co['typ'] or ''); row['kinds'].add(r['target_kind'])
            if r.get('target_tag'): row['targets'].add(r['target_tag'])
            row['matched'].update(r.get('matched', []))
            row['results'].append(r)
    # conflicts: an instance claimed by two different codes in the same room
    conflicts = {k: v for k, v in claims.items() if len(set(c for _, c in v)) > 1}
    return sheets, rows, conflicts

if __name__ == "__main__":
    sheets, rows, conflicts = aggregate()
    for key in sorted(rows, key=lambda k: (k[0], k[1], k[2])):
        r = rows[key]
        print("%-5s %-5s %-11s qty=%-3d tags=%-22s callouts=%s %s" % (key[0][0].upper(), key[1], key[2], len(r['matched']), sorted(r['targets']), r['callouts'],
              [x.get('disambiguation','') for x in r['results'] if x.get('disambiguation')]))
    print("conflicts:", conflicts)
