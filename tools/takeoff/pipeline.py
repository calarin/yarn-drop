"""Run the plan takeoff end to end in a work directory.

Stages (all read-only with respect to the source PDFs):
  1 text spans (display coordinates; PDF rotation applied)          -> {sheet}_spans.json
  2 vector primitives                                               -> {sheet}_prims.json
  3 label boxes, leader tracing (dot -> bends -> label), room tags   -> traces.json
  4 non-antialiased raster for wall/door barriers                   -> {sheet}_gray_z3.npy
  5 room regions (walls + doors, gap closing, open-plan split)      -> {sheet}_rooms.npy
  6 clipped white-mask polygons (true symbol footprints)            -> {sheet}_masks.json
  7 in-symbol tags split per tag (joined strings, rotated text)     -> {sheet}_tags.json
"""
import json, os, shutil
import numpy as np

SHEETS = ('east', 'west')

def prepare(work, east_pdf, west_pdf):
    os.makedirs(work, exist_ok=True)
    shutil.copyfile(east_pdf, os.path.join(work, 'east.pdf'))
    shutil.copyfile(west_pdf, os.path.join(work, 'west.pdf'))

def run_stages(work, log=print):
    cwd = os.getcwd(); os.chdir(work)
    try:
        import pymupdf as fitz
        import extract, callouts, trace2, rooms_final, masks, labels
        for fn in SHEETS:
            json.dump(extract.spans(f"{fn}.pdf"), open(f"{fn}_spans.json", "w"))
            json.dump(callouts.load_prims(f"{fn}.pdf"), open(f"{fn}_prims.json", "w"))
        log('1-2 text and vector primitives extracted')
        trace2.run_traces(verbose=False)
        log('3 leaders traced')
        fitz.TOOLS.set_aa_level(0)
        for fn in SHEETS:
            p = fitz.open(f"{fn}.pdf")[0]
            pix = p.get_pixmap(matrix=fitz.Matrix(3, 3), colorspace=fitz.csGRAY, alpha=False)
            np.save(f"{fn}_gray_z3.npy", np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width))
        fitz.TOOLS.set_aa_level(8)
        log('4 barrier rasters rendered')
        for fn in SHEETS:
            a, out, rooms, seeds, method = rooms_final.final_rooms(fn)
            np.save(f"{fn}_rooms.npy", out)
            json.dump(method, open(f"{fn}_room_method.json", "w"), indent=1)
        log('5 room regions segmented')
        for fn in SHEETS:
            json.dump(masks.extract_masks(fn), open(f"{fn}_masks.json", "w"))
            json.dump(labels.extract(fn), open(f"{fn}_tags.json", "w"))
        log('6-7 masks and in-symbol tags extracted')
    finally:
        os.chdir(cwd)
