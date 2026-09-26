# Fourth-floor furniture & equipment takeoff (A06.04A / A06.04B)

Branch `temp-plans` is an orphan branch: it shares no history with the yarn tooling on `main`.

This is a **plan takeoff with a reviewable model mapping prepared but not yet run**. The two furniture plans
were supplied. The fourth-floor model, the existing tag catalog and a furniture schedule were not, so every
model column is blank rather than guessed. `tools/` contains the read-only IFC inventory and comparison
scripts to finish the check when the model is available. No IFC Psets or model data were changed.

## Deliverables (`deliverables/`)

| # | File | Content |
|---|---|---|
| 1 | `01_room_code_takeoff.csv` | One row per room x drawing code: room, code, description (*not supplied - no schedule*), item class, unit, plan quantity, model quantity / difference (blank - model not supplied), source sheet, callout ids, TYP, symbol identified, counted instance ids, evidence, confidence, review status |
| 2 | `02_instance_list.csv` | Every plan symbol found (664): id, room, code, row, in-symbol tag, sheet position (pt) and approximate floor position (ft from grid 4 / B.1), rotation, footprint, assembly id, status, proposed model match (blank) |
| 3 | `03_overlay_A06.04A_east.(png, pdf)`, `03_overlay_A06.04B_west.(png, pdf)` | Review overlays: traced leaders and endpoint rings (`Cnn`), room boundaries used (blue = walls/doors, orange `*` = inferred open-plan line), every counted symbol ringed with its id (`Tnnn`, glazing bays `Wnn`, wall items `Ann`, assemblies `Snn`), uncoded items and exceptions (orange, `Xnnn`) |
| 4 | `04_exceptions.csv` | 75 exceptions with severity, related ids, description, recommended action and site/photo-check flag |
| 5 | `05_reconciliation_summary.md` | Rooms and codes reviewed, items counted, model items matched, unresolved cases, label count vs quantity |
| - | `pilot/pilot_rooms.md` | Close-ups and counts for pilot rooms 453, 427, 412, 431 (east) and 443, 451 (west) |
| - | `callout_catalog.csv` | All 128 code labels: TYP, label box, leader path through each bend, endpoint, symbol, traced room, and the room a label-position link would give |
| - | `rooms.csv`, `component_tags_by_room.csv`, `label_count_vs_quantity.csv`, `model_comparison_template.csv`, `takeoff_workbook.xlsx` | Supporting tables (the workbook holds all tables) |

## Results in brief

* 59 room tags reviewed (39 east, 20 west); 41 rooms carry coded items; 42 distinct codes; 128 code labels traced.
* Counted on plan: **245 individual pieces, 6 desk assemblies, 5 filing systems, 105 glazing bays** (WTR-500) in 124 room x code rows.
* Row confidence: High 88, Medium 34, Low 2. One row is unresolved (MFN-325, 433A) and one uses a probable target adopted by rule (MFN-312, 427).
* Label count is not quantity: e.g. MFN-400 has 34 labels but 71 chairs; DIN-400 has 1 label but 24 chairs; WTR-500 has 21 labels but 105 bays.
* 71 of 128 labels sit nearer another room's tag than the room of the symbol they point to, so label-position room links would be wrong for them.
* Model items matched: 0 (model not supplied).

## How the drawings were read

1. **Text and geometry** are taken from the vector PDFs in sheet orientation (the west sheet is rotated 90 degrees), including vertical and rotated text.
2. **Leaders**: each code box is followed dot -> every bend -> label edge (or the end of its TYP text). Each trace is checked against the drawing order of its annotation group; crossing leaders never share endpoints. All 128 passed.
3. **Rooms**: room numbers only identify spaces. Regions are grown from each tag inside walls and door swings. Where a tag sits outside its room, the tag's own leader endpoint is used. Open-plan spaces are split at the narrowest opening and marked as inferred. The symbol at the leader endpoint decides the room.
4. **Symbols**: the endpoint picks a symbol by its true (clipped) white mask and in-symbol tag. Instances are matched in the same room by in-symbol tag and footprint, with untagged repeats counted. TYP means "inspect repeats", not a quantity. Joined strings (`CC-1CC-1CC-1`, `S-10 S-10 S-10`) are split per tag.
5. **Pieces vs assemblies**: desk + returns (D-6A+F, D-6+L+F) count as assemblies. Filing banks (sections on rails, one F-1 tag) count as one system. Casework runs sharing one outline are flagged. Workstation component tags (D3, D11, P1, F3, B1 ...) have no leader codes and are listed separately.
6. **Walls and windows**: WTR-500 leaders end on exterior glazing, so glazing bays are counted (unit to confirm). RR-70x leaders end on wall-mounted items, and the room is the face they are drawn on.
7. **Match line**: symbols beyond a sheet's match line are counted on the other sheet. One duplicate callout (E-C57 = W-C35) was found; the overlap strip matches to 0.13 pt.
8. **Specifications**: no descriptions, manufacturers or model numbers were filled. Hidden CAD attribute text in the PDFs was not used for them.

## Re-running

```bash
pip install -r requirements.txt
python tools/run_takeoff.py --east inputs/4th_east.pdf --west inputs/4th_west.pdf --out deliverables
```

## Model check (when the IFC is available)

```bash
python tools/ifc_inventory.py model.ifc --list-storeys
python tools/ifc_inventory.py model.ifc --storey "<fourth floor storey name>" [--space-geometry] -o deliverables/model_inventory.csv
python tools/compare_model.py --plan-rows deliverables/01_room_code_takeoff.csv \
    --plan-instances deliverables/02_instance_list.csv --model deliverables/model_inventory.csv \
    [--control control_points.json --tolerance-ft 2] \
    --out-rows deliverables/06_model_comparison.csv --out-instances deliverables/07_instance_mapping.csv
```

`ifc_inventory.py` lists fourth-floor objects: GlobalId, class, name, type, spatial container / room, location in metres, and code-like Pset values (read only). `compare_model.py` reports room x code differences (match / model has more / model has fewer / plan only / model only). With control points (plan feet from grid 4 / B.1 to model metres, e.g. grid intersections) it also pairs instances as matched, moved, substitution, plan only or model only. The outputs are proposals for review. `python tools/tests/test_model_tools.py` checks both tools on a synthetic model and asserts the IFC file is unchanged.

## Limitations

* Drawing scale is not shown on the crops; 1/8" = 1'-0" (9 pt/ft) is inferred from standard object sizes and used only for approximate floor coordinates.
* Glazing-bay and filing-system units are counting bases, not confirmed purchase units.
* Items shown with gray diagonal hatching, counters and thin wall strips have no tags or codes; they are listed as exceptions for identification.
