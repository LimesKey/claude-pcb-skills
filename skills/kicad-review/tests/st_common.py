"""Shared by selftest.py and its st_*.py case files: fixture paths, run(), check(), CASES,
and the fixture builders more than one case file uses."""

import os, sys, json, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SK   = os.path.dirname(HERE)                       # skill root
S    = os.path.join(SK, 'scripts')
NET  = os.path.join(HERE, 'selftest.net')
PCB  = os.path.join(HERE, 'selftest.kicad_pcb')
PCB2 = os.path.join(HERE, 'selftest_amp2.kicad_pcb')
PCB3 = os.path.join(HERE, 'selftest_nightly.kicad_pcb')   # PCB in 10.99 (transform) form
CROSS = os.path.join(HERE, 'selftest_cross.kicad_pcb')     # two N tracks crossing mid-span
REPEAT = os.path.join(HERE, 'selftest_repeat', 'repeat.net')  # sub.kicad_sch used as sheets A and B
KSCH = os.path.join(HERE, 'selftest.ksch')
TMP  = tempfile.gettempdir()
svg1 = os.path.join(TMP, 'selftest_draw.svg')
svg2 = os.path.join(TMP, 'selftest_ksch.svg')
sys.path.insert(0, S)                   # the in-process checks import the scripts

class Cases(list):
    """(label, [tool, *args], expected_exit, [needles]) per case, each st_*.py suite()
    appending its own; append() notes the file:line that wrote each one, for `--list`."""
    where = {}
    def append(self, c):
        f = sys._getframe(1)
        self.where[c[0]] = f'{os.path.basename(f.f_code.co_filename)}:{f.f_lineno}'
        super().append(c)

CASES = Cases()
VERBOSE = False                 # selftest.py -v: print the passing checks too

def mini_project(d):
    """A throwaway project for what the fixtures above cannot carry: a no_connect
    marker at the END of a wire stub (not on the pin), a .kicad_sch saved after
    the .net, and a .kicad_pro naming a top-level sheet the .net lacks."""
    open(os.path.join(d, 't.kicad_pro'), 'w').write(
        '{"schematic": {"top_level_sheets": [{"filename": "t.kicad_sch", "name": "Root"},'
        ' {"filename": "other.kicad_sch", "name": "Other"}]}}')
    open(os.path.join(d, 't.net'), 'w').write(
        '(export (version "E") (design (source "t.kicad_sch") (sheet (number "1") (name "/Root/")))'
        ' (components (comp (ref "U1") (value "X") (libsource (lib "x") (part "y"))'
        ' (sheetpath (names "/Root/")))'
        ' (comp (ref "D1") (value "BAV199") (footprint "Package_TO_SOT_SMD:SOT-23")'
        ' (libsource (lib "Device") (part "D_Dual_Series_ACK")) (sheetpath (names "/Root/")))'
        ' (comp (ref "BT1") (value "cell") (libsource (lib "Device") (part "Battery_Cell")))'
        ' (comp (ref "D2") (value "SMF10A") (libsource (lib "Diode") (part "SMF10A")))'
        ' (comp (ref "R1") (value "10") (libsource (lib "Device") (part "R")))'
        ' (comp (ref "U2") (value "MAX1") (libsource (lib "x") (part "ic")))'
        ' (comp (ref "U3") (value "QFN") (footprint "t:QFN") (libsource (lib "x") (part "q"))))'
        ' (libparts (libpart (lib "x") (part "y") (pins (pin (num "1") (name "A") (type "passive"))'
        ' (pin (num "2") (name "B") (type "passive"))))'
        ' (libpart (lib "Device") (part "D_Dual_Series_ACK") (pins (pin (num "1") (name "A") (type "passive"))'
        ' (pin (num "2") (name "common") (type "passive")) (pin (num "3") (name "K") (type "passive"))))'
        ' (libpart (lib "Device") (part "Battery_Cell") (pins (pin (num "1") (name "+") (type "passive"))'
        ' (pin (num "2") (name "-") (type "passive"))))'
        ' (libpart (lib "Diode") (part "SMF10A") (pins (pin (num "1") (name "A1") (type "passive"))'
        ' (pin (num "2") (name "A2") (type "passive"))))'
        ' (libpart (lib "Device") (part "R") (pins (pin (num "1") (name "~") (type "passive"))'
        ' (pin (num "2") (name "~") (type "passive"))))'
        ' (libpart (lib "x") (part "ic") (pins (pin (num "1") (name "IN") (type "input"))'
        ' (pin (num "2") (name "GND") (type "power_in"))))'
        ' (libpart (lib "x") (part "q") (pins (pin (num "1") (name "A") (type "passive"))'
        ' (pin (num "3") (name "VIN") (type "power_in")) (pin (num "4") (name "VIN") (type "power_in"))'
        ' (pin (num "6") (name "X") (type "passive")))))'
        ' (nets (net (code "1") (name "unconnected-(U1-A-Pad1)") (node (ref "U1") (pin "1")))'
        ' (net (code "2") (name "unconnected-(U1-B-Pad2)") (node (ref "U1") (pin "2")))'
        ' (net (code "3") (name "VP") (node (ref "BT1") (pin "1")) (node (ref "D2") (pin "1"))'
        ' (node (ref "R1") (pin "1")))'
        ' (net (code "4") (name "GND") (node (ref "BT1") (pin "2")) (node (ref "D2") (pin "2"))'
        ' (node (ref "U2") (pin "2")))'
        ' (net (code "5") (name "Net-(R1-Pad2)") (node (ref "R1") (pin "2")) (node (ref "U2") (pin "1")))'
        ' (net (code "6") (name "N1") (node (ref "U3") (pin "1")))'
        ' (net (code "7") (name "VIN") (node (ref "U3") (pin "3")))'
        ' (net (code "8") (name "NX") (node (ref "U3") (pin "6")))))')
    # footprint library for U3: pad 3 spans pins 3-4 (fused), pad 5 is an EP the
    # symbol has no pin for, MP is a mounting pad, and pin 6 has no pad at all
    open(os.path.join(d, 'fp-lib-table'), 'w').write(
        '(fp_lib_table (lib (name "t") (type "KiCad") (uri "${KIPRJMOD}/t.pretty")))')
    os.makedirs(os.path.join(d, 't.pretty'))
    open(os.path.join(d, 't.pretty', 'QFN.kicad_mod'), 'w').write(
        '(footprint "QFN" ' + ' '.join(f'(pad "{n}" smd rect (at 0 0) (size 1 1) (layers "F.Cu"))'
                                       for n in ('1', '3', '5', 'MP'))
        + ' (pad "" np_thru_hole circle (at 0 0) (size 1 1) (drill 1)))')
    # RF nets: ANT has a series R, a shunt C, a bias-tee choke L1 (far end
    # bypassed by C2) and the IC = 3 series parts, a stub. VCC_RF is a DC line
    # named like RF: not flagged, the project has an RF netclass.
    def comp(r, v, lib='Device', part='R'):
        return f' (comp (ref "{r}") (value "{v}") (libsource (lib "{lib}") (part "{part}")))'
    def net(code, name, cls, *nodes):
        return (f' (net (code "{code}") (name "{name}") (class "{cls}")'
                + ''.join(f' (node (ref "{r}") (pin "{p}"))' for r, p in nodes) + ')')
    open(os.path.join(d, 'rf.net'), 'w').write(
        '(export (version "E") (design (source "t.kicad_sch"))'
        ' (components' + comp('J1', 'SMA') + comp('R1', '0') + comp('C1', '1p', part='C')
        + comp('L1', '27n', part='L') + comp('C2', '100n', part='C') + comp('U1', 'LNA', 'x', 'ic')
        + comp('R2', '10') + comp('R3', '10') + comp('J2', 'SMA') + comp('FL1', 'LPF', part='Filter')
        + comp('JP1', 'BYPASS', part='Jumper')[:-1] + ' (dnp))' + comp('U2', 'PA', 'x', 'ic') + ')'
        ' (libparts (libpart (lib "x") (part "ic") (pins (pin (num "1") (name "IN") (type "input"))'
        ' (pin (num "2") (name "GND") (type "power_in")))))'
        ' (nets' + net(1, 'ANT', 'RF_50OHM', ('J1', '1'), ('R1', '1'), ('C1', '1'), ('L1', '1'), ('U1', '1'))
        + net(2, 'GND', 'Default', ('C1', '2'), ('C2', '2'), ('U1', '2'), ('J1', '2'))
        + net(3, 'VB', 'Default', ('L1', '2'), ('C2', '1'))
        + net(4, 'VCC_RF', 'Default', ('R1', '2'), ('R2', '1'), ('R3', '1'))
        + net(5, 'N2', 'Default', ('R2', '2')) + net(6, 'N3', 'Default', ('R3', '2'))
        + net(7, 'RFA', 'RF_50OHM', ('J2', '1'), ('FL1', '1'), ('JP1', '1'))
        + net(8, 'RFB', 'RF_50OHM', ('FL1', '2'), ('JP1', '2'), ('U2', '1')) + '))')
    # a second netlist: one cell with a low-side NMOS reverse-polarity FET (gate
    # pulled to the cell's + through R2), a bidirectional ESD part, a zener
    open(os.path.join(d, 'fet.net'), 'w').write(
        '(export (version "E") (design (source "t.kicad_sch") (sheet (number "1") (name "/Root/")))'
        ' (components (comp (ref "BT1") (value "cell") (libsource (lib "Device") (part "Battery_Cell")))'
        ' (comp (ref "Q1") (value "X") (description "MOSFET N-CH 30V") (libsource (lib "y") (part "fet")))'
        ' (comp (ref "R2") (value "10k") (libsource (lib "Device") (part "R")))'
        ' (comp (ref "R1") (value "10") (libsource (lib "Device") (part "R")))'
        ' (comp (ref "D1") (value "ESD5") (description "Bidirectional TVS") (libsource (lib "Device") (part "D_TVS")))'
        ' (comp (ref "D2") (value "BZX84-C5V1") (description "Zener diode") (libsource (lib "Device") (part "D_Zener")))'
        ' (comp (ref "U1") (value "IC1") (libsource (lib "x") (part "ic"))))'
        ' (libparts (libpart (lib "Device") (part "Battery_Cell") (pins (pin (num "1") (name "+") (type "passive"))'
        ' (pin (num "2") (name "-") (type "passive"))))'
        ' (libpart (lib "y") (part "fet") (pins (pin (num "1") (name "G") (type "input"))'
        ' (pin (num "2") (name "S") (type "passive")) (pin (num "3") (name "D") (type "passive"))))'
        ' (libpart (lib "Device") (part "R") (pins (pin (num "1") (name "~") (type "passive"))'
        ' (pin (num "2") (name "~") (type "passive"))))'
        ' (libpart (lib "Device") (part "D_TVS") (pins (pin (num "1") (name "A1") (type "passive"))'
        ' (pin (num "2") (name "A2") (type "passive"))))'
        ' (libpart (lib "Device") (part "D_Zener") (pins (pin (num "1") (name "K") (type "passive"))'
        ' (pin (num "2") (name "A") (type "passive"))))'
        ' (libpart (lib "x") (part "ic") (pins (pin (num "1") (name "IN") (type "input"))'
        ' (pin (num "2") (name "GND") (type "power_in")))))'
        ' (nets (net (code "1") (name "VP") (node (ref "BT1") (pin "1")) (node (ref "R2") (pin "1"))'
        ' (node (ref "R1") (pin "1")) (node (ref "D1") (pin "1")))'
        ' (net (code "2") (name "VN") (node (ref "BT1") (pin "2")) (node (ref "Q1") (pin "3")))'
        ' (net (code "3") (name "GND") (node (ref "Q1") (pin "2")) (node (ref "U1") (pin "2"))'
        ' (node (ref "D1") (pin "2")) (node (ref "D2") (pin "2")))'
        ' (net (code "4") (name "NG") (node (ref "Q1") (pin "1")) (node (ref "R2") (pin "2"))'
        ' (node (ref "D2") (pin "1")))'
        ' (net (code "5") (name "NI") (node (ref "R1") (pin "2")) (node (ref "U1") (pin "1")))))')
    sch = os.path.join(d, 't.kicad_sch')
    open(sch, 'w').write(
        '(kicad_sch (lib_symbols (symbol "x:y" (symbol "y_1_1"'
        ' (pin passive line (at 0 0 0) (length 2.54) (number "1"))'
        ' (pin passive line (at 0 -2.54 0) (length 2.54) (number "2")))))'
        ' (symbol (lib_id "x:y") (at 100 100 0) (unit 1) (property "Reference" "U1"))'
        ' (wire (pts (xy 100 100) (xy 97.46 100))) (no_connect (at 97.46 100))'
        ' (sheet_instances (path "/" (page "1"))))')
    t = os.path.getmtime(os.path.join(d, 't.net')) + 3600
    os.utime(sch, (t, t))
    lint_project(os.path.join(d, 'lint'))
    sq = lambda x0, y0, x1, y1: f'(pts (xy {x0} {y0}) (xy {x1} {y0}) (xy {x1} {y1}) (xy {x0} {y1}))'
    fill = lambda ly, *boxes: (f'(zone (net "GND") (layer "{ly}") (polygon {sq(0, 0, 20, 20)})'
                               + ''.join(f' (filled_polygon (layer "{ly}") {sq(*bx)})' for bx in boxes) + ')')
    # B.Cu GND leaves x 9.5..14.5 bare (a removed island); F.Cu is solid GND with a
    # SIG track down x=12, so the rescue via must sit clear of x=12 (>= 0.3+0.15+0.1); a 1 mm2
    # +5V pour at 2,2 is a local pour `zones` folds (far from the void, so --voids is unmoved)
    open(os.path.join(d, 'voids.kicad_pcb'), 'w').write(
        '(kicad_pcb (version 20240108) (generator "pcbnew")'
        ' (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))'
        ' (gr_rect (start 0 0) (end 20 20) (layer "Edge.Cuts"))'
        ' (segment (start 12 1) (end 12 19) (width 0.2) (layer "F.Cu") (net "SIG"))'
        f' (zone (net "+5V") (layer "F.Cu") (polygon {sq(2, 2, 3, 3)}) (filled_polygon (layer "F.Cu") {sq(2, 2, 3, 3)}))'
        + fill('F.Cu', (0.5, 0.5, 19.5, 19.5)) + fill('B.Cu', (0.5, 0.5, 9.5, 19.5), (14.5, 0.5, 19.5, 19.5)) + ')')
    return os.path.join(d, 't.net')


def _tab_fp(ref, x, y, pads, crt=(.4, .4), rot=0):
    """a footprint in KiCad's tab layout (the writers edit by span); pads [(num, dx, dy, sx, sy, net[, pintype])]"""
    import uuid as U
    u = lambda: f'(uuid "{U.uuid4()}")'                 # noqa: E731
    return (f'\t(footprint "x:P"\n\t\t(layer "F.Cu")\n\t\t{u()}\n\t\t(at {x} {y}' + (f' {rot}' if rot else '') + ')\n'
            f'\t\t(property "Reference" "{ref}"\n\t\t\t(at 0 -1.5 0)\n\t\t\t(layer "F.SilkS")\n\t\t\t{u()}\n'
            f'\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1 1)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n'
            f'\t\t(fp_rect\n\t\t\t(start {-crt[0]} {-crt[1]})\n\t\t\t(end {crt[0]} {crt[1]})\n\t\t\t(stroke\n'
            f'\t\t\t\t(width 0.05)\n\t\t\t\t(type solid)\n\t\t\t)\n\t\t\t(layer "F.CrtYd")\n\t\t\t{u()}\n\t\t)\n'
            + ''.join(f'\t\t(pad "{n}" smd rect\n\t\t\t(at {dx} {dy})\n\t\t\t(size {sx} {sy})\n\t\t\t(layers "F.Cu")\n'
                      f'\t\t\t(net "{net}")\n' + ''.join(f'\t\t\t(pintype "{t}")\n' for t in pt) + f'\t\t\t{u()}\n\t\t)\n'
                      for n, dx, dy, sx, sy, net, *pt in pads) + '\t)\n')


def _tab_board(d, name, w, h, body):
    p = os.path.join(d, name)
    open(p, 'w').write('(kicad_pcb\n\t(version 20260901)\n\t(generator "pcbnew")\n\t(generator_version "10.99")\n'
                       '\t(layers\n\t\t(0 "F.Cu" signal)\n\t\t(2 "B.Cu" signal)\n\t\t(25 "Edge.Cuts" user)\n\t)\n'
                       f'\t(gr_rect\n\t\t(start 0 0)\n\t\t(end {w} {h})\n\t\t(layer "Edge.Cuts")\n\t)\n' + body + ')\n')
    return p


def _tseg(x0, y0, x1, y1, net, w=0.2, ly='F.Cu', uid=None):
    import uuid as U
    return (f'\t(segment\n\t\t(start {x0} {y0})\n\t\t(end {x1} {y1})\n\t\t(width {w})\n\t\t(layer "{ly}")\n'
            f'\t\t(net "{net}")\n\t\t(uuid "{uid or U.uuid4()}")\n\t)\n')


def _tvia(x, y, net):
    import uuid as U
    return (f'\t(via\n\t\t(at {x} {y})\n\t\t(size 0.6)\n\t\t(drill 0.3)\n\t\t(layers "F.Cu" "B.Cu")\n'
            f'\t\t(net "{net}")\n\t\t(uuid "{U.uuid4()}")\n\t)\n')


def sym(item, ind, fp='""', name=None, ref='U', extra=None):
    """a symbol node in KiCad's layout, `ind` tabs deep: Reference, Footprint, an optional extra
    field, one unit drawing a box"""
    t = '\t' * ind
    prop = lambda k, v: f'{t}\t(property "{k}" {v}\n{t}\t\t(at 0 0 0)\n{t}\t)\n'      # noqa: E731
    return (f'{t}(symbol "{name or item}"\n' + prop('Reference', f'"{ref}"') + prop('Footprint', fp)
            + (prop(extra, '"X"') if extra else '')
            + f'{t}\t(symbol "{item}_0_1"\n{t}\t\t(rectangle\n{t}\t\t\t(start -1 1)\n{t}\t\t\t(end 1 -1)\n{t}\t\t)\n{t}\t)\n{t})')


def _tzone(net, ly, x0, y0, x1, y1, uid):
    sq = ''.join(f'\t\t\t\t(xy {x} {y})\n' for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)))
    return (f'\t(zone\n\t\t(net "{net}")\n\t\t(layer "{ly}")\n\t\t(uuid "{uid}")\n\t\t(polygon\n\t\t\t(pts\n{sq}'
            f'\t\t\t)\n\t\t)\n\t\t(filled_polygon\n\t\t\t(layer "{ly}")\n\t\t\t(pts\n{sq}\t\t\t)\n\t\t)\n\t)\n')


def lint_project(d):
    """ksheet fixture, one hit per lint rule: a wire across R1's body (WIREBODY),
    /NA and /NB end-to-end 2.54 mm apart (GAPLINE), U1.1 jogging 1.27 mm at the
    pin (PINJOG), and R3.2 1.27 mm from U1.2's end (CROWD)."""
    os.makedirs(d)
    pin = lambda n, x, y, a, ln: (f'(pin passive line (at {x} {y} {a}) (length {ln}) '
                                   f'(name "{chr(64 + int(n))}") (number "{n}"))')
    sym = lambda lib, ref, x, y, r=0: (f'(symbol (lib_id "{lib}") (at {x} {y} {r}) (unit 1) '
                                        f'(property "Reference" "{ref}") (property "Value" "v"))')
    open(os.path.join(d, 'lint.kicad_sch'), 'w').write(
        '(kicad_sch (lib_symbols'
        ' (symbol "x:R" (symbol "R_0_1" (rectangle (start -1.016 2.54) (end 1.016 -2.54)))'
        '  (symbol "R_1_1" ' + pin(1, 0, 3.81, 270, 1.27) + pin(2, 0, -3.81, 90, 1.27) + '))'
        ' (symbol "x:U" (symbol "U_0_1" (rectangle (start -2.54 6.35) (end 2.54 -8.89)))'
        '  (symbol "U_1_1" ' + ''.join(pin(i + 1, -5.08, 5.08 - 2.54 * i, 0, 2.54) for i in range(6)) + ')))'
        + sym('x:R', 'R1', 50, 50) + sym('x:U', 'U1', 100, 100) + sym('x:R', 'R3', 89.84, 97.46, 90)
        + ' (wire (pts (xy 45 50) (xy 55 50)))'
        ' (wire (pts (xy 60 40) (xy 70 40))) (wire (pts (xy 72.54 40) (xy 80 40)))'
        ' (label "NA" (at 60 40 0)) (label "NB" (at 80 40 0))'
        ' (wire (pts (xy 94.92 94.92) (xy 94.92 93.65))) (wire (pts (xy 94.92 93.65) (xy 90 93.65)))'
        ' (sheet_instances (path "/" (page "1"))))')
    open(os.path.join(d, 'lint.net'), 'w').write(
        '(export (version "E") (design (source "lint.kicad_sch") (sheet (number "1") (name "/")))'
        ' (components' + ''.join(f' (comp (ref "{r}") (value "v") (libsource (lib "x") (part "{p}")))'
                                 for r, p in (('R1', 'R'), ('R3', 'R'), ('U1', 'U'))) + ')'
        ' (nets (net (code "1") (name "/J") (node (ref "U1") (pin "1")))'
        ' (net (code "2") (name "/K") (node (ref "U1") (pin "2")))'
        ' (net (code "3") (name "/L") (node (ref "R3") (pin "2")))))')


def _typed_dir(d, dru=True):
    """a project dir with Default clearance 0.15, an RF* class at 0.3, and (dru) the
    reference board's type rules: Pad to Track 0.1, outer track-track 0.127"""
    os.makedirs(d, exist_ok=True)
    pro = {'board': {'design_settings': {'rules': {'min_copper_edge_clearance': 0.2, 'min_text_height': 0.8,
                                                   'min_text_thickness': 0.1, 'min_silk_clearance': 0.15}}},
           'net_settings': {'classes': [{'name': 'Default', 'clearance': 0.15, 'track_width': 0.15, 'via_diameter': 0.6,
                                         'via_drill': 0.3}, {'name': 'RFC', 'clearance': 0.3}],
                            'netclass_patterns': [{'pattern': 'RF*', 'netclass': 'RFC'}]}}
    for stem in ('t', 's'):
        json.dump(pro, open(os.path.join(d, stem + '.kicad_pro'), 'w'))
    if dru:
        open(os.path.join(d, 't.kicad_dru'), 'w').write(
            '(version 1)\n(rule "Pad to Track"\n    (constraint clearance (min 0.1mm))\n'
            '    (condition "A.Type == \'Pad\' && B.Type == \'Track\'"))\n'
            '(rule "Min Trace Spacing (outer)"\n    (layer outer)\n    (constraint clearance (min 0.127mm))\n'
            '    (condition "A.Type == \'Track\' && B.Type == \'Track\'"))\n'
            '(rule "Min Silkscreen Text"\n    (layer "?.Silkscreen")\n    (constraint text_thickness (min 0.15mm))\n'
            '    (constraint text_height (min 1.0mm)))\n')
    return d


def _gzone(ly, outline, fill, name='GND', extra='', net='GND', uid=None):
    sq = lambda pts: ''.join(f'\t\t\t\t(xy {x} {y})\n' for x, y in pts)   # noqa: E731
    return (f'\t(zone\n\t\t(net "{net}")\n\t\t(layer "{ly}")\n\t\t(uuid "{uid or f"z{ly[0]}{len(outline)}"}")\n\t\t(name "{name}")\n'
            f'{extra}\t\t(polygon\n\t\t\t(pts\n{sq(outline)}\t\t\t)\n\t\t)\n'
            + (f'\t\t(filled_polygon\n\t\t\t(layer "{ly}")\n\t\t\t(pts\n{sq(fill)}\t\t\t)\n\t\t)\n' if fill else '')
            + '\t)\n')


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def run(argv, env=None):
    # fixture sheets are fake and golden inputs are frozen: never auto-regenerate
    e = {**os.environ, 'KREVIEW_NO_REGEN': '1', **(env or {})}
    p = subprocess.run([sys.executable, os.path.join(S, argv[0])] + argv[1:],
                       capture_output=True, text=True, env={k: v for k, v in e.items() if v})
    return p.returncode, p.stdout + p.stderr


CHECKS = []                     # the suites' ad-hoc checks, one bool each, for the total

def check(ok, msg):
    """Count one ad-hoc check and print it (a pass only with -v); returns 1 if it failed."""
    CHECKS.append(bool(ok))
    if VERBOSE or not ok:
        print(f"{'ok  ' if ok else 'FAIL'}  {msg}")
    return int(not ok)
