"""Smoke test for the model tools on a synthetic IFC built in a temp directory (no real model data)."""
import csv, json, os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

def build_model(path):
    import ifcopenshell, ifcopenshell.api
    m = ifcopenshell.api.run('project.create_file', version='IFC4')
    proj = ifcopenshell.api.run('root.create_entity', m, ifc_class='IfcProject', name='Test')
    ifcopenshell.api.run('unit.assign_unit', m)
    ctx = ifcopenshell.api.run('context.add_context', m, context_type='Model')
    site = ifcopenshell.api.run('root.create_entity', m, ifc_class='IfcSite', name='Site')
    bld = ifcopenshell.api.run('root.create_entity', m, ifc_class='IfcBuilding', name='B')
    l3 = ifcopenshell.api.run('root.create_entity', m, ifc_class='IfcBuildingStorey', name='Level 3')
    l4 = ifcopenshell.api.run('root.create_entity', m, ifc_class='IfcBuildingStorey', name='Level 4')
    ifcopenshell.api.run('aggregate.assign_object', m, products=[site], relating_object=proj)
    ifcopenshell.api.run('aggregate.assign_object', m, products=[bld], relating_object=site)
    ifcopenshell.api.run('aggregate.assign_object', m, products=[l3, l4], relating_object=bld)
    sp = ifcopenshell.api.run('root.create_entity', m, ifc_class='IfcSpace', name='453')
    sp.LongName = 'PROMOTION & MARKETING'
    ifcopenshell.api.run('aggregate.assign_object', m, products=[sp], relating_object=l4)
    import numpy as np
    def furn(name, code, xy, container):
        e = ifcopenshell.api.run('root.create_entity', m, ifc_class='IfcFurniture', name=name)
        mat = np.eye(4); mat[0][3], mat[1][3] = xy
        ifcopenshell.api.run('geometry.edit_object_placement', m, product=e, matrix=mat)
        ifcopenshell.api.run('spatial.assign_container', m, products=[e], relating_structure=container)
        if code:
            ps = ifcopenshell.api.run('pset.add_pset', m, product=e, name='Pset_Test')
            ifcopenshell.api.run('pset.edit_pset', m, pset=ps, properties={'Mark': code})
        return e
    furn('Chair A', 'MFN-400', (1.0, 1.0), sp)
    furn('Chair B', 'MFN-400', (3.0, 1.0), sp)
    furn('Side chair', 'MFN-402', (5.0, 1.0), sp)
    furn('Unknown', None, (7.0, 1.0), l4)
    furn('Other floor chair', 'MFN-400', (1.0, 1.0), l3)
    m.write(path)

def test_inventory_and_compare():
    import ifc_inventory, compare_model
    with tempfile.TemporaryDirectory() as td:
        ifc = os.path.join(td, 't.ifc'); build_model(ifc)
        before = open(ifc, 'rb').read()
        inv = os.path.join(td, 'inv.csv')
        assert ifc_inventory.main([ifc, '--storey', 'Level 4', '-o', inv]) == 0
        assert open(ifc, 'rb').read() == before, 'model must not be modified'
        rows = list(csv.DictReader(open(inv)))
        assert len(rows) == 4, rows
        codes = sorted(r['code'] for r in rows)
        assert codes == ['', 'MFN-400', 'MFN-400', 'MFN-402'], codes
        assert all(r['global_id'] for r in rows)
        assert sum(1 for r in rows if r['room_number'] == '453') == 3
        # plan side: 2 x MFN-400 and 2 x MFN-402 in 453
        pr = os.path.join(td, 'rows.csv'); pi = os.path.join(td, 'inst.csv')
        with open(pr, 'w', newline='') as f:
            w = csv.writer(f); w.writerow(['row_id', 'room_number', 'drawing_code', 'plan_qty'])
            w.writerow(['R1', '453', 'MFN-400', 2]); w.writerow(['R2', '453', 'MFN-402', 2])
        with open(pi, 'w', newline='') as f:
            w = csv.writer(f); w.writerow(['instance_id', 'row_id', 'room_number', 'drawing_code', 'symbol_tag', 'floor_x_ft', 'floor_y_ft'])
            w.writerow(['E-T1', 'R1', '453', 'MFN-400', 'S-5', 1.0, 1.0]); w.writerow(['E-T2', 'R1', '453', 'MFN-400', 'S-5', 3.0, 1.0])
            w.writerow(['E-T3', 'R2', '453', 'MFN-402', 'S-9', 5.0, 1.0]); w.writerow(['E-T4', 'R2', '453', 'MFN-402', 'S-9', 9.0, 1.0])
        ctrl = os.path.join(td, 'c.json'); json.dump({'pairs': [[[0, 0], [0, 0]], [[10, 0], [10, 0]]]}, open(ctrl, 'w'))
        oc = os.path.join(td, 'cmp.csv'); oi = os.path.join(td, 'map.csv')
        assert compare_model.main(['--plan-rows', pr, '--plan-instances', pi, '--model', inv, '--control', ctrl,
                                   '--tolerance-ft', '0.5', '--out-rows', oc, '--out-instances', oi]) == 0
        cmp_ = {(r['room_number'], r['drawing_code']): r for r in csv.DictReader(open(oc))}
        assert cmp_[('453', 'MFN-400')]['status'] == 'match'
        assert cmp_[('453', 'MFN-402')]['difference'] == '-1'
        mp = list(csv.DictReader(open(oi)))
        st = {r['instance_id']: r['status'] for r in mp if r['instance_id']}
        assert st['E-T1'] == 'matched' and st['E-T2'] == 'matched' and st['E-T3'] == 'matched'
        assert st['E-T4'].startswith('moved?') or st['E-T4'].startswith('plan only')
        assert any(r['status'].startswith('model only') for r in mp)

if __name__ == '__main__':
    test_inventory_and_compare(); print('ok')
