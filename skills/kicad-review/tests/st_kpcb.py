"""Self-test cases: kpcb.py read-only commands (references/kpcb.md): check, where, zones, ampacity, view, ...

selftest.py runs suite(); see its docstring for the case format."""
import os, re
from st_common import CASES, CROSS, NET, PCB, PCB2, PCB3, _gzone, _tab_board, _tab_fp, _tseg, check, rect, run


def fab_board(d):
    """FABFLAGS, against a t.pretty library: C2 DNP and excluded from the BOM, SW1 an LCSC
    part excluded from the BOM, TP1 in the CPL where its library footprint is not. C1 (DNP,
    in the BOM), FID1 (excluded from the BOM like its library footprint, in the CPL) and the
    board_only logo are fine."""
    d = os.path.join(d, 'fab'); os.makedirs(os.path.join(d, 't.pretty'), exist_ok=True)
    open(os.path.join(d, 'fp-lib-table'), 'w').write(
        '(fp_lib_table (lib (name "t") (type "KiCad") (uri "${KIPRJMOD}/t.pretty")))')
    for n, attr in (('TP', 'exclude_from_pos_files exclude_from_bom'), ('FID', 'smd exclude_from_bom')):
        open(os.path.join(d, 't.pretty', n + '.kicad_mod'), 'w').write(f'(footprint "{n}" (attr {attr}))')
    p = os.path.join(d, 'fab.kicad_pcb')
    fp = lambda ref, x, attr, lcsc='', lib='': (
        f' (footprint "{lib or "x:" + ref}" (layer "F.Cu") (at {x} 5) (property "Reference" "{ref}")'
        + (f' (property "LCSC Part" "{lcsc}")' if lcsc else '') + f' (attr {attr})'
        f' (fp_rect (start -.5 -.3) (end .5 .3) (layer "F.CrtYd"))'
        f' (pad "1" smd rect (at 0 0) (size .3 .3) (layers "F.Cu")))')
    open(p, 'w').write('(kicad_pcb (version 20240108) (generator "pcbnew")'
                       ' (layers (0 "F.Cu" signal) (25 "Edge.Cuts" user)) (gr_rect (start 0 0) (end 30 10) (layer "Edge.Cuts"))'
                       + fp('C1', 3, 'smd dnp', 'C1525') + fp('C2', 6, 'smd exclude_from_bom dnp', 'C1525')
                       + fp('SW1', 9, 'smd exclude_from_bom', 'C202388') + fp('TP1', 12, 'exclude_from_bom', lib='t:TP')
                       + fp('FID1', 18, 'smd exclude_from_bom', lib='t:FID')
                       + fp('G1', 15, 'board_only exclude_from_pos_files exclude_from_bom') + ')')
    return p


def assembly_board(d):
    """`assembly`: U1 a 0.4 mm-pitch QFN with no Fab outline, its exposed pad found as ringed
    by the others and its thermal via not a joint; U2 an LGA (every pad inside the Fab body);
    Q1 (back) and C1 iron parts; J1 through-hole (its pads under the body are soldered from
    the other side); C2 DNP and FID1 excluded from the BOM are not counted. D1 a SOD-882
    (1.0x0.6 body, 3/4 of each land under it: bottom-only terminals, listed) where C1, an 0402
    chip of the same size, is not. BT1.1 a 9x7.5 mm land solid into a 240 mm2 GND pour
    (heat-sinked); BT1.2 on the same pour through thermal spokes is not."""
    p = os.path.join(d, 'asm.kicad_pcb')
    pad = lambda n, x, y, w, h, k='smd', lay='F.Cu', ex='': (                          # noqa: E731
        f' (pad "{n}" {k} rect (at {x} {y}) (size {w} {h})' + (' (drill .3)' if k != 'smd' else '')
        + f' (layers "{lay}"){ex})')
    fab = lambda x0, y0, x1, y1, s='F': f' (fp_rect (start {x0} {y0}) (end {x1} {y1}) (layer "{s}.Fab"))'   # noqa: E731
    fp = lambda ref, x, y, body, attr='smd', s='F': (                                 # noqa: E731
        f' (footprint "x:{ref}" (layer "{s}.Cu") (at {x} {y}) (property "Reference" "{ref}") (attr {attr}){body})')
    qfn = ''.join(pad(i + 1 + 4 * (sx > 0), sx, -.6 + .4 * i, .6, .2) for sx in (-1, 1) for i in range(4))
    qfn += pad(9, 0, 0, 1, 1) + pad(9, 0, 0, .5, .5, 'thru_hole', '*.Cu')
    lga = fab(-.6, -.6, .6, .6) + ''.join(pad(i + 1, x, y, .3, .3) for i, (x, y) in
                                          enumerate(((-.3, -.3), (.3, -.3), (.3, .3), (-.3, .3))))
    sot = fab(-.65, -1.45, .65, 1.45, 'B') + ''.join(pad(n, x, y, .6, .8, lay='B.Cu') for n, x, y in
                                                     ((1, -.95, 1.4), (2, .95, 1.4), (3, 0, -1.4)))
    chip = fab(-.5, -.25, .5, .25) + pad(1, -.48, 0, .56, .62) + pad(2, .48, 0, .56, .62)
    tht = fab(-1.27, -1.27, 3.81, 1.27) + pad(1, 0, 0, 1.7, 1.7, 'thru_hole', '*.Cu') + pad(2, 2.54, 0, 1.7, 1.7, 'thru_hole', '*.Cu')
    sod = fab(-.3, -.5, .3, .5) + pad(1, 0, -.35, .7, .4) + pad(2, 0, .35, .7, .4)
    bt = (fab(-6, -4, 6, 4, 'B') + pad(1, -4, 0, 9, 7.5, lay='B.Cu', ex=' (net "GND") (zone_connect 2)')
          + pad(2, 6, 0, 9, 7.5, lay='B.Cu', ex=' (net "GND")'))
    open(p, 'w').write('(kicad_pcb (version 20240108) (generator "pcbnew")'
                       ' (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (25 "Edge.Cuts" user))'
                       ' (gr_rect (start 0 0) (end 30 20) (layer "Edge.Cuts"))'
                       + fp('U1', 5, 5, qfn) + fp('U2', 10, 5, lga) + fp('Q1', 15, 5, sot, s='B')
                       + fp('C1', 20, 5, chip) + fp('C2', 23, 5, chip, 'smd dnp')
                       + fp('FID1', 26, 5, pad(1, 0, 0, 1, 1), 'smd exclude_from_bom')
                       + fp('J1', 5, 15, tht, 'through_hole') + fp('D1', 25, 15, sod)
                       + fp('BT1', 50, 10, bt, s='B') + _gzone('B.Cu', rect(30, 0, 60, 20), rect(38, 4, 62, 14)) + ')')
    return p


def crtyd_board(d):
    """CRTYDPAD: J1's courtyard wraps its housing (y -3..-1) but not its pads (y 0, 2).
    HOLECLR: H1 (3.2 mm hole, keepout 3.1 at --hole 1.5) - R1's courtyard corner reaches
    2.3 mm from the centre on the diagonal but its pads stay 3.25 mm out (clear); R2's pad
    sits 2.3 mm out (inside). ESD: J2.1 (S) is 15 mm from its clamp D1 and U1.1 sits 3 mm
    from it (reached first); J3.1 (T) has D2 2 mm away (fine). Pads: (num, x, y[, net])."""
    p = os.path.join(d, 'crtyd.kicad_pcb')
    def fp(ref, x, y, crt, pads, name='', size=.4, drill='', value=''):
        pads = [(q[0], q[1], q[2], f' (net "{q[3]}")' if len(q) > 3 else '') for q in pads]
        return (f' (footprint "{name or "x:" + ref}" (layer "F.Cu") (at {x} {y}) (property "Reference" "{ref}")'
                + (f' (property "Value" "{value}")' if value else '') + ' (attr smd)'
                f' (fp_rect (start {crt[0]} {crt[1]}) (end {crt[2]} {crt[3]}) (layer "F.CrtYd"))'
                + ''.join(f' (pad "{n}" {"thru_hole" if drill else "smd"} circle (at {px} {py}) (size {size} {size})'
                          f'{drill} (layers "F.Cu"){net})' for n, px, py, net in pads) + ')')
    box = (-.5, -.5, .5, 1.5)
    open(p, 'w').write('(kicad_pcb (version 20240108) (generator "pcbnew")'
                       ' (layers (0 "F.Cu" signal) (25 "Edge.Cuts" user)) (gr_rect (start 0 0) (end 40 30) (layer "Edge.Cuts"))'
                       + fp('J1', 30, 15, (-1, -3, 1, -1), (('1', 0, 0), ('2', 0, 2)))
                       + fp('H1', 10, 10, (-1.7, -1.7, 1.7, 1.7), (('1', 0, 0),), 'MountingHole_3.2mm', 3.2, ' (drill 3.2)')
                       + fp('R1', 12.1, 12.1, (-.5, -.5, 1, 1), (('1', .4, .4), ('2', .7, .7)))
                       + fp('R2', 10, 7.5, (-.5, -.5, .5, .5), (('1', 0, 0),))
                       + fp('J2', 38, 25, box, (('1', 0, 0, 'S'), ('2', 0, 1, 'GND')))
                       + fp('D1', 23, 25, box, (('1', 0, 0, 'S'), ('2', 0, 1, 'GND')), value='ESD5Z5.0')
                       + fp('U1', 35, 25, box, (('1', 0, 0, 'S'), ('2', 0, 1, 'VCC')))
                       + fp('J3', 38, 20, box, (('1', 0, 0, 'T'), ('2', 0, 1, 'GND')))
                       + fp('D2', 36, 20, box, (('1', 0, 0, 'T'), ('2', 0, 1, 'GND')), value='PESD5V0S1BL') + ')')
    return p


def link_board(d):
    """sync by symbol path: R1 linked, R2 refdes-only (no path), FID1 board_only and
    not in the schematic (INFO, not an error). Returns (board, net)."""
    fp = lambda r, extra: (f' (footprint "R" (layer "F.Cu") (at 5 5){extra} (property "Reference" "{r}")'
                           f' (property "Value" "1k") (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu")))')
    p, n = os.path.join(d, 'link.kicad_pcb'), os.path.join(d, 'link.net')
    open(p, 'w').write('(kicad_pcb (version 20240108) (generator "pcbnew")'
                       ' (layers (0 "F.Cu" signal) (25 "Edge.Cuts" user))'
                       + fp('R1', ' (path "/s1/u1")') + fp('R2', '') + fp('FID1', ' (attr smd board_only)') + ')')
    comp = lambda r, u: (f' (comp (ref "{r}") (value "1k") (libsource (lib "x") (part "R"))'
                         f' (sheetpath (names "/") (tstamps "/s1/")) (tstamps "{u}"))')
    open(n, 'w').write('(export (version "E") (design (source "t.kicad_sch")) (components'
                       + comp('R1', 'u1') + comp('R2', 'u2') + ') (libparts) (nets))')
    return p, n


def edge_board(d):
    """J1: an edge-launch part whose PCB Edge mark sits 0.5 mm inside the top edge.
    J2: a side-entry connector (Horizontal, MP pads toward the bottom edge) whose MP
    pad ends 0.2 mm from the edge, inside the 0.3 mm default edge clearance."""
    p = os.path.join(d, 'edge.kicad_pcb')
    pad = lambda n, x, y, w, h: f' (pad "{n}" smd rect (at {x} {y}) (size {w} {h}) (layers "F.Cu") (net "N{n}"))'
    open(p, 'w').write(
        '(kicad_pcb (version 20240108) (generator "pcbnew")'
        ' (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))'
        ' (gr_rect (start 0 0) (end 20 20) (layer "Edge.Cuts"))'
        ' (footprint "SMA_EdgeMount" (layer "F.Cu") (at 10 1.5) (property "Reference" "J1")'
        ' (fp_line (start -4 -1) (end 4 -1) (layer "Dwgs.User")) (fp_text user "PCB Edge" (at 0 -1.5) (layer "Dwgs.User"))'
        + pad('1', 0, 0, 1, 1) + ')'
        ' (footprint "JST_SH_Horizontal" (layer "F.Cu") (at 10 18) (property "Reference" "J2")'
        ' (fp_rect (start -4 -3) (end 4 1.5) (layer "F.Fab"))'
        + pad('1', 0, -2, .6, 1.5) + pad('MP', -3, .8, 1, 2) + pad('MP', 3, .8, 1, 2) + '))')
    return p


def neck_board(d):
    """U1's pad -> a 0.2 x 0.35 mm stub -> a 0.3 mm track to C1: the track's end stops
    short of the pad (0.35 - 0.15 > 0.15), so the stub is the only way in: PAD-NECK."""
    p = os.path.join(d, 'neck.kicad_pcb')
    pad = lambda r, x: (f' (footprint "P" (layer "F.Cu") (at {x} 5) (property "Reference" "{r}")'
                        ' (pad "1" smd rect (at 0 0) (size 0.3 0.3) (layers "F.Cu") (net "N")))')
    open(p, 'w').write(
        '(kicad_pcb (version 20240108) (generator "pcbnew")'
        ' (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))'
        ' (gr_rect (start 0 0) (end 20 10) (layer "Edge.Cuts"))' + pad('U1', 5) + pad('C1', 15)
        + ' (segment (start 5 5) (end 5.35 5) (width 0.2) (layer "F.Cu") (net "N"))'
        ' (segment (start 5.35 5) (end 15 5) (width 0.3) (layer "F.Cu") (net "N")))')
    return p


def stub_board(d):
    """J1 -> J2 on a 1.5 mm trunk, with U1 and C1 each on a 0.2 mm stub off it. Every
    arm of the tee is a pad stub (three DC parts), U1's is the only one under 2 A, and
    C1's cap stub is no carrier at all."""
    p = os.path.join(d, 'stub.kicad_pcb')
    pad = lambda r, x, y: (f' (footprint "P" (layer "F.Cu") (at {x} {y}) (property "Reference" "{r}")'
                           ' (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu") (net "N")))')
    seg = lambda a, b, w: f' (segment (start {a}) (end {b}) (width {w}) (layer "F.Cu") (net "N"))'
    open(p, 'w').write(
        '(kicad_pcb (version 20240108) (generator "pcbnew")'
        ' (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))'
        ' (gr_rect (start 0 0) (end 20 10) (layer "Edge.Cuts"))'
        + pad('J1', 2, 5) + pad('J2', 18, 5) + pad('U1', 10, 8) + pad('C1', 14, 8)
        + seg('2 5', '10 5', 1.5) + seg('10 5', '14 5', 1.5) + seg('14 5', '18 5', 1.5)
        + seg('10 5', '10 8', 0.2) + seg('14 5', '14 8', 0.2) + ')')
    return p


def dup_board(d):
    """Three padless `REF**` logos (KiCad allows duplicate refs; the third is a B.Cu
    footprint whose art is on F.SilkS; only the first is board_only) beside one real part, R1."""
    logo = lambda x, side, art, at='': (f' (footprint "Logo" (layer "{side}") (at {x} 5){at}'
                                        ' (property "Reference" "REF**") (property "Value" "LOGO")'
                                 f' (fp_poly (pts (xy -1 -1) (xy 1 -1) (xy 1 1)) (layer "{art}")))')
    p = os.path.join(d, 'dup.kicad_pcb')
    open(p, 'w').write(
        '(kicad_pcb (version 20240108) (generator "pcbnew")'
        ' (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))'
        ' (gr_rect (start 0 0) (end 20 20) (layer "Edge.Cuts"))'
        + logo(5, 'F.Cu', 'F.SilkS', ' (attr board_only)') + logo(10, 'F.Cu', 'F.SilkS') + logo(15, 'B.Cu', 'F.SilkS')
        + ' (footprint "R_0402" (layer "F.Cu") (at 10 12) (property "Reference" "R1") (property "Value" "10k")'
        ' (pad "1" smd rect (at -0.5 0) (size 0.5 0.5) (layers "F.Cu") (net "A"))'
        ' (pad "2" smd rect (at 0.5 0) (size 0.5 0.5) (layers "F.Cu") (net "B"))))')
    open(os.path.join(d, 'dup.net'), 'w').write(
        '(export (version "E") (design (source "dup.kicad_sch"))'
        ' (components (comp (ref "R1") (value "10k") (footprint "R_0402") (libsource (lib "Device") (part "R"))))'
        ' (libparts) (nets (net (code "1") (name "A") (node (ref "R1") (pin "1")))'
        ' (net (code "2") (name "B") (node (ref "R1") (pin "2")))))')
    return p


def tee_board(d):
    """A via whose barrel reaches two tracks' bodies, where track B ends on track A:
    the joins must not depend on set order. J1 -> J2 by hand: 2 mm of 1.5 mm
    (0.655 mohm) + 3.1 mm of 0.2 mm from the via on (7.617) = 8.27 mohm."""
    p = os.path.join(d, 'tee.kicad_pcb')
    pad = lambda r, x, y: (f' (footprint "P" (layer "F.Cu") (at {x} {y}) (property "Reference" "{r}")'
                           ' (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu") (net "N")))')
    open(p, 'w').write(
        '(kicad_pcb (version 20240108) (generator "pcbnew")'
        ' (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))'
        ' (gr_rect (start -2 -2) (end 6 6) (layer "Edge.Cuts"))' + pad('J1', 0, 0) + pad('J2', 2, 4)
        + ' (segment (start 0 0) (end 4 0) (width 1.5) (layer "F.Cu") (net "N"))'
        ' (segment (start 2 0) (end 2 4) (width 0.2) (layer "F.Cu") (net "N"))'
        ' (via (at 2 0.9) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "N")))')
    return p


def scale_board(d):
    """One 10.99-form footprint scaled 0.5 (CrtYd 8 x 4, Fab 6 x 2 in its own frame)
    at 10,10 on a board whose grid origin is 5,5."""
    p = os.path.join(d, 'scale.kicad_pcb')
    open(p, 'w').write(
        '(kicad_pcb (version 20250901) (generator "pcbnew") (generator_version "10.99")'
        ' (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))'
        ' (setup (grid_origin 5 5) (aux_axis_origin 2 3))'
        ' (gr_rect (start 0 0) (end 20 20) (layer "Edge.Cuts"))'
        ' (footprint "Logo" (layer "F.Cu") (transform (translate 10 10) (rotate 0) (scale 0.5 0.5))'
        ' (property "Reference" "S1") (property "Value" "ART")'
        ' (fp_rect (start -4 -2) (end 4 2) (layer "F.CrtYd"))'
        ' (fp_rect (start -3 -1) (end 3 1) (layer "F.Fab"))'
        ' (fp_poly (pts (xy -2 -1) (xy 2 -1) (xy 2 1)) (layer "F.SilkS"))))')
    return p


def custom_pad_board(d):
    """U1.1 an L-shaped custom pad (2 x 2 box, arms 0.4 wide); a track from the empty
    corner of that box (1.5,1.5 local) to TP2: inside the box, nowhere near the copper"""
    p = os.path.join(d, 'cpad.kicad_pcb')
    open(p, 'w').write(
        '(kicad_pcb (version 20240108) (generator "pcbnew")'
        ' (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))'
        ' (gr_rect (start 0 0) (end 20 10) (layer "Edge.Cuts"))'
        ' (footprint "U" (layer "F.Cu") (at 5 5) (property "Reference" "U1")'
        ' (pad "1" smd custom (at 0 0) (size 0.2 0.2) (layers "F.Cu") (net "N")'
        ' (primitives (gr_poly (pts (xy 0 0) (xy 2 0) (xy 2 0.4) (xy 0.4 0.4) (xy 0.4 2) (xy 0 2)) (width 0)))))'
        ' (footprint "TP" (layer "F.Cu") (at 12 6.5) (property "Reference" "TP2")'
        ' (pad "1" smd rect (at 0 0) (size 0.6 0.6) (layers "F.Cu") (net "N")))'
        ' (segment (start 6.5 6.5) (end 12 6.5) (width 0.2) (layer "F.Cu") (net "N")))')
    return p


def rfbranch_board(d):
    """RFX: TP1 (2,5) -> TP2 (18,5) on F.Cu, and a 3 mm branch (10,5)->(10,8) to JP1.1, a DNP
    pad: an open stub, over lambda/50 at --freq 5000 (1.2 mm with no stackup, eeff 1)"""
    jp = _tab_fp('JP1', 10, 8, [('1', 0, 0, .6, .6, 'RFX')]).replace('\t\t(layer "F.Cu")\n', '\t\t(layer "F.Cu")\n\t\t(attr smd dnp)\n', 1)
    return _tab_board(d, 'rfbr.kicad_pcb', 20, 12, _tab_fp('TP1', 2, 5, [('1', 0, 0, .6, .6, 'RFX')])
                      + _tab_fp('TP2', 18, 5, [('1', 0, 0, .6, .6, 'RFX')]) + jp
                      + _tseg(2, 5, 18, 5, 'RFX', 0.3) + _tseg(10, 5, 10, 8, 'RFX', 0.3))


def refslot_board(d):
    """4 layers with a stackup. Net S on F.Cu (2,5)->(18,5); In1 GND filled only x < 12, and
    an In1 track of X at x=15 cutting across the gap under S"""
    p = os.path.join(d, 'refslot.kicad_pcb')
    st = ''.join(f'\t\t\t(layer "{n}"\n\t\t\t\t(type "{t}")\n\t\t\t\t(thickness {th})\n' + ('\t\t\t\t(epsilon_r 4.4)\n' if t != 'copper' else '')
                 + '\t\t\t)\n' for n, t, th in (('F.Cu', 'copper', 0.035), ('dielectric 1', 'prepreg', 0.2), ('In1.Cu', 'copper', 0.03),
                                                ('dielectric 2', 'core', 1.0), ('In2.Cu', 'copper', 0.03),
                                                ('dielectric 3', 'prepreg', 0.2), ('B.Cu', 'copper', 0.035)))
    open(p, 'w').write('(kicad_pcb\n\t(version 20260901)\n\t(generator "pcbnew")\n\t(generator_version "10.99")\n'
                       '\t(layers\n\t\t(0 "F.Cu" signal)\n\t\t(4 "In1.Cu" signal)\n\t\t(6 "In2.Cu" signal)\n\t\t(2 "B.Cu" signal)\n'
                       '\t\t(25 "Edge.Cuts" user)\n\t)\n\t(setup\n\t\t(stackup\n' + st + '\t\t)\n\t)\n'
                       '\t(gr_rect\n\t\t(start 0 0)\n\t\t(end 20 10)\n\t\t(layer "Edge.Cuts")\n\t)\n'
                       + _tseg(2, 5, 18, 5, 'S') + _tseg(15, 1, 15, 9, 'X', 0.2, 'In1.Cu')
                       + _gzone('In1.Cu', rect(.5, .5, 12, 9.5), rect(.5, .5, 12, 9.5)) + ')\n')
    return p


def _void_via(out):
    """`zones --voids`: the rescue via must land inside the void, off the SIG track at x=12"""
    if 'rescue via at ' not in out:
        return ''
    vx = float(out.split('rescue via at ')[1].split(',')[0])
    return f"rescue via x={vx} is on the SIG track or outside the void" if abs(vx - 12) < 0.55 or not 9.5 < vx < 14.5 else ''


def suite(tmp, mini):
    """Append this file's cases to CASES, yield while the runner runs them, then do the
    ad-hoc checks (the full run only: -k stops at the yield)."""
    CASES.append(("kpcb help cmd", ['kpcb.py', PCB, 'where', '-h'],          0, ["kpcb.py FILE where U8 J7", "where flags:", "  --pads ", "lists every command"]))
    CASES.append(("kpcb help cmd flags", ['kpcb.py', PCB, 'copper', '--help'], 0, ["copper flags:", "  --net NET ", "only these nets"]))
    bad = os.path.join(tmp.name, 'badcfg')         # a knet.json typo: named once, not a silently lost ilim table
    os.makedirs(bad)
    open(os.path.join(bad, 'b.kicad_pcb'), 'w').write(open(PCB).read())
    open(os.path.join(bad, 'knet.json'), 'w').write('{"ilim": ')
    CASES.append(("kpcb malformed knet.json", ['kpcb.py', os.path.join(bad, 'b.kicad_pcb'), 'ampacity'], 0,
                  ["(ignoring malformed knet.json: Expecting value"]))
    CASES.append(("kpcb where --pads", ['kpcb.py', PCB, 'where', 'U1', '--pads'], 0, ["    2     11.500, 11.500  F      0.50x0.60 rot 0  GND"]))
    CASES.append(("kpcb summary zones", ['kpcb.py', PCB2, 'summary'],        0, ["zones  : 1 ", "  F.Cu    GND"]))
    CASES.append(("kpcb check",   ['kpcb.py', PCB, 'check'],                 2, ["4 error, 10 warn, 3 info"]))
    CASES.append(("kpcb unplaced", ['kpcb.py', PCB, 'unplaced'], 0,
                  ["4 footprint(s) still parked off the board", "C9 R9-R11"]))
    CASES.append(("kpcb review", ['kpcb.py', PCB, 'review'], 2,
                  ["### STOP: board vs selftest.net", "### placement", "### findings", "### next"]))
    CASES.append(("kpcb summary", ['kpcb.py', PCB, 'summary'],               0, ["40.00 x 30.00 mm", "placed 16"]))
    # nightly writes (transform (translate X Y) (rotate R)); read as (at) it parks all at 0,0
    CASES.append(("kpcb nightly", ['kpcb.py', PCB3, 'summary'],              0, ["pcbnew 10.99", "placed 16"]))
    CASES.append(("kpcb nightly check", ['kpcb.py', PCB3, 'check'],          2, ["4 error, 10 warn, 3 info"]))
    CASES.append(("kpcb map",     ['kpcb.py', PCB, 'map'],                   0, []))
    CASES.append(("kpcb span",    ['kpcb.py', PCB, 'span'],                  0, ["1 net(s)"]))
    CASES.append(("kpcb sheet",   ['kpcb.py', PCB, 'sheet'],                 0, ["/Test/", "/Test/Spare/"]))
    CASES.append(("kpcb sync",    ['kpcb.py', PCB, 'sync', NET],             2, ["23 error, 7 warn"]))
    CASES.append(("kpcb ic",      ['kpcb.py', PCB, 'ic'],                    1, ["no regulator-shaped part found"]))  # 1 = not found
    CASES.append(("kpcb ampacity",['kpcb.py', PCB, 'ampacity', 'PWR', '--amps', '5'], 2, ["TRACE-THIN", "VIA-FEW"]))
    CASES.append(("kpcb amp-par", ['kpcb.py', PCB, 'ampacity', 'PAR', '--amps', '5'], 0, ["MESH-CHECK"]))  # parallel edges: no bridge, not flagged thin
    # selftest_amp2.kicad_pcb: false-positive classes once reported as bugs.
    # NECK's 0.5 mm track end overlaps U1's pad (its cap reaches x 5.05, the pad edge is
    # 5.15), so the 0.2 mm stub is inside one piece of metal: no neck at all
    CASES.append(("kpcb amp-neck", ['kpcb.py', PCB2, 'ampacity', 'NECK', '--amps', '1.0'],
                  0, ["bottleneck 1.45 A on F.Cu (narrowest bridge)", "OK"]))
    CASES.append(("kpcb amp-tap",  ['kpcb.py', PCB2, 'ampacity', 'TAP', '--amps', '1.2'],
                  2, ["TRACE-THIN", "near J1", '!near TH2']))  # real backbone bottleneck, TH2 tap branch excluded
    CASES.append(("kpcb amp-alltap", ['kpcb.py', PCB2, 'ampacity', 'ALLTAP', '--amps', '1.0'],
                  0, ["meshed, no series bottleneck (sense-tap legs skipped: TH1)   OK"]))  # the only bridge is a tap
    # nodal solve J1 -> J2: the TH2 tap leg carries nothing; R = 13.10 + 6.88 mohm by hand
    CASES.append(("kpcb amp-path", ['kpcb.py', PCB2, 'ampacity', '--from', 'J1.1', '--to', 'J2.1', '--amps', '1.2'], 2,
                  ["R 19.98 mohm", "0.30 x  8.00 mm  1.20 A (100%)", "1 element(s) over"]))
    CASES.append(("kpcb zones-under", ['kpcb.py', PCB2, 'zones', 'U2', 'U3'], 2,
                  ["100% of samples covered  (continuous)", "27% of samples covered  (MOSTLY MISSING)"]))
    # a +3V3 via dropped on U1 pad 1's centre -> one same-net via-in-pad, no mismatch
    CASES.append(("kpcb viapad",  ['kpcb.py', PCB, 'viapad'],                 0,
                  ["1 via drill(s) reach into 1 SMD pad mask opening(s)", "U1.1", "drill wholly in", "OK same net (+3V3)",
                   "via protection (Board Setup): none (open vias)"]))
    CASES.append(("kpcb viapad --signal", ['kpcb.py', PCB, 'viapad', '--signal'], 0, ["1 PWR / 0 SIG", "showing 0"]))
    CASES.append(("kpcb where pad", ['kpcb.py', PCB, 'where', 'U1.1', 'U1.2'], 0,
                  ["8.500, 8.500  (absolute)", "U1.1 -> U1.2: 4.24 mm"]))
    CASES.append(("kpcb net",     ['kpcb.py', PCB, 'net', '+3V3'],            0, ["2 pad(s)", "U1.1", "1 via(s)",
                                                                               "copper  2 PIECES", "C1.1  (@9.5,20.0)"]))
    CASES.append(("kpcb net crossing", ['kpcb.py', CROSS, 'net', 'N'],        0, ["copper  one piece joins all 2 pad(s)"]))
    CASES.append(("kpcb amp crossing", ['kpcb.py', CROSS, 'ampacity', '--from', 'J1.1', '--to', 'J2.1', '--amps', '0.5'], 0,
                  ["R 23.17 mohm", "4 track piece(s)"]))
    lb, ln = link_board(tmp.name)
    CASES.append(("kpcb sync link+board_only", ['kpcb.py', lb, 'sync', ln], 2,
                  ["1 error, 0 warn, 1 info", "R2 is not linked to its symbol", "board-only footprints", "FID1"]))
    CASES.append(("kpcb check FABFLAGS", ['kpcb.py', fab_board(tmp.name), 'check', '--only', 'FABFLAGS'], 0,
                  ["0 error, 2 warn, 1 info", "C2 is DNP and excluded from the BOM: the BOM loses it",
                   "SW1 has LCSC C202388 but is excluded from the BOM",
                   "1 part(s) whose BOM/pos flags differ from their library footprint: TP1 (-pos_files)"]))
    CASES.append(("kpcb assembly", ['kpcb.py', assembly_board(tmp.name), 'assembly'], 0,
                  ["7 parts to fit, 5 front / 2 back, 7 BOM lines; 22 SMD pads, 2 through-hole",
                   "not counted: DNP 1 (C2); excluded from the BOM 1 (FID1)",
                   "0402-size 3 | 0603-size 0 | 0805-size 0 | 1206-size 1 | larger 2 | no Fab outline 1",
                   "through-hole (1): J1", "(3 parts)", "the other 4:", "!C1  ",
                   "D1                       F        -    0.40    2/2   0.6x1.0  D1",
                   "heat-sinked lands (1):", "BT1.1      B      9.0x7.5      240     1  GND",
                   "U1                       F     0.40    0.20    1/9         -  U1",
                   "U2                       F     0.60    0.30    4/4   1.2x1.2  U2"]))
    CASES.append(("kpcb check CRTYDPAD HOLECLR", ['kpcb.py', crtyd_board(tmp.name), 'check', '--only', 'CRTYDPAD,HOLECLR'], 2,
                  ["1 error, 1 warn", "J1: 2 of 2 pad(s) outside its own courtyard",
                   "R2 is inside H1's 3.1 mm screw keepout: its pad 2.30 mm from the centre"]))
    CASES.append(("kpcb check ESD", ['kpcb.py', crtyd_board(tmp.name), 'check', '--only', 'ESD'], 0,
                  ["0 error, 1 warn", "J2.1 (S) is 15.0 mm from D1 (ESD5Z5.0), the nearest clamp on that net (want <= 10); "
                   "U1.1 is 3.0 mm from the pin, so a strike reaches it first"]))
    circ = lambda cx, cy, r: (f'\t\t(fp_circle\n\t\t\t(center {cx} {cy})\n\t\t\t(end {cx + r} {cy})\n\t\t\t(stroke\n'  # noqa: E731
                              '\t\t\t\t(width 0.1)\n\t\t\t\t(type solid)\n\t\t\t)\n\t\t\t(layer "F.Fab")\n\t\t)\n')
    wl = [(n, dx, dy, .2, .2, 'N') for n, dx, dy in (('A1', -.2, -.2), ('A2', .2, -.2), ('B1', -.2, .2), ('B2', .2, .2))]
    fb = _tab_board(tmp.name, 'fabcirc.kicad_pcb', 20, 10,   # U9: ball markers only; U8: a round housing
                    _tab_fp('U9', 5, 5, wl, (.6, .6)).replace('\t\t(pad', ''.join(circ(dx, dy, .05) for _n, dx, dy, *_ in wl)
                                                               + '\t\t(pad', 1)
                    + _tab_fp('U8', 12, 5, wl, (1.2, 1.2)).replace('\t\t(pad', circ(0, 0, 1) + '\t\t(pad', 1))
    CASES.append(("kpcb where fab markers are not a body", ['kpcb.py', fb, 'where', 'U9', 'U8'], 0,
                  ["fab body  : none drawn", "fab body  : 11.00,4.00 .. 13.00,6.00  (2.00 x 2.00 mm)"]))
    CASES.append(("kpcb custom pad copper", ['kpcb.py', custom_pad_board(tmp.name), 'net', 'N'], 0,
                  ["copper  2 PIECES"]))
    CASES.append(("kpcb check EDGEREF", ['kpcb.py', edge_board(tmp.name), 'check', '--only', 'EDGEREF'], 0,
                  ["J1's PCB Edge mark (Dwgs.User) is 0.50 mm inside the outline",
                   "move it +0.00,-0.50 mm (nearest pad then 0.50 mm from the edge, edge_clearance 0.3)",
                   "J2 side-entry, mates +y: Fab housing front 0.50 mm inside the edge; a pad is already "
                   "0.10 mm inside the 0.3 mm edge_clearance"]))
    CASES.append(("kpcb amp-pad-neck", ['kpcb.py', neck_board(tmp.name), 'ampacity', 'N', '--amps', '1.0'], 0,
                  ["PAD-NECK", "stub landing right on U1.1"]))
    CASES.append(("kpcb amp-stub", ['kpcb.py', stub_board(tmp.name), 'ampacity', 'N', '--amps', '2'], 0,
                  ["meshed, no series bottleneck; 3 part(s) hang on pad stubs",
                   "STUB-CHECK: 1 pad stub(s) under 2.00 A, each the only copper to one part: U1.1 0.20 mm"]))
    dp = dup_board(tmp.name)
    CASES.append(("kpcb sync art", ['kpcb.py', dp, 'sync', os.path.join(tmp.name, 'dup.net')], 0,
                  ["IN SYNC", "[INFO] SYNCART", "(3): REF** REF**~dup2 REF**~dup3", "[WARN] SYNCART",
                   "REF**~dup2 (Logo at 10.0,5.0 F) lacks board_only: Update PCB deletes it",
                   "REF**~dup3 (Logo at 15.0,5.0 B) lacks board_only", '!REF** (Logo']))
    # diff pairs by uuid: deleting the middle logo renumbers dup3 -> dup2, which is no change
    du = open(dp).read()
    for i, x in enumerate((5, 10, 15)):
        du = du.replace(f'(at {x} 5)', f'(at {x} 5) (uuid "u{i}")', 1)
    du0, du1 = os.path.join(tmp.name, 'du0.kicad_pcb'), os.path.join(tmp.name, 'du1.kicad_pcb')
    with open(du0, 'w') as fh:
        fh.write(du)
    with open(du1, 'w') as fh:
        fh.write(re.sub(r' \(footprint "Logo" \(layer "F.Cu"\) \(at 10 5\) \(uuid "u1"\).*?"F.SilkS"\)\)\)', '', du, count=1))
    CASES.append(("kpcb diff pairs by uuid", ['kpcb.py', du1, 'diff', du0], 0,
                  ["footprints: 0 moved, 0 rotated, 0 flipped, 0 added, 1 removed", "removed  REF**~dup2"]))
    sp = scale_board(tmp.name)
    CASES.append(("kpcb where scale+origin", ['kpcb.py', sp, 'where', 'S1', '--origin', 'grid'], 0,
                  ["relative to the grid origin 5,5", "at        : 5.000, 5.000  rot 0  layer F.Cu  scale 0.5 x 0.5",
                   "courtyard : 3.00,4.00 .. 7.00,6.00  (4.00 x 2.00 mm)", "fab body  : 3.50,4.50 .. 6.50,5.50"]))
    CASES.append(("kpcb where xy origin", ['kpcb.py', sp, 'where', '8,7', '--origin', 'aux', '-r', '0'], 0,
                  ["=== 8.00,7.00   inside the outline", "within 0 mm (1)"]))
    CASES.append(("kpcb summary origins", ['kpcb.py', sp, 'summary'], 0, ["origins: grid 5,5  aux 2,3"]))
    CASES.append(("kpcb zones --voids", ['kpcb.py', os.path.join(tmp.name, 'voids.kicad_pcb'), 'zones', '--voids'], 0,
                  ["B.Cu    void core", "rescue via at", "GND on F.Cu there, nothing foreign", _void_via]))
    CASES.append(("kpcb zones planes", ['kpcb.py', os.path.join(tmp.name, 'voids.kicad_pcb'), 'zones'], 0,
                  ["F.Cu     + 1 local pour(s) under 5%: +5V 0%", "F.Cu     GND         90%      1  18 mm, 1 net(s)       SIG 18",
                   "B.Cu     GND         66%      2  0 mm, 0 net(s)"]))
    CASES.append(("kpcb rf branch", ['kpcb.py', rfbranch_board(tmp.name), 'rf', 'RFX', '--freq', '5000'], 2,
                  ["branch off F.Cu track @10.00,5.00: 3.00 mm, 18 deg at 5000 MHz, ends in JP1.1 DNP  <-- OPEN STUB > lambda/50 (1.2 mm)"]))
    CASES.append(("kpcb refslots", ['kpcb.py', refslot_board(tmp.name), 'refslots'], 0,
                  ["refslots: 1 signal net(s)", "S                          F.Cu/In1  gnd  10.", "void/pad/via", ", X 0.8"]))
    yield
    import argparse, contextlib, io, kpcb_amp, kpcb_board, kpcb_height, kpcb_viapad, kpcb_zones, kzo                # the checks below call them in-process
    clr = kpcb_zones._clearance_fn(kpcb_board.Board(os.path.join(tmp.name, 'typed', 't.kicad_pcb')))[0]
    got = (clr('A', 'X'), clr('A', 'X', 'track', 'pad', 'F.Cu'), clr('A', 'W', 'track', 'track', 'F.Cu'),
           clr('RF1', 'X', 'track', 'pad', 'F.Cu'), clr('A', 'X', 'via', 'pad', 'F.Cu'))
    check(got == (0.15, 0.1, 0.127, 0.3, 0.15),
                   f"typed DRU clearance (netclass, pad-track, outer track-track, RF class kept, via-pad) = {got}")
    rd = os.path.join(tmp.name, 'rules')                 # Board.rules: first .kicad_pro, dru comments dropped
    os.makedirs(rd)
    open(os.path.join(rd, 'r.kicad_pcb'), 'w').write(open(PCB).read())
    open(os.path.join(rd, 'a.kicad_pro'), 'w').write('{"board": {"design_settings": {"rules": {"min_copper_edge_clearance": 0.4}}}}')
    open(os.path.join(rd, 'b.kicad_pro'), 'w').write('{"board": {"design_settings": {"rules": {"min_copper_edge_clearance": 0.9}}}}')
    open(os.path.join(rd, 'r.kicad_dru'), 'w').write('(version 1)\n# (rule "old" (constraint edge_clearance (min 1.0mm)))\n'
                                                     '(rule "e" (condition "A.Type == \'Via\'") (constraint hole_clearance (min 0.5mm)))\n')
    rb = kpcb_board.Board(os.path.join(rd, 'r.kicad_pcb'))
    import kpcb_route
    check(rb.edge_clearance() == 0.4 and kpcb_route._hole_clr(rb) == {'via': 0.5, 'pth': 0.2, 'npth': 0.2},
          "Board.rules: the first .kicad_pro only, a commented-out dru rule ignored, a condition before its constraint read")
    r = kpcb_amp.dt_rod(3.0, 0.3, 0.035, 1.5)
    ok6 = 0.95 < r < 1.1 and kpcb_amp.dt_ipc(kpcb_amp.ipc_current(0.3, 0.035, True, 10), 0.3, 0.035, True) - 10 < 1e-6
    check(ok6, f"ampacity rise model: rod {r:.2f} C, IPC inverse round-trip")
    vb = kpcb_board.Board(os.path.join(tmp.name, 'voids.kicad_pcb'))
    sl = kpcb_zones._slots(vb, 'F.Cu', 'GND', (5, 5, 15, 15))
    ok7 = len(sl) == 1 and sl[0][0] == 'SIG' and abs(sl[0][1][0] - 10) < 1e-6 and sl[0][1][2] == 'x=12.0' \
        and not kpcb_zones._slots(vb, 'F.Cu', 'GND', (0, 0, 20, 20), min_len=19)
    check(ok7, f"zones SLOT measure {sl}")
    vp = {'x': 0, 'y': 0, 'prot': 0, 'sx': 1, 'sy': 1, 'shape': 'roundrect', 'rr': 0.25, 'prims': [], 'mask': 0}
    dd = lambda x, y, m=0: kpcb_viapad.drill_depth({**vp, 'mask': m}, {'x': x, 'y': y, 'drill': 0.3})   # noqa: E731
    check(abs(dd(0.6, 0) - 0.05) < 1e-9 and dd(0.55, 0.55) < 0 and dd(0.6, 0, -0.05) < 1e-9
                   and kpcb_viapad.protection({'tenting': (1, 1), 'covering': (0, 0), 'plugging': (1, 1),
                                               'capping': False, 'filling': False})[0] == 'IV-b mask-plugged',
                   "viapad: drill vs the real pad shape + mask margin; tent + plug both sides = IV-b")
    z = kzo.microstrip(0.36, 0.203, 4.4, 0.035)[0]
    ok = 49.0 < z < 51.0
    check(ok, f"microstrip Zo {z:.1f} ohm")
    # rf's CPWG field solver vs exact stripline / CPW and Hammerstad microstrip,
    # and side grounds can only LOWER Zo (the closed forms got that backwards)
    zs = kzo._selftest()
    ms = kzo.field_zo(0.306, 0.203, 4.4, 0.035)[0]
    cp = [kzo.field_zo(0.306, 0.203, 4.4, 0.035, s=g)[0] for g in (0.15, 0.3, 1.0)]
    ok4 = all(abs(z - r) / r < 0.02 for _, z, r in zs) and cp[0] < cp[1] < cp[2] < ms
    check(ok4, "field solver " + ', '.join(f"{(z - r) / r * 100:+.1f}%" for _, z, r in zs)
          + f"; CPWG {cp[0]:.1f} < {cp[1]:.1f} < {cp[2]:.1f} < microstrip {ms:.1f}")
    # `height`'s glTF transform: 90 deg about Y (x,y,z,w quaternion) then +2 in Y
    M = kpcb_height._mat({'rotation': [0, 0.7071068, 0, 0.7071068], 'translation': [0, 2, 0]})
    p = [sum(M[r][c] * v for c, v in enumerate((1, 0, 0, 1))) for r in range(3)]
    ok2 = all(abs(x - y) < 1e-6 for x, y in zip(p, (0, 2, -1)))
    check(ok2, f"glTF node transform {[round(x, 3) for x in p]}")
    # duplicate refs: every footprint block becomes one Board entry, and a padless
    # logo's side is its art layer, not its (layer)
    db = kpcb_board.Board(dp)
    ok8 = len(db.fps) == open(dp).read().count('(footprint ') == 4 \
        and {'REF**', 'REF**~dup2', 'REF**~dup3'} <= set(db.fps) and not db.fps['REF**~dup3'].back
    check(ok8, f"Board keeps duplicate refs {sorted(db.fps)}")
    # `height` with no models loaded: R1 is UNKNOWN, the padless logos are not parts
    kpcb_height.heights = lambda b: ({}, [])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        kpcb_height.c_height(db, argparse.Namespace(args=[], height_cfg={}, max=8))
    nm = [x for x in buf.getvalue().splitlines() if 'NO 3D MODEL' in x]
    ok9 = len(nm) == 1 and nm[0].endswith(': R1')
    check(ok9, f"height skips padless art: {nm}")
    # the copper graph must not depend on the hash seed (set order)
    tp = tee_board(tmp.name)
    rs = {run(['kpcb.py', tp, 'ampacity', '--from', 'J1.1', '--to', 'J2.1', '--amps', '1'],
              {'PYTHONHASHSEED': str(sd)})[1].split('   R ')[1].split(' mohm')[0] for sd in range(8)}
    ok10 = rs == {'8.27'}
    check(ok10, f"copper graph independent of hash seed: R {sorted(rs)} mohm")
