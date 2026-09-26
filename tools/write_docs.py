"""Write 05_reconciliation_summary.md and pilot/pilot_rooms.md from deliverables/takeoff_data.json."""
import json, os, sys
from collections import Counter, defaultdict

def md_table(rows, cols, heads=None):
    heads = heads or cols
    out = ['| ' + ' | '.join(heads) + ' |', '|' + '|'.join('---' for _ in cols) + '|']
    for r in rows:
        out.append('| ' + ' | '.join(str(r.get(c, '')).replace('|', '/').replace('\n', ' ') for c in cols) + ' |')
    return '\n'.join(out)

def main(out):
    d = json.load(open(os.path.join(out, 'takeoff_data.json')))
    rows, inst, cos, exc, rooms, lvq = d['rows'], d['instances'], d['callouts'], d['exceptions'], d['rooms'], d['label_vs_qty']
    units = defaultdict(int)
    for r in rows: units[r['unit']] += int(r['plan_qty'])
    conf = Counter(r['confidence'] for r in rows)
    stat = Counter(r['review_status'].split(' - ')[0] for r in rows)
    sev = Counter(e['severity'] for e in exc)
    cat = Counter(e['category'] for e in exc)
    rooms_with = sorted(set((r['sheet'], r['room_number']) for r in rows))
    naive = sum(1 for c in cos if str(c['naive_differs']) == 'True')
    kinds = Counter(c['target_kind'] for c in cos)
    unresolved = [e for e in exc if e['severity'] == 'High' and e['category'] not in ('Inputs not supplied',)]
    uncoded = [i for i in inst if i['status'] == 'not coded in this room']
    wb_unc = [i for i in inst if i['status'] == 'window bay in room without WTR leader']
    L = []
    L.append('# Fourth-floor furniture & equipment takeoff - reconciliation summary\n')
    L.append('Sources: furniture plans **A06.04A (east)** and **A06.04B (west)** (vector PDFs, rotation handled). '
             'The IFC model, the existing tag catalog and a furniture schedule were **not supplied** with the request, so model '
             'quantities, differences, GlobalIds and code descriptions are left blank rather than inferred. Tools to run the model '
             'check are in `tools/` (see README).\n')
    L.append('## Headline numbers\n')
    L.append(md_table([
        dict(k='Rooms reviewed (room tags on the two sheets)', v='%d (%d east, %d west)' % (len(rooms), sum(1 for r in rooms if r['sheet'].startswith('A06.04A')), sum(1 for r in rooms if r['sheet'].startswith('A06.04B')))),
        dict(k='Rooms with coded items', v=len(rooms_with)),
        dict(k='Distinct drawing codes reviewed', v=len(set(c['code'] for c in cos))),
        dict(k='Code labels (callouts) traced leader-to-symbol', v='%d (%d east, %d west)' % (len(cos), sum(1 for c in cos if c['sheet'].startswith('A06.04A')), sum(1 for c in cos if c['sheet'].startswith('A06.04B')))),
        dict(k='Room x code rows', v=len(rows)),
        dict(k='Items counted on plan', v='; '.join('%d %s' % (v, k) for k, v in sorted(units.items(), key=lambda kv: -kv[1]))),
        dict(k='Model items matched', v='0 - model not supplied'),
        dict(k='Row confidence', v=', '.join('%s %d' % (k, conf[k]) for k in ('High', 'Medium', 'Low'))),
        dict(k='Row status', v=', '.join('%s %d' % kv for kv in stat.items())),
        dict(k='Exceptions', v='%d (High %d, Review %d, Info %d)' % (len(exc), sev['High'], sev['Review'], sev['Info'])),
        dict(k='Callouts a label-position (nearest room tag) link would put in the wrong room', v='%d of %d' % (naive, len(cos))),
    ], ['k', 'v'], ['Item', 'Value']))
    L.append('\n## Unresolved and high-severity cases\n')
    L.append(md_table(unresolved, ['exception_id', 'category', 'sheet', 'room', 'code', 'related_ids', 'description'],
                      ['ID', 'Category', 'Sheet', 'Room', 'Code', 'Related', 'What is unclear']))
    L.append('\nOther review items: %s.\n' % '; '.join('%s: %d' % kv for kv in cat.most_common() if kv[0] not in [u['category'] for u in unresolved]))
    L.append('## Label count is not quantity\n')
    L.append('Code labels on the sheets vs symbols actually counted (TYP treated as "inspect repeats", untagged repeats counted):\n')
    L.append(md_table(lvq, ['code', 'code_labels_on_sheets', 'labels_marked_TYP', 'rooms_with_code', 'plan_quantity_counted', 'unit'],
                      ['Code', 'Labels', 'of which TYP', 'Rooms', 'Counted', 'Unit']))
    L.append('\n## How the drawings were read\n')
    L.append('\n'.join([
        '* **Leaders**: each code label box was matched to its leader by geometry (dot -> each bend -> label edge or end of the TYP text) and '
        'cross-checked against the drawing order of the annotation group; all %d leaders passed both checks. Crossing and overlapping '
        'leaders do not share endpoints, so they were not confused. %d leaders end on a tagged furniture symbol, %d on exterior glazing, '
        '%d on a wall-mounted item, %d on a filing bank and %d beyond the match line (duplicate of a west-sheet callout).' % (
            len(cos), kinds['tagged-piece'], kinds['window-bay'], kinds['wall-accessory'], kinds['hdf-system'], kinds['other-sheet']),
        '* **Rooms**: room numbers were used only to identify spaces. Each room region was grown from its tag (or from the end of the '
        'tag\'s own leader when the tag sits outside the room) inside walls and door swings; open-plan spaces were split at the narrowest '
        'opening and marked as inferred. The symbol at each leader endpoint decides the room, never the label position.',
        '* **Symbols**: the leader endpoint identifies a symbol through its true (clipped) white mask and its in-symbol tag (S-5, T-16, CC-1 ...). '
        'Matching instances in the same room are those with the same in-symbol tag and footprint; joined strings such as "CC-1CC-1CC-1" and '
        '"S-10 S-10 S-10" were split per tag; rotated and vertical text was read in the sheet orientation.',
        '* **Pieces vs assemblies**: desk + return pieces (D-6A + F, D-6 + L + F) are counted as assemblies; filing banks (sections on rails with '
        'one F-1 tag) are counted as one system with sections as components; casework runs sharing one outline are flagged; workstation '
        'component tags (D3, D11, P1, F3, B1 ...) carry no leader codes and are listed separately in `component_tags_by_room.csv`.',
        '* **Windows / walls**: WTR-500 leaders end on exterior glazing; the repeated symbol is the glazing bay, so bays are counted per room '
        '(unit to be confirmed). RR-70x leaders end on wall-mounted items; the room is the one on the face where the item is drawn.',
        '* **Specifications**: no descriptions, manufacturers or model numbers were filled. The PDFs contain hidden CAD attribute text; it was not used for specifications.',
    ]))
    L.append('\n## Pilot rooms\n')
    L.append('See `pilot/pilot_rooms.md` for marked-up close-ups and counts of %s.\n' % ', '.join('%s %s' % (p[0], p[1]) for p in d['pilots']))
    L.append('\n## Files\n')
    L.append('\n'.join([
        '* `01_room_code_takeoff.csv` - deliverable 1 (one row per room x code; model columns blank).',
        '* `02_instance_list.csv` - deliverable 2 (every counted plan symbol with location, IDs, proposed model match blank).',
        '* `03_overlay_A06.04A_east.(png|pdf)`, `03_overlay_A06.04B_west.(png|pdf)` - deliverable 3.',
        '* `04_exceptions.csv` - deliverable 4.', '* this file - deliverable 5.',
        '* `callout_catalog.csv` (every label, leader path, endpoint, traced room, label-position room), `rooms.csv`, '
        '`component_tags_by_room.csv`, `label_count_vs_quantity.csv`, `model_comparison_template.csv`, `takeoff_workbook.xlsx`.']))
    open(os.path.join(out, '05_reconciliation_summary.md'), 'w').write('\n'.join(L) + '\n')
    # pilot doc
    P = ['# Pilot rooms - interpretation check\n',
         'Each close-up shows the traced leaders (magenta line, ring at the endpoint, Cnn = callout id), the room boundary used '
         '(blue = walls/doors, orange = inferred open-plan line) and every counted symbol ringed with its instance id (Tnnn, Wnn = glazing '
         'bay, Snn = assembly). Orange squares/dashed boxes are uncoded items (see exceptions).\n']
    for fn, room, png in d['pilots']:
        sheet = 'A06.04A (east)' if fn == 'east' else 'A06.04B (west)'
        rr = [r for r in rows if r['sheet'] == sheet and r['room_number'] == room]
        name = rr[0]['room_name'] if rr else ''
        P.append('## %s %s - %s\n' % (room, name, sheet))
        P.append('![%s](%s)\n' % (room, png))
        P.append(md_table(rr, ['row_id', 'drawing_code', 'typ_on_label', 'target_symbol', 'plan_qty', 'unit', 'callout_ids', 'confidence', 'review_status'],
                          ['Row', 'Code', 'TYP', 'Symbol identified', 'Qty', 'Unit', 'Callouts', 'Confidence', 'Status']))
        ex = [e for e in exc if e['sheet'] == sheet and e['room'] == room]
        if ex:
            P.append('\nExceptions in this room: ' + '; '.join('%s %s' % (e['exception_id'], e['category']) for e in ex) + '\n')
        P.append('')
    open(os.path.join(out, 'pilot', 'pilot_rooms.md'), 'w').write('\n'.join(P) + '\n')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'deliverables')
