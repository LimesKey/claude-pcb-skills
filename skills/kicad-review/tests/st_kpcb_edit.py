"""Self-test cases: kpcb.py placement and edit commands: edit, move, movecheck, place, silk, refdes, pinlabels, label, zoneshape, diff, ...

selftest.py runs suite(); see its docstring for the case format."""
import math, os
from st_common import CASES, _gzone, _tab_board, _tab_fp, _tseg, _tvia, _typed_dir, _tzone, check, rect, run


def tidy_board(d):
    """one near miss per tidy class: C3 0.08 mm off the C1/C2 row, R2 off an even
    pitch, TP1 at 60 deg, H4 inset 3.1 vs 3.0, D1 0.3 mm off U1's long centre line (an X
    track then sits 0.15 mm from its pads, so movecheck flags that one)"""
    p = os.path.join(d, 'tidy.kicad_pcb')
    def fp(ref, name, x, y, r=0, crt=(.5, .3), pads=(('1', -.4, 0), ('2', .4, 0)), drill=''):
        return (f' (footprint "{name}" (layer "F.Cu") (at {x} {y} {r}) (property "Reference" "{ref}")'
                f' (fp_rect (start {-crt[0]} {-crt[1]}) (end {crt[0]} {crt[1]}) (layer "F.CrtYd"))'
                + ''.join(f' (pad "{n}" {"thru_hole" if drill else "smd"} rect (at {px} {py}) (size .3 .3)'
                          f'{drill} (layers "F.Cu") (net "{ref}{n}"))' for n, px, py in pads) + ')')
    hole = lambda r, x, y: fp(r, 'MountingHole_3.2mm', x, y, crt=(2, 2), pads=(('1', 0, 0),), drill=' (drill 3.2)')
    open(p, 'w').write(
        '(kicad_pcb (version 20240108) (generator "pcbnew")'
        ' (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))'
        ' (gr_rect (start 0 0) (end 40 30) (layer "Edge.Cuts"))'
        + fp('C1', 'C_0402', 5, 10) + fp('C2', 'C_0402', 7, 10) + fp('C3', 'C_0402', 9, 10.08)
        + fp('R1', 'R_0603', 5, 15) + fp('R2', 'R_0603', 7.1, 15) + fp('R3', 'R_0603', 9, 15)
        + fp('TP1', 'TestPoint', 15, 15, 60)
        + hole('H1', 3, 3) + hole('H2', 37, 3) + hole('H3', 3, 27) + hole('H4', 36.9, 27)
        + fp('U1', 'Holder', 25, 10, crt=(10, 3)) + fp('D1', 'D_0402', 28, 10.3)
        + ' (segment (start 26 9.6) (end 30 9.6) (width 0.2) (layer "F.Cu") (net "X")))')
    return p


def stair_zone_board(d):
    """power_board plus a P zone whose hypotenuse (8,8) -> (2,2) is a 0.05 mm raster
    staircase, the shape `fatten` traced before 2026-10-19, with a stale fill"""
    st = ''.join(f'(xy {8 - k * .05:g} {8 - (k + 1) * .05:g}) (xy {8 - (k + 1) * .05:g} {8 - (k + 1) * .05:g}) '
                 for k in range(120))
    return _tab_board(d, 'stair.kicad_pcb', 20, 10,
                      '\t(zone\n\t\t(net "P")\n\t\t(layer "F.Cu")\n\t\t(uuid "zstair")\n\t\t(name "stair")\n'
                      f'\t\t(polygon\n\t\t\t(pts\n\t\t\t\t(xy 2 8) (xy 8 8) {st}\n\t\t\t)\n\t\t)\n'
                      '\t\t(filled_polygon\n\t\t\t(layer "F.Cu")\n\t\t\t(pts\n\t\t\t\t(xy 2 8) (xy 8 8) (xy 2 2)\n'
                      '\t\t\t)\n\t\t)\n\t)\n')


def shove_board(d):
    """12 x 2.5: R1 at 3 (its courtyard 2..4), C2 at 6.2 with a track on its pad 2, R3 far
    right, C1 parked: no spot within 2 mm of R1 fits until C2 moves 1.25 mm right"""
    return _tab_board(d, 'shove.kicad_pcb', 12, 2.5,
                      _tab_fp('R1', 3, 1.25, [('1', -.5, 0, .5, .5, 'A'), ('2', .5, 0, .5, .5, 'B')], (1, .5))
                      + _tab_fp('C2', 6.2, 1.25, [('1', -.5, 0, .5, .5, 'X'), ('2', .5, 0, .5, .5, 'Y')], (1, .5))
                      + _tab_fp('R3', 10.5, 1.25, [('1', -.5, 0, .5, .5, 'P'), ('2', .5, 0, .5, .5, 'Q')], (1, .5))
                      + _tab_fp('C1', 30, 1.25, [('1', -.5, 0, .5, .5, 'B'), ('2', .5, 0, .5, .5, 'GND')], (1, .5))
                      + _tseg(6.7, 1.25, 6.7, 2.2, 'Y'))


def pocket_board(d, h=0.5):
    """10 x 4: Z tracks (y 2 +- h) fence a pocket along y=2 (x 0..6, closed at x=6); TP9's
    GND pad placed in it reaches no GND copper. h 0.5: no legal via spot, boxed in. h 0.58:
    a 0.5/0.2 via fits, the class (here default) 0.6/0.3 route lays does not: boxed in too"""
    return _tab_board(d, f'pocket{h}.kicad_pcb', 10, 4,
                      _tab_fp('TP9', 30, 2, [('1', 0, 0, .3, .3, 'GND')], (.2, .2))
                      + _tseg(0.3, 2 - h, 6, 2 - h, 'Z') + _tseg(0.3, 2 + h, 6, 2 + h, 'Z') + _tseg(6, 2 - h, 6, 2 + h, 'Z'))


def padstack_board(d):
    """12 x 6: J1 (origin 9,3) has its N pad 3 x 1 at 3,3, outside its own courtyard (as an
    easyeda header's); TP9 (N) parked off-board. place --near 3,3 once put TP9 on J1.1"""
    return _tab_board(d, 'padstack.kicad_pcb', 12, 6,
                      _tab_fp('J1', 9, 3, [('1', -6, 0, 3, 1, 'N')], (.5, .5))
                      + _tab_fp('TP9', 30, 3, [('1', 0, 0, .6, .6, 'N')], (.4, .4)))


def freebox_board(d):
    """30 x 20 board: U1's courtyard over x 1..13, a logo over x 14..19, and board text
    "AB" anchored left-bottom at 25,2 - so a 6 x 4 box only fits right of x 19, below y 2;
    text "ZZ" off the board at x -6 (its raster cells clamp, not shrink a row)"""
    p = os.path.join(d, 'freebox.kicad_pcb')
    open(p, 'w').write(
        '(kicad_pcb (version 20240108) (generator "pcbnew")'
        ' (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))'
        ' (gr_rect (start 0 0) (end 30 20) (layer "Edge.Cuts"))'
        ' (gr_text "AB" (at 25 2 0) (layer "F.SilkS") (effects (font (size 1 1)) (justify left bottom)))'
        ' (gr_text "ZZ" (at -6 2 0) (layer "F.SilkS") (effects (font (size 1 1))))'
        ' (footprint "M" (layer "F.Cu") (at 7 10) (property "Reference" "U1")'
        ' (fp_rect (start -6 -9) (end 6 9) (layer "F.CrtYd"))'
        ' (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu") (net "A")))'
        ' (footprint "Logo" (layer "F.Cu") (at 16.5 10) (property "Reference" "REF**")'
        ' (fp_poly (pts (xy -2.5 -9) (xy 2.5 -9) (xy 2.5 9) (xy -2.5 9)) (layer "F.SilkS"))))')
    return p


def vcenter_board(d):
    """A: a track ending 0.15 mm off its via's centre (snaps), a 0.1 mm stub inside that via
    (goes); C: a track ending off-centre whose snap would tilt it into B's via at 9,11.5
    (skipped). Default clearance 0.2."""
    return _tab_board(d, 'vcenter.kicad_pcb', 20, 20,
                      _tseg(2, 5, 10.15, 5, 'A') + _tseg(9.95, 5, 10.05, 5, 'A') + _tvia(10, 5, 'A')
                      + _tseg(2, 12.2, 10.2, 12.2, 'C') + _tvia(10, 12, 'C') + _tvia(9, 11.5, 'B'))


def faceted_board(d):
    """20 x 10: za "fatten P", a 2 mm band (2,4)-(12,4) whose round ends are 15-degree chord
    runs (as fatten / route --pour wrote them before kpcb_fillet), and zb, a hand-drawn
    rectangle (no chord run: stays sharp, no fillet)"""
    def zone(uid, name, pts):
        xy = ''.join(f'\t\t\t\t(xy {x:.4f} {y:.4f})\n' for x, y in pts)
        return (f'\t(zone\n\t\t(net "P")\n\t\t(layer "F.Cu")\n\t\t(uuid "{uid}")\n\t\t(name "{name}")\n'
                f'\t\t(hatch edge 0.5)\n\t\t(connect_pads yes\n\t\t\t(clearance 0.2)\n\t\t)\n\t\t(min_thickness 0.25)\n'
                f'\t\t(fill yes\n\t\t\t(thermal_gap 0.5)\n\t\t\t(thermal_bridge_width 0.5)\n\t\t\t(island_removal_mode 0)\n'
                f'\t\t)\n\t\t(polygon\n\t\t\t(pts\n{xy}\t\t\t)\n\t\t)\n\t)\n')
    arc = lambda cx, a0: [(cx + math.cos(math.radians(a0 + 15 * k)), 4 + math.sin(math.radians(a0 + 15 * k)))  # noqa: E731
                          for k in range(13)]
    return _tab_board(d, 'faceted.kicad_pcb', 20, 10, zone('za', 'fatten P', arc(12, -90) + arc(2, 90))
                      + zone('zb', 'hand', [(14, 2), (18, 2), (18, 8), (14, 8)]))


def notch_board(d):
    """20 x 10: zr, a P zone (2,2)-(12,8) whose top edge notches round Q's pad at 7,2.4 along
    its 0.2 mm clearance, as a raster trace leaves it: `zoneshape --redraw` drops the notch"""
    return _tab_board(d, 'notch.kicad_pcb', 20, 10, _tab_fp('U1', 7, 2.4, [('1', 0, 0, 1, 1, 'Q')])
                      + _gzone('F.Cu', [(2, 2), (6.3, 2), (6.3, 3.1), (7.7, 3.1), (7.7, 2), (12, 2), (12, 8), (2, 8)],
                               None, 'band', net='P', uid='zr'))


def merge_board(d):
    """20 x 10: P zones za 'band' (2,2)-(10,6) and zb 'hand' (6,4)-(14,8), priority 2, overlapping
    in a 4 x 2 box (union: one 8-corner outline, 56 mm2); on B.Cu zc (a pair with za zonemerge refuses),
    and zd priority 3 over Q's zq priority 1 that out-ranks zc (zc + zd refused); zf F.Cu+B.Cu
    (15,1)-(19,5) under zg, an F.Cu band (17,3)-(19.5,9): merged on F.Cu, zf keeps B.Cu"""
    return _tab_board(d, 'merge.kicad_pcb', 20, 10, _gzone('F.Cu', rect(2, 2, 10, 6), None, 'band', net='P', uid='za')
                      + _gzone('F.Cu', rect(6, 4, 14, 8), None, 'hand', '\t\t(priority 2)\n', net='P', uid='zb')
                      + _gzone('B.Cu', rect(6, 4, 14, 8), None, 'back', net='P', uid='zc')
                      + _gzone('B.Cu', rect(5, 3, 8, 5), None, 'q', '\t\t(priority 1)\n', net='Q', uid='zq')
                      + _gzone('B.Cu', rect(8, 5, 12, 7), None, 'back hi', '\t\t(priority 3)\n', net='P', uid='zd')
                      + _gzone('F.Cu', rect(15, 1, 19, 5), None, 'hand2', '\t\t(priority 1)\n', net='P', uid='zf')
                      .replace('(layer "F.Cu")', '(layers "F.Cu" "B.Cu")', 1)
                      + _gzone('F.Cu', rect(17, 3, 19.5, 9), None, 'route P', '\t\t(priority 4)\n', net='P', uid='zg'))


def mvvia_board(d):
    """GND filled on F.Cu and B.Cu; a free GND via at 10,10 that a SIG track down x=10 now
    runs through (as after a chain is re-laid over it): mvvia must move it >= 0.6 mm"""
    v = _tvia(10, 10, 'GND').replace('\t\t(net "GND")', '\t\t(free yes)\n\t\t(net "GND")')
    return _tab_board(d, 'mvvia.kicad_pcb', 20, 20, _tseg(10, 2, 10, 18, 'SIG') + v.replace('(uuid "', '(uuid "vv')
                      + _tzone('GND', 'F.Cu', 1, 1, 19, 19, 'zf') + _tzone('GND', 'B.Cu', 1, 1, 19, 19, 'zb'))


def move_board(d):
    """R1 (pads A/B at 9.5/10.5,10) with its own A track running to 9.5,5; a foreign C
    track down x=12 (0.2 mm); a bare D via at 8,14. FID1 at 15,5, a 1 mm pad with its own
    (clearance 0.6), an E via 0.7 mm off it; TP1 at 4,4 already 0.15 mm from a G track
    (y 4.75). Default clearance 0.2, edge 0.3."""
    p = os.path.join(d, 'move.kicad_pcb')
    open(p, 'w').write(
        '(kicad_pcb (version 20240108) (generator "pcbnew")'
        ' (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))'
        ' (gr_rect (start 0 0) (end 20 20) (layer "Edge.Cuts"))'
        ' (footprint "R" (layer "F.Cu") (at 10 10) (property "Reference" "R1")'
        ' (fp_rect (start -1 -0.5) (end 1 0.5) (layer "F.CrtYd"))'
        ' (pad "1" smd rect (at -0.5 0) (size 0.5 0.5) (layers "F.Cu") (net "A"))'
        ' (pad "2" smd rect (at 0.5 0) (size 0.5 0.5) (layers "F.Cu") (net "B")))'
        ' (segment (start 9.5 10) (end 9.5 5) (width 0.2) (layer "F.Cu") (net "A"))'
        ' (segment (start 12 2) (end 12 18) (width 0.2) (layer "F.Cu") (net "C"))'
        ' (via (at 8 14) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "D"))'
        ' (footprint "Fid" (layer "F.Cu") (at 15 5) (property "Reference" "FID1")'
        ' (pad "" smd circle (at 0 0) (size 1 1) (layers "F.Cu" "F.Mask") (clearance 0.6)))'
        ' (via (at 16.5 5) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "E"))'
        ' (footprint "TP" (layer "F.Cu") (at 4 4) (property "Reference" "TP1")'
        ' (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu") (net "T")))'
        ' (segment (start 2 4.75) (end 8 4.75) (width 0.2) (layer "F.Cu") (net "G")))')
    return p


def silk_board(d):
    """L1: a logo under U1's 10 x 10 Fab body. L2: a B.Cu footprint whose art is on
    F.SilkS, running over R2's pad 1."""
    p = os.path.join(d, 'silk.kicad_pcb')
    logo = lambda r, x, side: (f' (footprint "Logo" (layer "{side}") (at {x} 10) (property "Reference" "{r}")'
                               ' (fp_poly (pts (xy -2 -1) (xy 2 -1) (xy 2 1) (xy -2 1)) (layer "F.SilkS")))')
    open(p, 'w').write(
        '(kicad_pcb (version 20240108) (generator "pcbnew")'
        ' (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))'
        ' (gr_rect (start 0 0) (end 40 20) (layer "Edge.Cuts"))'
        ' (footprint "Module" (layer "F.Cu") (at 10 10) (property "Reference" "U1")'
        ' (fp_rect (start -5 -5) (end 5 5) (layer "F.Fab"))'
        ' (pad "1" smd rect (at -4.5 4.5) (size 0.5 0.5) (layers "F.Cu") (net "A")))'
        ' (footprint "R" (layer "F.Cu") (at 26 10) (property "Reference" "R2")'
        ' (pad "1" smd rect (at -0.5 0) (size 0.5 0.5) (layers "F.Cu") (net "A"))'
        ' (pad "2" smd rect (at 0.5 0) (size 0.5 0.5) (layers "F.Cu") (net "B")))'
        + logo('L1', 10, 'F.Cu') + logo('L2', 24, 'B.Cu') + ')')
    return p


def drag_board(d):
    """R1 (pads A at 9.5,10 / B at 10.5,10, 0.6 mm) with a 0.4 mm A via in pad 1; an F.Cu A
    track from 9.25,10.2 (in pad 1, off the via) to 5,10.2; a B.Cu A track from the via
    centre to 9.5,14; a B.Cu A track ending at 9.75,9.8 (under pad 1, off the via: B.Cu,
    so it must not drag); a C track at y 10.75 x 7..8.5 that the F.Cu leg swings into
    when R1 moves up 0.5"""
    import uuid as U
    via = (f'\t(via\n\t\t(at 9.5 10)\n\t\t(size 0.4)\n\t\t(drill 0.2)\n\t\t(layers "F.Cu" "B.Cu")\n'
           f'\t\t(net "A")\n\t\t(uuid "{U.uuid4()}")\n\t)\n')
    return _tab_board(d, 'drag.kicad_pcb', 20, 20,
                      _tab_fp('R1', 10, 10, [('1', -0.5, 0, .6, .6, 'A'), ('2', 0.5, 0, .6, .6, 'B')], (1, .5))
                      + via + _tseg(9.25, 10.2, 5, 10.2, 'A') + _tseg(9.5, 10, 9.5, 14, 'A', ly='B.Cu')
                      + _tseg(9.75, 9.8, 13, 6, 'A', ly='B.Cu') + _tseg(7, 10.75, 8.5, 10.75, 'C'))


def _silk_fp(ref, x, y, pads, ref_at=(0, -1.5, 0), size=1, thick=0.15, fab=None, crt=(.9, .5), user=()):
    import uuid as U
    u = lambda: f'(uuid "{U.uuid4()}")'                 # noqa: E731
    fb = ''.join(f'\t\t(fp_text user "{txt}"\n\t\t\t(at {ux} {uy} 0)\n\t\t\t(layer "F.SilkS")\n\t\t\t(uuid "{uu}")\n'
                 f'\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1 1)\n\t\t\t\t\t(thickness 0.15)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n'
                 for txt, ux, uy, uu in user)
    fb += (f'\t\t(fp_rect\n\t\t\t(start {-fab[0]} {-fab[1]})\n\t\t\t(end {fab[0]} {fab[1]})\n\t\t\t(stroke\n'
          f'\t\t\t\t(width 0.1)\n\t\t\t\t(type solid)\n\t\t\t)\n\t\t\t(layer "F.Fab")\n\t\t\t{u()}\n\t\t)\n') if fab else ''
    return (f'\t(footprint "x:P"\n\t\t(layer "F.Cu")\n\t\t{u()}\n\t\t(at {x} {y})\n'
            f'\t\t(property "Reference" "{ref}"\n\t\t\t(at {ref_at[0]} {ref_at[1]} {ref_at[2]})\n\t\t\t(layer "F.SilkS")\n'
            f'\t\t\t{u()}\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size {size} {size})\n\t\t\t\t\t(thickness {thick})\n'
            f'\t\t\t\t)\n\t\t\t)\n\t\t)\n'
            f'\t\t(property "Value" "V{ref}"\n\t\t\t(at 0 1.5 0)\n\t\t\t(layer "F.Fab")\n\t\t\t{u()}\n'
            f'\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1 1)\n\t\t\t\t\t(thickness 0.15)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n'
            f'\t\t(fp_rect\n\t\t\t(start {-crt[0]} {-crt[1]})\n\t\t\t(end {crt[0]} {crt[1]})\n\t\t\t(stroke\n'
            f'\t\t\t\t(width 0.05)\n\t\t\t\t(type solid)\n\t\t\t)\n\t\t\t(layer "F.CrtYd")\n\t\t\t{u()}\n\t\t)\n' + fb
            + ''.join(f'\t\t(pad "{n}" smd rect\n\t\t\t(at {dx} {dy})\n\t\t\t(size {sx} {sy})\n\t\t\t(layers "F.Cu" "F.Mask")\n'
                      f'\t\t\t(net "{net}")\n\t\t\t{u()}\n\t\t)\n' for n, dx, dy, sx, sy, net in pads) + '\t)\n')


def silk_art_board(d):
    """typed rules (min text 1.0/0.15). U5: a module with no Fab layer (body = courtyard, its
    designator at its centre: UNDER); P1: a 6 x 6 SMD pad far outside its 0.4 mm courtyard
    (freebox must not offer it); a filled board poly at 20..24,2..6 with board text 'AB' on
    it (OVERLAP); 'TTF' in DIN at 1.2 mm (SIZE); 'RC' justified left bottom at 5,18 whose
    render_cache spans 5..7, 16.5..18 (the box)"""
    sd = _typed_dir(os.path.join(d, 'silkart'))
    gt = lambda txt, x, y, extra='', font='': (f'\t(gr_text "{txt}"\n\t\t(at {x} {y} 0)\n\t\t(layer "F.SilkS")\n'  # noqa: E731
                                              f'\t\t(uuid "gt{txt}")\n\t\t(effects\n\t\t\t(font\n{font}\t\t\t\t(size 1.2 1.2)\n'
                                              f'\t\t\t\t(thickness 0.2)\n\t\t\t)\n{extra}\t\t)\n\t)\n')
    din = '\t\t\t\t(face "DIN Mittelschrift Std")\n'
    rc = ('\t\t\t(justify left bottom)\n\t\t)\n\t\t(render_cache "RC" 0\n\t\t\t(polygon\n\t\t\t\t(pts\n'
          '\t\t\t\t\t(xy 5 16.5) (xy 7 16.5) (xy 7 18) (xy 5 18)\n\t\t\t\t)\n\t\t\t)\n')
    poly = ('\t(gr_poly\n\t\t(pts\n\t\t\t(xy 20 2) (xy 24 2) (xy 24 6) (xy 20 6)\n\t\t)\n\t\t(stroke\n'
            '\t\t\t(width 0.1)\n\t\t\t(type solid)\n\t\t)\n\t\t(fill yes)\n\t\t(layer "F.SilkS")\n\t\t(uuid "art1")\n\t)\n')
    return _tab_board(sd, 't.kicad_pcb', 30, 20,
                      _silk_fp('U5', 8, 8, [('1', -3.5, 0, .6, .6, 'A'), ('2', 3.5, 0, .6, .6, 'B')],
                               ref_at=(0, 0, 0), crt=(4, 4))
                      + _silk_fp('P1', 15, 15, [('1', 4, 0, 6, 6, 'C')], ref_at=(0, -1.2, 0), crt=(.4, .4))
                      + _silk_fp('J1', 27, 9, [('1', 0, -1.27, 1, 1, 'VCC'), ('2', 0, 1.27, 1, 1, 'Net-(F1-Pad2)')],
                                 ref_at=(0, -3, 0), crt=(.6, 1.9))
                      + _silk_fp('F1', 26, 16, [('1', -.5, 0, .6, .6, 'Net-(F1-Pad2)'), ('2', .5, 0, .6, .6, '/Pwr/VBAT')],
                                 ref_at=(0, 1.5, 0))
                      + poly + gt('AB', 22, 4) + gt('TTF', 14, 3, font=din) + gt('RC', 5, 18, rc, din))


def silk_review_board(d):
    """beside typed_board's rules (min text 1.0/0.15): R1's designator on its own pads
    (PAD), U1's inside its own Fab body (UNDER), R2's upside down at 0.8/0.1 (ORIENT, SIZE)"""
    sd = _typed_dir(os.path.join(d, 'silkrev'))
    two = lambda a, b: [('1', -0.5, 0, .6, .6, a), ('2', 0.5, 0, .6, .6, b)]   # noqa: E731
    return _tab_board(sd, 't.kicad_pcb', 30, 20,
                      _silk_fp('R1', 5, 5, two('A', 'B'), ref_at=(0, 0, 0))
                      + _silk_fp('U1', 15, 10, [('1', -2.5, -2.5, .6, .6, 'A'), ('2', 2.5, 2.5, .6, .6, 'B')],
                                 ref_at=(0, 0, 0), fab=(3, 3), crt=(3.3, 3.3))
                      + _silk_fp('R2', 25, 5, two('C', 'D'), ref_at=(0, -1.5, 180), size=0.8, thick=0.1))


def utext_board(d):
    """JP1 with user texts '1' (ut1) and '3' (ut3), a knockout board text 'KO' (gtKO)"""
    sd = _typed_dir(os.path.join(d, 'utext'))
    return _tab_board(sd, 't.kicad_pcb', 30, 20,
                      _silk_fp('JP1', 10, 10, [('1', -1, 0, .6, .6, 'A'), ('3', 1, 0, .6, .6, 'B')],
                               user=[('1', -2.2, 0, 'ut1'), ('3', 2.2, 0, 'ut3')], crt=(1.5, .5))
                      + '\t(gr_text "KO"\n\t\t(at 20 5 0)\n\t\t(layer "F.SilkS" knockout)\n\t\t(uuid "gtKO")\n'
                        '\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.5 1.5)\n\t\t\t\t(thickness 0.2)\n\t\t\t)\n\t\t)\n\t)\n')


def suite(tmp, mini):
    """Append this file's cases to CASES, yield while the runner runs them, then do the
    ad-hoc checks (the full run only: -k stops at the yield)."""
    T = lambda n: os.path.join(tmp.name, n)             # noqa: E731
    CASES.append(("kpcb edit vcenter", ['kpcb.py', vcenter_board(tmp.name), 'edit', 'vcenter', 'all', '-o',
                                        os.path.join(tmp.name, 'vc2.kicad_pcb')], 0,
                  ["vcenter: 1 track end(s) snapped to the via centre, 1 zero-length segment(s) deleted, "
                   "1 skipped (the snap breaks clearance)"]))
    CASES.append(("kpcb edit mvvia", ['kpcb.py', mvvia_board(tmp.name), 'edit', 'mvvia', 'vv', '2.5', '-o',
                                      os.path.join(tmp.name, 'mv2.kicad_pcb')], 0,
                  ["mvvia vv", "GND 0.6/0.3 free 10.000,10.000 -> ", "GND vias within 3 mm 1 -> 1"]))
    CASES.append(("kpcb tidy", ['kpcb.py', tidy_board(tmp.name), 'tidy'], 0,
                  ["5 tidy suggestion(s)", "C3     9.000,10.080 -> 9.000,10.000   y to the row of C1 C2 (0.080 off)",
                   "R2     7.100,15.000 -> 7.000,15.000   even 2.000 pitch along x between R1 and R3",
                   "H4     36.900,27.000 -> 37.000,27.000   x inset 3.100 -> 3.000 mm like H1 H2 H3",
                   "TP1    15.000,15.000 rot 60 -> 15.000,15.000 rot 90",
                   "D1     28.000,10.300 -> 28.000,10.000   0.300 off U1's long centre line y=10.000",
                   "movecheck: 2 new hit(s): D1.1 0.15 mm from a X track", "4 of the shown suggestions are clear"]))
    CASES.append(("kpcb freebox", ['kpcb.py', freebox_board(tmp.name), 'freebox', 'f', '6', '4'], 0,
                  ["1 region(s)", "centre   24.12,10.38    margin 1.75 mm  (region   52.0 mm2"]))
    mv = move_board(tmp.name)
    CASES.append(("kpcb movecheck hit", ['kpcb.py', mv, 'movecheck', 'R1', '11', '10'], 2,
                  ["NEW   R1.2 0.15 mm from a C track on F.Cu @12.00,10.00, needs 0.20", "1 own track(s) drag"]))
    CASES.append(("kpcb movecheck clear", ['kpcb.py', mv, 'movecheck', 'R1', '10.5', '10'], 0, ["CLEAR: nothing new"]))
    CASES.append(("kpcb movecheck scan", ['kpcb.py', mv, 'movecheck', 'R1', '--scan', 'y=10', 'x=9..12', '--step', '0.25'], 0,
                  ["x    9.000 ..   10.750  clear", "x   11.000 ..   12.000  blocked by a C track"]))
    CASES.append(("kpcb movecheck pad clearance", ['kpcb.py', mv, 'movecheck', 'FID1', '15.3', '5'], 2,
                  ["NEW   FID1. 0.40 mm from a E via @16.50,5.00, needs 0.60"]))
    CASES.append(("kpcb movecheck still", ['kpcb.py', mv, 'movecheck', 'TP1', '--scan', 'x=4', 'y=3..4', '--step', '0.25'], 0,
                  ["the current spot already has 1 hit(s), e.g. TP1.1 0.15 mm from a G track", "y    3.000 ..    3.750  clear",
                   "y    4.000 ..    4.000  blocked by a G track on F.Cu @5.00,4.75"]))
    CASES.append(("kpcb movecheck via", ['kpcb.py', mv, 'movecheck', 'via', '8,14', '8,15'], 0,
                  ["a bare stitching via, free to move", "CLEAR: nothing new"]))
    CASES.append(("kpcb edit simplify", ['kpcb.py', stair_zone_board(tmp.name), 'edit', 'simplify', 'zstair', '0.0625',
                                         '-o', T('stair2.kicad_pcb')], 0,
                  ["simplify zstair 242 -> 3 corner(s)", "(1 stale fill polygon(s) dropped: refill)"]))
    CASES.append(("kpcb edit del zone", ['kpcb.py', os.path.join(tmp.name, 'stair.kicad_pcb'), 'edit', 'del', 'zstair',
                                         '-o', T('stair3.kicad_pcb')], 0, ["del   zstair (zone)"]))
    sh = shove_board(tmp.name)
    CASES.append(("kpcb place --shove", ['kpcb.py', sh, 'place', 'C1', '--near', 'R1', '-r', '2', '--side', 'f', '--shove'], 0,
                  ["shove: ", "move C2 +1.25,+0.00 to 7.45,1.25"]))
    CASES.append(("kpcb place --shove write", ['kpcb.py', sh, 'place', 'C1', '--near', 'R1', '-r', '2', '--side', 'f', '--shove',
                                               '-o', T('sh2.kicad_pcb')], 0,
                  ["wrote C2 -> 7.450,1.250 (1 track end(s) dragged), then C1 -> 5.250,1.250"]))
    CASES.append(("kpcb place --shove result", ['kpcb.py', T('sh2.kicad_pcb'), 'check', '--only', 'OVERLAP,EDGECLR'], 0,
                  ["0 error, 0 warn"]))
    CASES.append(("kpcb place not on a pad", ['kpcb.py', padstack_board(tmp.name), 'place', 'TP9', '--near', '3,3', '-r',
                                              '1.5', '--side', 'f', '-o', T('padstack2.kicad_pcb')], 0,
                  ["wrote TP9 -> 3.000,2.000 rot 0 F"]))
    CASES.append(("kpcb place escape", ['kpcb.py', pocket_board(tmp.name), 'place', 'TP9', '--near', '3,2', '-r', '0.5',
                                        '--side', 'f'], 2, ["boxed in: TP9.1 (GND)", "skipped: a pad there reaches neither"]))
    CASES.append(("kpcb place escape class via", ['kpcb.py', pocket_board(tmp.name, 0.58), 'place', 'TP9', '--near', '3,2',
                                                  '-r', '0.5', '--side', 'f'], 2, ["boxed in: TP9.1 (GND)"]))
    CASES.append(("kpcb silk logos", ['kpcb.py', silk_board(tmp.name), 'silk'], 0,
                  ["HIDDEN under U1", "[footprint layer B.Cu, art on F]", "crosses 1 F-side pad(s): R2.1",
                   "logo L1 100% under U1's body"]))
    os.makedirs(T('mvw'))
    CASES.append(("kpcb no-project warning", ['kpcb.py', move_board(T('mvw')), 'movecheck', 'R1', '10.5', '10'], 0,
                  ["WARN: no .kicad_pro beside the board - kpcb's netclasses and clearances use"]))
    db = drag_board(tmp.name)
    CASES.append(("kpcb move drag layers+via", ['kpcb.py', db, 'move', 'R1', '10.5', '10', '-o', T('drag2.kicad_pcb')], 0,
                  ["dragged 2 track end(s)", "moved 1 via(s) inside its pads with it"]))
    CASES.append(("kpcb movecheck dragged segment", ['kpcb.py', db, 'movecheck', 'R1', '10', '10.5'], 2,
                  ["NEW   dragged A F.Cu", "from a C track on F.Cu"]))
    CASES.append(("kpcb movecheck --no-drag", ['kpcb.py', db, 'movecheck', 'R1', '10', '10.5', '--no-drag'], 0,
                  ["--no-drag (Move, M)", "left behind: 1 track end(s) on its pads, 1 via(s) in them", "CLEAR: nothing new"]))
    CASES.append(("kpcb move --no-drag", ['kpcb.py', db, 'move', 'R1', '10', '10.5', '--no-drag', '-o', T('drag3.kicad_pcb')], 0,
                  ["1 track end(s) on its pads stay behind (--no-drag)"]))
    CASES.append(("kpcb move --no-drag result", ['kpcb.py', T('drag3.kicad_pcb'), 'diff', db], 0,
                  ["moved    R1 +0.000,+0.500", "identical: vias (1)"]))
    dv = _tab_board(_typed_dir(T('dv')), 't.kicad_pcb', 14, 10,     # A via 0.2 into TP1, a B.Cu run to TP2 (B.Cu)
                    _tab_fp('TP1', 5, 5, [('1', 0, 0, .6, .6, 'A')])
                    + _tab_fp('TP2', 10, 5, [('1', 0, 0, .6, .6, 'A')]).replace('"F.Cu"', '"B.Cu"')
                    + _tvia(5.25, 5, 'A').replace('(uuid "', '(uuid "dv1', 1) + _tseg(5.25, 5, 10, 5, 'A', 0.3, 'B.Cu')
                    + _tseg(5.25, 5, 5.25, 5.1, 'A', 0.3, 'In1.Cu') + _tseg(5.25, 5.1, 5.3, 5.15, 'A', 0.3, 'In1.Cu'))
    CASES.append(("kpcb edit dragvia auto", ['kpcb.py', dv, 'edit', 'dragvia', 'dv1', 'auto', '-o', T('dv/d2.kicad_pcb')], 0,
                  ["dragvia dv1", "-> 5.45,5 (0.20 mm): 1 track(s) dragged, 2 in-via sliver(s) folded away"]))
    CASES.append(("kpcb edit dragvia stub", ['kpcb.py', dv, 'edit', 'dragvia', 'dv1', '5.8,5', '-o', T('dv/d3.kicad_pcb')], 0,
                  ["-> 5.8,5 (0.55 mm)", "stub 0.3 mm F.Cu from TP1.1"]))
    CASES.append(("kpcb edit dragvia refuses a pad", ['kpcb.py', dv, 'edit', 'dragvia', 'dv1', '5.3,5', '-o', T('dv/d4.kicad_pcb')], 1,
                  ["its drill still reaches into a pad's mask opening; nothing written"]))
    tdz = ('\t(zone\n\t\t(net "A")\n\t\t(layer "In1.Cu")\n\t\t(uuid "dwz")\n\t\t(attr\n\t\t\t(teardrop\n'
           '\t\t\t\t(type padvia)\n\t\t\t)\n\t\t)\n\t\t(polygon\n\t\t\t(pts\n\t\t\t\t(xy 4.8 4.8) (xy 5.4 4.8)'
           ' (xy 5.4 5.2) (xy 4.8 5.2)\n\t\t\t)\n\t\t)\n\t)\n')
    dw = _tab_board(_typed_dir(T('dw')), 't.kicad_pcb', 14, 10,  # a via in NO pad, an In1 sliver under a teardrop
                    _tab_fp('TP2', 10, 5, [('1', 0, 0, .6, .6, 'A')]).replace('"F.Cu"', '"B.Cu"')
                    + _tvia(5, 5, 'A').replace('(uuid "', '(uuid "dw1', 1) + _tseg(5, 5, 10, 5, 'A', 0.3, 'B.Cu')
                    + _tseg(5, 5, 5, 5.05, 'A', 0.3, 'In1.Cu') + tdz)
    CASES.append(("kpcb edit dragvia folds + drops one teardrop once", ['kpcb.py', dw, 'edit', 'dragvia', 'dw1', '5.2,5',
                                                                       '-o', T('dw/d2.kicad_pcb')], 0,
                  ["1 in-via sliver(s) folded away, 1 teardrop(s) dropped", "edit: 1 op(s)"]))
    CASES.append(("kpcb edit via on a track end is not free", ['kpcb.py', dw, 'edit', 'seg', 'A', 'F.Cu', '0.2', '10,5', '12,5',
                                                              'via', 'A', '12,5', '0.6/0.3', '-o', T('dw/d3.kicad_pcb')], 0,
                  ["via   A 12,5 0.6/0.3 (tracked: a track end lands in it)"]))
    fz = faceted_board(tmp.name)
    CASES.append(("kpcb edit unround", ['kpcb.py', fz, 'edit', 'unround', 'all', 'unround', 'zb', '-o', T('faceted2.kicad_pcb')], 0,
                  ["unround za fatten P: 26 -> 8 pts, outline +0.200 -0.000 mm2", "unround all: 1 zone(s)",
                   "unround zb hand: no arc runs"]))
    CASES.append(("kpcb edit unround again", ['kpcb.py', T('faceted2.kicad_pcb'), 'edit', 'unround', 'za', '-o',
                                              T('faceted3.kicad_pcb')], 0, ["za fatten P: already (smoothing fillet)"]))
    CASES.append(("kpcb zoneshape lint", ['kpcb.py', fz, 'zoneshape'], 0,
                  ["2 zone(s), 1 not hand-drawn style", "1 over a designer's bar", "za        P                  F.Cu     26    24    24    2  26 -> 8 pts  [fatten P]"]))
    CASES.append(("kpcb zoneshape one", ['kpcb.py', fz, 'zoneshape', 'za'], 0,
                  ["vertices 26 -> 8, off-45 edges 24 -> 0, micro-edges 24 -> 0, faceted arcs 2 -> 0; corners now sharp",
                   "outline moved <= 0.086 mm", "geometry ok"]))
    CASES.append(("kpcb zoneshape clean", ['kpcb.py', fz, 'zoneshape', 'hand'], 0, ["already clean"]))
    CASES.append(("kpcb zoneshape --over-bar", ['kpcb.py', fz, 'zoneshape', '--over-bar'], 0,
                  ["1 zone(s) over a designer's bar", "za        P                  F.Cu     26 -> 8    pts, off-45 24 -> 0",
                   "-o OUT writes the 1 proposal(s)"]))
    zm = merge_board(tmp.name)
    CASES.append(("kpcb zonemerge", ['kpcb.py', zm, 'zonemerge', 'za', 'zb'], 0,
                  ["zonemerge za 'band' (priority 0) into zb 'hand' (priority 2)", "4 + 4 -> 8 vertices, off-45 edges 0",
                   "area 32.00 + 32.00 -> 56.00 mm2", "geometry ok"]))
    CASES.append(("kpcb zonemerge refuses no shared layer", ['kpcb.py', zm, 'zonemerge', 'za', 'zc'], 2,
                  ["refused, no shared layer (F.Cu / B.Cu)"]))
    CASES.append(("kpcb zonemerge splits a two-layer zone", ['kpcb.py', zm, 'zonemerge', 'zf', 'zg'], 0,
                  ["zonemerge zf 'hand2' (priority 1) into zg 'route P' (priority 4), P F.Cu",
                   "zf 'hand2' keeps B.Cu as it is", "area 15.00 + 16.00 -> 27.00 mm2"]))
    CASES.append(("kpcb zonemerge refuses a zone ranked between", ['kpcb.py', zm, 'zonemerge', 'zc', 'zd'], 2,
                  ["refused, zq 'q' (priority 1) ranks between them over that area"]))
    CASES.append(("kpcb zoneshape redraw", ['kpcb.py', notch_board(tmp.name), 'zoneshape', 'zr', '--redraw'], 0,
                  ["redrawn along the copper", "vertices 8 -> 4", "geometry ok"]))
    CASES.append(("kpcb tracks zonepts", ['kpcb.py', fz, 'tracks', '--kind', 'zonepts'], 0,
                  ["zones hard to edit        1 visible", "'fatten P' 26 corners, 24 edge(s) < 0.3 mm", '!corners, acute']))
    srb = silk_review_board(tmp.name)
    CASES.append(("kpcb silk review", ['kpcb.py', srb, 'silk'], 0,
                  ["R1's designator over R1.1", "U1's designator under its own body",
                   "R2's designator at 180 deg reads upside down", "R2's designator 0.8/0.1 mm under the 1/0.15 minimum"]))
    sab = silk_art_board(tmp.name)
    CASES.append(("kpcb silk art/ttf/body", ['kpcb.py', sab, 'silk'], 0,
                  ["U5's designator under its own body", "board text 'AB' over board art",
                   "board text 'TTF' TrueType at 1.2 mm: glyph stroke under the 0.15 mm minimum (needs >= ~1.3 mm)"]))
    CASES.append(("kpcb pinlabels", ['kpcb.py', sab, 'pinlabels', 'J1', '-o', T('silkart/pl.kicad_pcb')], 0,
                  ["pinlabels J1: 1=VCC 2=VBAT", "F side, -x of the pads at ", "wrote 2 text(s)"]))
    CASES.append(("kpcb pinlabels result", ['kpcb.py', T('silkart/pl.kicad_pcb'), 'silk', 'J1'], 0, ["'VBAT'", "'VCC'"]))
    CASES.append(("kpcb pinlabels --table", ['kpcb.py', sab, 'pinlabels', 'J1', '--table', 'PWR', '--title-col',
                                              '-o', T('silkart/tb.kicad_pcb')], 0,
                  ["-x of the pads at 0.42 mm: 7.10 x 5.08 mm, 2 row(s) on the 2.54 mm pitch, title 'PWR' as a column",
                   "wrote 1 table (4 cells)"]))
    CASES.append(("kpcb table read by silk", ['kpcb.py', T('silkart/tb.kicad_pcb'), 'silk', '--box', '20,6,28,12'], 0,
                  ["table cell           'VCC'", "table cell           'PWR'", "1/0.15 knockout"]))
    CASES.append(("kpcb table diff", ['kpcb.py', T('silkart/tb.kicad_pcb'), 'diff', sab], 0,
                  ["board silk items 4 -> 5, 1 new/changed; table cells 3 added, 0 removed"]))
    CASES.append(("kpcb label --near", ['kpcb.py', sab, 'label', 'PWR', '--near', 'J1'], 0,
                  ["label 'PWR' F at ", "J1's designator hidden"]))
    CASES.append(("kpcb silk list", ['kpcb.py', srb, 'silk', 'R1'], 0, ["R1 designator", "(pad"]))
    ub = utext_board(tmp.name)
    CASES.append(("kpcb silk list user texts", ['kpcb.py', ub, 'silk', '--box', '0,0,30,20'], 0,
                  ["JP1 user             '1'", "[ut1]", "1.5/0.2 knockout  [gtKO]"]))
    CASES.append(("kpcb edit user text/knockout/retext/addtext",
                  ['kpcb.py', ub, 'edit', 'text', 'ut1', '7.5,10', 'keep', 'del', 'ut3', 'knockout', 'gtKO', 'off',
                   'retext', 'gtKO', 'OK', 'knockout', 'JP1', 'on', 'addtext', 'GPIO', '20,15', '0', 'f', '1.2',
                   '-o', T('utext/u2.kicad_pcb')], 0,
                  ["del   ut3 (footprint user text)", "retext gtKO -> 'OK'", "addtext 'GPIO' 20,15 0 deg F.SilkS 1.2 mm"]))
    CASES.append(("kpcb edit refuses a designator by uuid", ['kpcb.py', ub, 'edit', 'del', 'ut', '-o', T('utext/u3.kicad_pcb')],
                  1, ["matches 2 board/footprint text(s); nothing written"]))
    CASES.append(("kpcb diff silk restyle", ['kpcb.py', T('utext/u2.kicad_pcb'), 'diff', ub], 0,
                  ["visible text changed on 1 footprint(s) (1 of them did not move)", "JP1: Reference knockout on, user moved, user removed",
                   "1 board text(s) restyled in place", "board text 'OK': text knockout off"]))
    CASES.append(("kpcb refdes", ['kpcb.py', srb, 'refdes', '-o', T('silkrev/t2.kicad_pcb')], 0,
                  ["refdes: 3 of 3 designator(s) get a clear spot", "wrote "]))
    CASES.append(("kpcb refdes result", ['kpcb.py', T('silkrev/t2.kicad_pcb'), 'silk', '--only',
                                         'SILK-PAD,SILK-UNDER,SILK-ORIENT,SILK-SIZE'], 0, ["silk 0 error, 0 warn, 0 info"]))
    CASES.append(("kpcb edit silk ops", ['kpcb.py', srb, 'edit', 'ref', 'R1', '5,3.5', '0', 'hide', 'R2', 'textsize',
                                         'U1', '1.2', '0.18', '-o', T('silkrev/t3.kicad_pcb')], 0,
                  ["ref   R1 5,3.5 0", "hide  R2", "edit: 3 op(s)"]))
    CASES.append(("kpcb edit value ops", ['kpcb.py', srb, 'edit', 'value', 'R1', '5,7', '0', 'hide-value', 'R2',
                                          'valuesize', 'U1', '0.8', '0.12', '-o', T('silkrev/t4.kicad_pcb')], 0,
                  ["value R1 5,7 0", "hide-value R2", "valuesize U1 0.8 0.12", "edit: 3 op(s)"]))
    CASES.append(("kpcb view --layers silk", ['kpcb.py', srb, 'view', 'R1', '--layers', 'silk', '-o', T('silk.png')], 0,
                  ["F silk from the model"]))
    CASES.append(("kpcb edit text keep shifts the render_cache", ['kpcb.py', sab, 'edit', 'text', 'gtRC', '6,18', 'keep',
                                                                  '-o', T('silkart/rc2.kicad_pcb')], 0, ["text  gtRC -> 6,18 keep"]))
    yield
    import kpcb_board, kpcb_edit, kpcb_freebox, kpcb_place                # the checks below call them in-process
    ab = kpcb_board.Board(sab)
    rcb = next(x['box'] for x in ab.silktexts if x['text'] == 'RC')
    og, ox, oy = kpcb_freebox.occupancy(ab, False)
    check(rcb == (5.0, 16.5, 7.0, 18.0) and og[int((15 - oy) / 0.25)][int((19 - ox) / 0.25)] == 1,
                   f"TTF render_cache is the text box {rcb}; freebox counts P1's SMD pad outside its courtyard")
    wb2 = os.path.join(tmp.name, 'w2.kicad_pcb')                 # fixlines output, above
    bb, tt = kpcb_board.Board(wb2), kpcb_edit.PcbText(wb2)
    G = lambda f: type('G', (), {'ref': f.ref, 'x': f.x + 1, 'y': f.y, 'rot': f.rot + 90})()   # noqa: E731
    ok7 = all(kpcb_edit.flip_text(kpcb_edit.flip_text(tt.text(f.uuid), f), f) == tt.text(f.uuid) and
              kpcb_edit.place_text(kpcb_edit.place_text(tt.text(f.uuid), f, f.x + 1, f.y, f.rot + 90), G(f),
                                   f.x, f.y, f.rot) == tt.text(f.uuid) for f in bb.fps.values())
    for f in bb.fps.values():
        tt.sub(f.uuid, kpcb_edit.flip_text(tt.text(f.uuid), f))
    tt.save(os.path.join(tmp.name, 'wflip.kicad_pcb'))
    fb = kpcb_board.Board(os.path.join(tmp.name, 'wflip.kicad_pcb'))
    ok7 &= all(abs(q['x'] - (2 * f.x - p['x'])) < 1e-9 and abs(q['y'] - p['y']) < 1e-9 and fb.fps[r].back != f.back
               for r, f in bb.fps.items() for p, q in zip(f.pads, fb.fps[r].pads))
    check(ok7, "writers: flip / move+rotate round trips exact, flipped pads mirrored")
    nocli = {'KICAD_CLI': 'no-such-kicad-cli'}                 # the writes only: the refill is the goldens' job
    zm, zmo, fzo = (os.path.join(tmp.name, n) for n in ('merge.kicad_pcb', 'merge2.kicad_pcb', 'overbar.kicad_pcb'))
    code, out = run(['kpcb.py', zm, 'zonemerge', 'za', 'zb', '-o', zmo], nocli)
    mz = kpcb_board.Board(zmo).zones if os.path.exists(zmo) else []
    check(code == 0 and 'no-such-kicad-cli not found' in out and sorted(z.uuid for z in mz) == ['zb', 'zc', 'zd', 'zf', 'zg', 'zq']
          and len(next(z for z in mz if z.uuid == 'zb').outline) == 8,
          "zonemerge -o: za deleted, zb takes the 8-corner union, zc untouched")
    zmo2 = os.path.join(tmp.name, 'merge3.kicad_pcb')
    code, out = run(['kpcb.py', zm, 'zonemerge', 'zf', 'zg', '-o', zmo2], nocli)
    mz = {z.uuid: z for z in kpcb_board.Board(zmo2).zones} if os.path.exists(zmo2) else {}
    check(code == 0 and mz.get('zg') and mz['zg'][1] == ['F.Cu'] and len(mz['zg'].outline) == 8
          and mz['zf'][1] == ['B.Cu'] and len(mz['zf'].outline) == 4 and mz['zg'].name == 'hand2',
          "zonemerge -o split: zg takes the F.Cu union and hand2's name (not its band's), zf stays on B.Cu")
    code, out = run(['kpcb.py', os.path.join(tmp.name, 'faceted.kicad_pcb'), 'zoneshape', '--over-bar', '-o', fzo], nocli)
    oz = {z.uuid: z for z in kpcb_board.Board(fzo).zones} if os.path.exists(fzo) else {}
    check(code == 0 and 'za' in oz and len(oz['za'].outline) == 8 and len(oz['zb'].outline) == 4,
          "zoneshape --over-bar -o: za written as its 8-corner proposal, zb (under the bar) as it was")
    f0 = next(iter(bb.fps.values()))
    check(repr(f0).startswith(f'FP({f0.ref} ') and f'{len(f0.pads)} pads)' in repr(f0),
                   "FP repr: ref, value, layer, position, pad count (what an ad-hoc print shows)")
    Lb = kpcb_place._bands([[(-2, -2), (2, -2), (2, 0), (0, 0), (0, 2), (-2, 2), (-2, -2)]], 0.1)
    okL = sorted(Lb) == [(-2.0, -2.0, 2.0, 0.0), (-2.0, 0.0, 0.0, 2.0)]
    check(okL, f"place: an L courtyard tests as 2 boxes {Lb}")
