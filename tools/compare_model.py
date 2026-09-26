#!/usr/bin/env python3
"""Compare the plan takeoff with a fourth-floor model inventory (review mapping only).

Nothing is written to the model. Outputs are proposals for review:
  * room x code comparison: plan qty, model qty, difference and a status
    (match / model has more / model has fewer / plan only / model only);
  * instance mapping (only when plan->model control points are supplied): each plan
    symbol paired with the nearest model object of the same code, and statuses
    matched / moved / substitution? / plan only / model only / uncertain.

Usage:
    python tools/compare_model.py \
        --plan-rows deliverables/01_room_code_takeoff.csv \
        --plan-instances deliverables/02_instance_list.csv \
        --model deliverables/model_inventory.csv \
        [--control control_points.json --tolerance-ft 2.0] \
        --out-rows deliverables/06_model_comparison.csv --out-instances deliverables/07_instance_mapping.csv

control_points.json: {"pairs": [[[plan_x_ft, plan_y_ft], [model_x_m, model_y_m]], ...]}  (>= 2 pairs; model x/y in metres as
reported by ifc_inventory.py;
plan coordinates are the floor_x_ft / floor_y_ft columns of the instance list, measured from grid 4 / B.1).
"""
import argparse, csv, json, math, sys
from collections import defaultdict

def read_csv(p):
    with open(p, newline='') as f:
        return list(csv.DictReader(f))

def similarity_transform(pairs):
    """Least-squares 2D similarity (scale, rotation, translation) from plan to model."""
    n = len(pairs)
    if n < 2: raise SystemExit('need at least 2 control point pairs')
    px = sum(a[0] for a, _ in pairs) / n; py = sum(a[1] for a, _ in pairs) / n
    mx = sum(b[0] for _, b in pairs) / n; my = sum(b[1] for _, b in pairs) / n
    sxx = sxy = syx = syy = 0.0; norm = 0.0
    for (ax, ay), (bx, by) in pairs:
        ax -= px; ay -= py; bx -= mx; by -= my
        sxx += ax * bx + ay * by
        sxy += ax * by - ay * bx
        norm += ax * ax + ay * ay
    a = sxx / norm; b = sxy / norm
    def f(p):
        x, y = p[0] - px, p[1] - py
        return (a * x - b * y + mx, b * x + a * y + my)
    resid = [math.hypot(*(lambda q, r: (q[0] - r[0], q[1] - r[1]))(f(pp), mm)) for pp, mm in pairs]
    return f, math.hypot(a, b), max(resid) if resid else 0.0

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--plan-rows', required=True)
    ap.add_argument('--plan-instances', required=True)
    ap.add_argument('--model', required=True, help='CSV from tools/ifc_inventory.py')
    ap.add_argument('--control', help='JSON with plan->model control point pairs')
    ap.add_argument('--tolerance-ft', type=float, default=2.0, help='match radius in plan feet')
    ap.add_argument('--out-rows', default='model_comparison.csv')
    ap.add_argument('--out-instances', default='instance_mapping.csv')
    a = ap.parse_args(argv)

    rows = read_csv(a.plan_rows)
    inst = [i for i in read_csv(a.plan_instances) if i.get('row_id')]
    model = read_csv(a.model)

    plan_q = defaultdict(int); plan_rows = defaultdict(list)
    for r in rows:
        try: q = int(r['plan_qty'])
        except (TypeError, ValueError): q = 0
        key = (r['room_number'], r['drawing_code'])
        plan_q[key] += q; plan_rows[key].append(r['row_id'])
    model_q = defaultdict(list); uncoded = []
    for m in model:
        if m.get('code_status') == 'single code' and m.get('code'):
            model_q[(m.get('room_number', ''), m['code'])].append(m['global_id'])
        else:
            uncoded.append(m)
    out = []
    for key in sorted(set(plan_q) | set(model_q)):
        p = plan_q.get(key, 0); mq = len(model_q.get(key, []))
        if key in plan_q and key in model_q:
            st = 'match' if p == mq else ('model has more (addition?)' if mq > p else 'model has fewer (omission?)')
        elif key in plan_q:
            st = 'plan only (omitted in model, or model room/code differs)'
        else:
            st = 'model only (added in model, or plan room/code differs)'
        out.append(dict(room_number=key[0], drawing_code=key[1], plan_qty=p, model_qty=mq, difference=mq - p, status=st,
                        plan_row_ids=', '.join(plan_rows.get(key, [])), model_globalids=', '.join(model_q.get(key, []))))
    for m in uncoded:
        out.append(dict(room_number=m.get('room_number', ''), drawing_code='', plan_qty='', model_qty=1, difference='',
                        status='model object without a single code (%s) - uncertain' % m.get('code_status', ''),
                        plan_row_ids='', model_globalids=m['global_id']))
    with open(a.out_rows, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()) if out else ['room_number']); w.writeheader(); w.writerows(out)
    print('room x code comparison: %d lines -> %s' % (len(out), a.out_rows))

    if not a.control:
        print('no control points given: instance-level mapping skipped (room x code comparison only)')
        return 0
    pairs = json.load(open(a.control))['pairs']
    f, scale, resid = similarity_transform(pairs)
    print('plan->model similarity transform: scale %.4f model units per plan ft, max control residual %.3f' % (scale, resid))
    tol = a.tolerance_ft * scale
    mobj = [m for m in model if m.get('x') not in (None, '') and m.get('y') not in (None, '')]
    used = set(); mapping = []
    for i in sorted(inst, key=lambda i: i['instance_id']):
        try:
            p = f((float(i['floor_x_ft']), float(i['floor_y_ft'])))
        except (TypeError, ValueError):
            continue
        cands = sorted(((math.hypot(float(m['x']) - p[0], float(m['y']) - p[1]), m) for m in mobj if m['global_id'] not in used),
                       key=lambda t: t[0])
        same = [(d, m) for d, m in cands if m.get('code') == i['drawing_code']]
        near_other = [(d, m) for d, m in cands if d <= tol and m.get('code') != i['drawing_code']]
        if same and same[0][0] <= tol:
            d, m = same[0]; used.add(m['global_id'])
            st = 'matched' if m.get('room_number') == i['room_number'] else 'matched by location; model room differs (%s)' % m.get('room_number')
        elif near_other:
            d, m = near_other[0]; used.add(m['global_id'])
            st = 'substitution? model object at this location carries %s' % (m.get('code') or 'no code')
        elif same:
            d, m = same[0]
            st = 'moved? nearest same-code object is %.1f plan ft away' % (d / scale)
        else:
            d, m = None, None; st = 'plan only (no model object of this code)'
        mapping.append(dict(instance_id=i['instance_id'], room_number=i['room_number'], drawing_code=i['drawing_code'],
                            symbol=i['symbol_tag'], plan_x_ft=i['floor_x_ft'], plan_y_ft=i['floor_y_ft'],
                            model_globalid=(m['global_id'] if m else ''), model_name=(m.get('name', '') if m else ''),
                            model_class=(m.get('ifc_class', '') if m else ''), model_room=(m.get('room_number', '') if m else ''),
                            distance_plan_ft=('%.2f' % (d / scale) if d is not None else ''), status=st))
    for m in mobj:
        if m['global_id'] not in used:
            mapping.append(dict(instance_id='', room_number=m.get('room_number', ''), drawing_code=m.get('code', ''), symbol='',
                                plan_x_ft='', plan_y_ft='', model_globalid=m['global_id'], model_name=m.get('name', ''),
                                model_class=m.get('ifc_class', ''), model_room=m.get('room_number', ''), distance_plan_ft='',
                                status='model only (no plan symbol within tolerance)'))
    with open(a.out_instances, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(mapping[0].keys()) if mapping else ['instance_id']); w.writeheader(); w.writerows(mapping)
    print('instance mapping: %d lines -> %s' % (len(mapping), a.out_instances))
    return 0

if __name__ == '__main__':
    sys.exit(main())
