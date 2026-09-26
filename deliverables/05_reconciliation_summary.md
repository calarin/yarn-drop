# Fourth-floor furniture & equipment takeoff - reconciliation summary

Sources: furniture plans **A06.04A (east)** and **A06.04B (west)** (vector PDFs, rotation handled). The IFC model, the existing tag catalog and a furniture schedule were **not supplied** with the request, so model quantities, differences, GlobalIds and code descriptions are left blank rather than inferred. Tools to run the model check are in `tools/` (see README).

## Headline numbers

| Item | Value |
|---|---|
| Rooms reviewed (room tags on the two sheets) | 59 (39 east, 20 west) |
| Rooms with coded items | 41 |
| Distinct drawing codes reviewed | 42 |
| Code labels (callouts) traced leader-to-symbol | 128 (79 east, 49 west) |
| Room x code rows | 124 |
| Items counted on plan | 245 each; 105 glazing bay; 6 assembly; 5 system (assembly) |
| Model items matched | 0 - model not supplied |
| Row confidence | High 88, Medium 34, Low 2 |
| Row status | Plan count checked; awaiting model comparison 88, REVIEW 35, UNRESOLVED 1 |
| Exceptions | 75 (High 3, Review 44, Info 28) |
| Callouts a label-position (nearest room tag) link would put in the wrong room | 71 of 128 |

## Unresolved and high-severity cases

| ID | Category | Sheet | Room | Code | Related | What is unclear |
|---|---|---|---|---|---|---|
| X002 | Leader endpoint on shared edge (probable target adopted) | A06.04A (east) | 427 | MFN-312 | E-C54 | Endpoint lies on the shared edge of S-10 and T-1. S-10 in this room is already tagged MFN-415, so T-1 is adopted as the probable target. |
| X003 | Unresolved leader endpoint | A06.04B (west) | 433A | MFN-325 | W-C40 -> W-T071, W-T072 | Endpoint lies on the shared edge of O-1 and O-3; no drawing evidence separates them. Quantity reported as 1 (one piece under the dot) with the target unconfirmed. |

Other review items: Untagged item (no in-symbol tag, no code): 20; Room boundary inferred (open plan / no door): 14; Code label without TYP; repeated symbols counted: 11; Glazing bay straddles a partition: 6; Same in-symbol tag carries different codes: 6; Window bays without WTR-500 leader in room: 4; Glazing bay not adjacent to a tagged room: 2; Tagged symbol with no leader code in room: 2; Inputs not supplied: 1; Curved facade glazing not counted: 1; Room tag leader ends at a wall: 1; Drawing scale inferred: 1; Duplicate callout across match line: 1; Hidden CAD attribute text in PDF: 1; Non-furniture tag: 1; Revision cloud / delta tags: 1.

## Label count is not quantity

Code labels on the sheets vs symbols actually counted (TYP treated as "inspect repeats", untagged repeats counted):

| Code | Labels | of which TYP | Rooms | Counted | Unit |
|---|---|---|---|---|---|
| AUD-300.1LF | 1 | 0 | 1 | 1 | assembly |
| AUD-300.2R | 5 | 0 | 5 | 5 | assembly |
| AUD-320 | 1 | 0 | 1 | 2 | each |
| AUD-321 | 1 | 0 | 1 | 1 | each |
| AUD-400 | 5 | 0 | 5 | 5 | each |
| CC-900 | 5 | 2 | 5 | 21 | each |
| CRM-301.3 | 1 | 0 | 1 | 1 | each |
| CRM-325 | 1 | 0 | 1 | 2 | each |
| CRM-400 | 1 | 1 | 1 | 6 | each |
| DIN-301 | 1 | 1 | 1 | 4 | each |
| DIN-400 | 1 | 1 | 1 | 24 | each |
| EQP-900 | 2 | 0 | 2 | 2 | each |
| HDF-900 | 5 | 0 | 5 | 5 | system (assembly) |
| MFN-301 | 1 | 1 | 1 | 12 | each |
| MFN-305 | 2 | 1 | 2 | 3 | each |
| MFN-306 | 1 | 0 | 1 | 1 | each |
| MFN-307 | 1 | 0 | 1 | 1 | each |
| MFN-312 | 1 | 0 | 1 | 2 | each |
| MFN-313 | 1 | 0 | 1 | 2 | each |
| MFN-314 | 1 | 0 | 1 | 1 | each |
| MFN-315 | 1 | 0 | 1 | 1 | each |
| MFN-316 | 1 | 0 | 1 | 2 | each |
| MFN-317 | 1 | 0 | 1 | 1 | each |
| MFN-320 | 1 | 1 | 1 | 8 | each |
| MFN-323 | 2 | 1 | 2 | 4 | each |
| MFN-325 | 1 | 0 | 1 | 1 | each |
| MFN-326 | 1 | 0 | 1 | 1 | each |
| MFN-400 | 34 | 16 | 31 | 71 | each |
| MFN-401 | 4 | 3 | 4 | 8 | each |
| MFN-402 | 8 | 5 | 8 | 13 | each |
| MFN-405 | 1 | 1 | 1 | 2 | each |
| MFN-410 | 1 | 1 | 1 | 4 | each |
| MFN-412 | 1 | 0 | 1 | 1 | each |
| MFN-414 | 1 | 1 | 1 | 8 | each |
| MFN-415 | 2 | 0 | 1 | 20 | each |
| MFN-416 | 1 | 0 | 1 | 2 | each |
| MFN-417 | 1 | 0 | 1 | 1 | each |
| MFN-900 | 1 | 0 | 1 | 1 | each |
| RR-700 | 1 | 0 | 1 | 1 | each |
| RR-701 | 1 | 0 | 1 | 1 | each |
| RR-702 | 4 | 0 | 4 | 4 | each |
| WTR-500 | 21 | 21 | 21 | 105 | glazing bay |

## How the drawings were read

* **Leaders**: each code label box was matched to its leader by geometry (dot -> each bend -> label edge or end of the TYP text) and cross-checked against the drawing order of the annotation group; all 128 leaders passed both checks. Crossing and overlapping leaders do not share endpoints, so they were not confused. 95 leaders end on a tagged furniture symbol, 21 on exterior glazing, 6 on a wall-mounted item, 5 on a filing bank and 1 beyond the match line (duplicate of a west-sheet callout).
* **Rooms**: room numbers were used only to identify spaces. Each room region was grown from its tag (or from the end of the tag's own leader when the tag sits outside the room) inside walls and door swings; open-plan spaces were split at the narrowest opening and marked as inferred. The symbol at each leader endpoint decides the room, never the label position.
* **Symbols**: the leader endpoint identifies a symbol through its true (clipped) white mask and its in-symbol tag (S-5, T-16, CC-1 ...). Matching instances in the same room are those with the same in-symbol tag and footprint; joined strings such as "CC-1CC-1CC-1" and "S-10 S-10 S-10" were split per tag; rotated and vertical text was read in the sheet orientation.
* **Pieces vs assemblies**: desk + return pieces (D-6A + F, D-6 + L + F) are counted as assemblies; filing banks (sections on rails with one F-1 tag) are counted as one system with sections as components; casework runs sharing one outline are flagged; workstation component tags (D3, D11, P1, F3, B1 ...) carry no leader codes and are listed separately in `component_tags_by_room.csv`.
* **Windows / walls**: WTR-500 leaders end on exterior glazing; the repeated symbol is the glazing bay, so bays are counted per room (unit to be confirmed). RR-70x leaders end on wall-mounted items; the room is the one on the face where the item is drawn.
* **Specifications**: no descriptions, manufacturers or model numbers were filled. The PDFs contain hidden CAD attribute text; it was not used for specifications.

## Pilot rooms

See `pilot/pilot_rooms.md` for marked-up close-ups and counts of east 453, east 427, east 412, east 431, west 443, west 451.


## Files

* `01_room_code_takeoff.csv` - deliverable 1 (one row per room x code; model columns blank).
* `02_instance_list.csv` - deliverable 2 (every counted plan symbol with location, IDs, proposed model match blank).
* `03_overlay_A06.04A_east.(png|pdf)`, `03_overlay_A06.04B_west.(png|pdf)` - deliverable 3.
* `04_exceptions.csv` - deliverable 4.
* this file - deliverable 5.
* `callout_catalog.csv` (every label, leader path, endpoint, traced room, label-position room), `rooms.csv`, `component_tags_by_room.csv`, `label_count_vs_quantity.csv`, `model_comparison_template.csv`, `takeoff_workbook.xlsx`.
