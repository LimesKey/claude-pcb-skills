"""Self-test cases: kpcb.py copper commands (references/kpcb-writers.md): route, ripup, smooth, stitch, fatten, widen, tracks, copper, ...

selftest.py runs suite(); see its docstring for the case format."""
import json, os
from st_common import CASES, PCB, TMP, _gzone, _tab_board, _tab_fp, _tseg, _tvia, _typed_dir, _tzone, check, \
    rect, run


def rip_board(d, sealed=False):
    """30 x 20, route on F.Cu: a W wall along y=10 with one 0.9 mm gap at x=20. B (TP1/TP2
    at y=9.3, the shorter net, routed first) runs straight over the gap's mouth and seals
    it; A (TP3 above, TP4 below) has no other way through, so it must rip B, and B then
    goes round over TP3 - unless `sealed` walls that off too, and the rip is undone.
    D_P / D_N on B.Cu: a pair 6 / 7 mm long at a 0.15 mm edge gap."""
    p = os.path.join(d, 'ripsealed.kicad_pcb' if sealed else 'rip.kicad_pcb')
    fp = lambda ref, x, y, net: (f' (footprint "x:TP" (layer "F.Cu") (at {x} {y}) (property "Reference" "{ref}") (attr smd)'
                                 f' (fp_rect (start -.4 -.4) (end .4 .4) (layer "F.CrtYd"))'
                                 f' (pad "1" smd rect (at 0 0) (size .5 .5) (layers "F.Cu") (net "{net}")))')
    seg = lambda x0, y0, x1, y1, net='W', ly='F.Cu': (f' (segment (start {x0} {y0}) (end {x1} {y1}) (width 0.2)'
                                                      f' (layer "{ly}") (net "{net}") (uuid "{net}{x0}{y0}"))')
    open(p, 'w').write('(kicad_pcb (version 20240108) (generator "pcbnew")'
                       ' (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))'
                       ' (gr_rect (start 0 0) (end 30 20) (layer "Edge.Cuts"))'
                       + fp('TP1', 16, 9.3, 'B') + fp('TP2', 24, 9.3, 'B') + fp('TP3', 20, 3, 'A') + fp('TP4', 20, 15, 'A')
                       + seg(0, 10, 19.55, 10) + seg(20.45, 10, 30, 10) + (seg(20, 0, 20, 2.6) if sealed else '')
                       + seg(2, 18, 8, 18, 'D_P', 'B.Cu') + seg(2, 18.35, 9, 18.35, 'D_N', 'B.Cu') + '\n)\n')
    return p


def pour_board(d):
    """20 x 10 in KiCad's tab layout: P pads at x=3 and x=17, a W wall at x=10 with a
    1.2 mm gap - no 1.0 mm track fits it (1.4 with clearance), a 0.3 mm probe does.
    KiCad's refill of the `--pour` copy joins P through the gap (checked by hand)."""
    p = os.path.join(d, 'pour.kicad_pcb')
    fp = lambda ref, x: (f'\t(footprint "x:TP"\n\t\t(layer "F.Cu")\n\t\t(uuid "f{ref}")\n\t\t(at {x} 5)\n'
                         f'\t\t(property "Reference" "{ref}" (at 0 -1.5 0) (layer "F.SilkS") (effects (font (size 1 1))))\n'
                         f'\t\t(attr smd)\n\t\t(fp_rect (start -.8 -.8) (end .8 .8) (stroke (width 0.05) (type solid)) (layer "F.CrtYd"))\n'
                         f'\t\t(pad "1" smd rect (at 0 0) (size 1.2 1.2) (layers "F.Cu") (net "P"))\n\t)\n')
    seg = lambda y0, y1: (f'\t(segment\n\t\t(start 10 {y0})\n\t\t(end 10 {y1})\n\t\t(width 0.2)\n\t\t(layer "F.Cu")\n'
                          f'\t\t(net "W")\n\t\t(uuid "w{y0}")\n\t)\n')
    open(p, 'w').write('(kicad_pcb\n\t(version 20240108)\n\t(generator "pcbnew")\n\t(layers\n\t\t(0 "F.Cu" signal)\n'
                       '\t\t(31 "B.Cu" signal)\n\t\t(44 "Edge.Cuts" user)\n\t)\n'
                       '\t(gr_rect\n\t\t(start 0 0)\n\t\t(end 20 10)\n\t\t(layer "Edge.Cuts")\n\t)\n'
                       + fp('TP1', 3) + fp('TP2', 17) + seg(0, 4.4) + seg(5.6, 10) + ')\n')
    return p


def cleanup_board(d):
    """what KiCad's Cleanup Tracks & Vias takes: a collinear joint at 8,5, a duplicated 4 mm
    segment, a segment wholly inside J1.1, two vias stacked at 12,5; on M a free joint at 6,11
    and one at 10,11 held by a via met on F.Cu only (dead: it goes, then the joint merges); on K a
    joint at 6,13 whose right leg touches a 0.3 mm track (it necks: KiCad's pair order decides);
    a zero-length segment at 15,5. Held, so no row: T's joint at 9,2 by a teardrop outline 0.05 mm
    off it, H's F.Cu joint at 14,8 by an H pad on B.Cu (PAD::HitTest takes every layer)"""
    pad = lambda r, x, y=5, n='N': (f'\t(footprint "P"\n\t\t(layer "F.Cu")\n\t\t(at {x} {y})\n\t\t(property "Reference" "{r}")\n'
                                   f'\t\t(pad "1" smd rect\n\t\t\t(at 0 0)\n\t\t\t(size 1 1)\n\t\t\t(layers "F.Cu")\n\t\t\t(net "{n}")\n\t\t)\n\t)\n')
    run = lambda y, n, w3: (pad(f'J{y}a', 2, y, n) + pad(f'J{y}b', 18, y, n) + _tseg(2, y, 6, y, n) + _tseg(6, y, 10, y, n)
                            + _tseg(10, y, 18, y, n, w3))
    tear = ('\t(zone\n\t\t(net "T")\n\t\t(layer "F.Cu")\n\t\t(uuid "ct1")\n\t\t(attr\n\t\t\t(teardrop\n'
            '\t\t\t\t(type padvia)\n\t\t\t)\n\t\t)\n\t\t(polygon\n\t\t\t(pts\n\t\t\t\t(xy 8 1.9) (xy 8.95 1.95)'
            ' (xy 8.95 2.05) (xy 8 2.1)\n\t\t\t)\n\t\t)\n\t)\n')
    return _tab_board(d, 'cleanup.kicad_pcb', 20, 14, pad('J1', 2) + pad('J2', 18) + _tseg(2, 5, 8, 5, 'N')
                      + _tseg(8, 5, 18, 5, 'N') + _tseg(2, 8, 6, 8, 'N') + _tseg(2, 8, 6, 8, 'N') + _tseg(1.8, 5.1, 2.2, 5.1, 'N')
                      + _tvia(12, 5, 'N') + _tvia(12, 5, 'N') + run(11, 'M', 0.2) + _tvia(10, 11, 'M') + run(13, 'K', 0.3)
                      + _tseg(15, 5, 15, 5, 'N') + pad('T1', 2, 2, 'T') + pad('T2', 18, 2, 'T') + _tseg(2, 2, 9, 2, 'T')
                      + _tseg(9, 2, 18, 2, 'T') + tear + pad('H1', 10, 8, 'H') + pad('H2', 18, 8, 'H') + _tseg(10, 8, 14, 8, 'H')
                      + _tseg(14, 8, 18, 8, 'H') + pad('H3', 14, 8, 'H').replace('"F.Cu"', '"B.Cu"'))


def power_board(d):
    """20 x 10: net P from TP1 (2,5) to TP2 (18,5) as a 1 mm F.Cu track, a 1 mm B.Cu track
    6..14 with vias at both ends; C1 decouples P at 10,5 with its GND pad at 10,6.2 (the
    band must leave room round it). For fatten, stitch and ampacity --fills."""
    return _tab_board(d, 'power.kicad_pcb', 20, 10,
                      _tab_fp('TP1', 2, 5, [('1', 0, 0, 1, 1, 'P')], (.6, .6))
                      + _tab_fp('TP2', 18, 5, [('1', 0, 0, 1, 1, 'P')], (.6, .6))
                      + _tab_fp('C1', 10, 5.6, [('1', 0, -0.6, .5, .5, 'P'), ('2', 0, 0.6, .5, .5, 'GND')], (.4, 1.0))
                      + _tseg(2, 5, 18, 5, 'P', 1.0) + _tseg(6, 5, 14, 5, 'P', 1.0, 'B.Cu')
                      + _tvia(6, 5, 'P') + _tvia(14, 5, 'P'))


def neck_route_board(d):
    """16 x 10: P1 (net P) a 0.3 mm pad between X and Y pads at 0.5 mm pitch, P2 a big pad
    10 mm away: no 1 mm track can leave P1, a neck can"""
    return _tab_board(d, 'neckr.kicad_pcb', 16, 10,
                      _tab_fp('U1', 4, 5, [('1', 0, -0.5, .6, .3, 'X'), ('2', 0, 0, .6, .3, 'P'), ('3', 0, 0.5, .6, .3, 'Y')], (.5, .9))
                      + _tab_fp('TP2', 13, 5, [('1', 0, 0, 1.5, 1.5, 'P')], (.9, .9)))


def prerouted_rip_board(d):
    """rip_board with B already routed straight over the gap's mouth: only --rip-board
    lets A through"""
    p = rip_board(d)
    q = os.path.join(d, 'riprb.kicad_pcb')
    open(q, 'w').write(open(p).read().replace('\n)\n', ' (segment (start 16 9.3) (end 24 9.3) (width 0.2) (layer "F.Cu")'
                                                       ' (net "B") (uuid "B169.3"))\n)\n'))
    return q


def pair_board(d):
    """30 x 20: D_P / D_N pads 0.5 mm apart at both ends, a W wall from y 0 to 12 at x=15"""
    p = os.path.join(d, 'pair.kicad_pcb')
    fp = lambda ref, x, y, net: (f' (footprint "x:TP" (layer "F.Cu") (at {x} {y}) (property "Reference" "{ref}") (attr smd)'
                                 f' (fp_rect (start -.2 -.2) (end .2 .2) (layer "F.CrtYd"))'
                                 f' (pad "1" smd rect (at 0 0) (size .3 .3) (layers "F.Cu") (net "{net}")))')
    open(p, 'w').write('(kicad_pcb (version 20240108) (generator "pcbnew")'
                       ' (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))'
                       ' (gr_rect (start 0 0) (end 30 20) (layer "Edge.Cuts"))'
                       + fp('TP1', 5, 9.8, 'D_P') + fp('TP2', 5, 10.3, 'D_N') + fp('TP3', 25, 13.8, 'D_P')
                       + fp('TP4', 25, 14.3, 'D_N') + ' (segment (start 15 0) (end 15 12) (width 0.2) (layer "F.Cu")'
                       ' (net "W") (uuid "w1"))\n)\n')
    return p


def uniform_board(d):
    """PWR_HIGH (1 mm) runs P (y 5) and P2 (y 15), each 1.5 / 1.0 / 1.5 mm between test points;
    a foreign Q track at y 16 boxes P2's middle in at 1.0. P3 (y 10) is 4 / 1 / 4 mm with a
    0.2 mm R track 1.8 mm off its middle: a 4 mm middle's edge would cross it, though R lies
    outside the centreline box + 1 mm that Exact once gathered items in. widen --uniform-power
    takes P's middle to 1.5 and leaves P2's and P3's steps (4)"""
    os.makedirs(d, exist_ok=True)
    json.dump({'net_settings': {'classes': [{'name': 'Default', 'clearance': 0.2, 'track_width': 0.2},
                                            {'name': 'PWR_HIGH', 'clearance': 0.2, 'track_width': 1.0}],
                                'netclass_patterns': [{'pattern': 'P*', 'netclass': 'PWR_HIGH'}]}},
              open(os.path.join(d, 'u.kicad_pro'), 'w'))
    run = lambda n, y, wo=1.5: (_tab_fp('TP' + n, 2, y, [('1', 0, 0, 2, 2, 'P' + n)], (1.1, 1.1))   # noqa: E731
                        + _tab_fp('TQ' + n, 18, y, [('1', 0, 0, 2, 2, 'P' + n)], (1.1, 1.1))
                        + _tseg(2, y, 8, y, 'P' + n, wo) + _tseg(8, y, 14, y, 'P' + n, 1.0) + _tseg(14, y, 18, y, 'P' + n, wo))
    return _tab_board(d, 'u.kicad_pcb', 20, 20, run('', 5) + run('2', 15) + run('3', 10, 4.0)
                      + _tseg(9, 16, 13, 16, 'Q') + _tseg(10, 11.8, 12, 11.8, 'R'))


def jog_board(d, nudge=False):
    """typed rules, GND filled on F and B. Net S: TP1 (2,9) up to (2,5), along to (8,5), a 45
    jog of 0.5 mm, along y 5.5 to (14,5.5), down to TP2 (14,9). Collapse A (the run onto
    y 5.5) is blocked by a free GND via at 5,6.0; collapse B (onto y 5) by a Q track at y 4.7.
    nudge: no GND via; A blocked by an R track at y 5.8, B by a Q via at 11,4.55 with its Q
    track down to 11,1 (0.1 mm down is exactly the clearance, Exact's margin refuses it: 0.15)"""
    sd = _typed_dir(os.path.join(d, nudge if isinstance(nudge, str) else 'nudge' if nudge else 'jog'))
    v = _tvia(5, 6.0, 'GND').replace('\t\t(net "GND")', '\t\t(free yes)\n\t\t(net "GND")')
    # 'fresh': Q's track to the via has a jog of its own, listed first, so it is re-laid (no uuid)
    # before S's nudge would drag it (KeyError: None in the writer, 2026-10-27)
    body = (_tseg(11, 4.55, 11, 3, 'Q') + _tseg(11, 3, 13, 3, 'Q') + _tseg(13, 3, 13.3, 2.7, 'Q')
            + _tseg(13.3, 2.7, 17, 2.7, 'Q') + _tseg(17, 2.7, 17, 1, 'Q') if nudge == 'fresh' else '')
    body += (_tab_fp('TP1', 2, 9, [('1', 0, 0, 1, 1, 'S')], (.6, .6)) + _tab_fp('TP2', 14, 9, [('1', 0, 0, 1, 1, 'S')], (.6, .6))
             + _tseg(2, 9, 2, 5, 'S') + _tseg(2, 5, 8, 5, 'S') + _tseg(8, 5, 8.5, 5.5, 'S') + _tseg(8.5, 5.5, 14, 5.5, 'S')
             + _tseg(14, 5.5, 14, 9, 'S'))
    if nudge == 'neck':                              # A: S onto y 5.5 leaves GND 0.4 mm beside R at y 6.1
        body += _tseg(3, 6.1, 7, 6.1, 'R') + _tseg(9, 4.85, 13, 4.85, 'Q')
    elif nudge:
        body += _tseg(3, 5.8, 7, 5.8, 'R') + _tvia(11, 4.55, 'Q') + ('' if nudge == 'fresh' else _tseg(11, 4.55, 11, 1, 'Q'))
    else:
        body += v + _tseg(9, 4.7, 13, 4.7, 'Q')
    return _tab_board(sd, 't.kicad_pcb', 20, 12, body + _tzone('GND', 'F.Cu', .5, .5, 19.5, 11.5, 'zf')
                      + _tzone('GND', 'B.Cu', .5, .5, 19.5, 11.5, 'zb'))


def cusp_board(d):
    """typed rules, GND filled on F and B. Net S leaves via V (5,9) up to (5,8.3), 45 to (6.55,6.75),
    a 0.55 mm jog leg to (7.1,6.75), 45 to TP2 (8,5.85). Full collapse A bends 0.15 mm off V's
    centre, inside its antipad (the GPIO_4 In1 cusp): refused; only 20% would clear it, under the
    70% floor, so the jog stays and `tracks` says why (no `fix:` promise smooth would refuse)"""
    sd = _typed_dir(os.path.join(d, 'cusp'))
    body = (_tvia(5, 9, 'S') + _tab_fp('TP2', 8, 5.85, [('1', 0, 0, .6, .6, 'S')], (.4, .4))
            + _tseg(5, 9, 5, 8.3, 'S') + _tseg(5, 8.3, 6.55, 6.75, 'S') + _tseg(6.55, 6.75, 7.1, 6.75, 'S')
            + _tseg(7.1, 6.75, 8, 5.85, 'S'))
    return _tab_board(sd, 't.kicad_pcb', 14, 12, body + _tzone('GND', 'F.Cu', .5, .5, 13.5, 11.5, 'zf')
                      + _tzone('GND', 'B.Cu', .5, .5, 13.5, 11.5, 'zb'))


def writer_board(d):
    """30 x 20 board in KiCad's own tab layout (the writers edit by span): R1 at 5,10 and
    R2 at 25,10 (rot 90) share net A behind a W wall on F.Cu (x=15, y 1..19); C1 is
    parked off the board (B to R1.2, GND); a netless stub sits on R2.2 (net C); R2's
    fp_lines are stored through the 10.99 double transform (stored = T^-1(local))."""
    import uuid as U
    u = lambda: f'(uuid "{U.uuid4()}")'                 # noqa: E731
    def lines(ref, x, y, rot, bad):
        out = ''
        for (x0, y0), (x1, y1) in (((-1, -.5), (1, -.5)), ((1, -.5), (1, .5)), ((1, .5), (-1, .5)), ((-1, .5), (-1, -.5))):
            if bad:                                     # T^-1 of the local point, rot 90 only
                (x0, y0), (x1, y1) = (y - y0, x0 - x), (y - y1, x1 - x)
            out += (f'\t\t(fp_line\n\t\t\t(start {x0} {y0})\n\t\t\t(end {x1} {y1})\n'
                    f'\t\t\t(stroke\n\t\t\t\t(width 0.05)\n\t\t\t\t(type solid)\n\t\t\t)\n'
                    f'\t\t\t(layer "F.CrtYd")\n\t\t\t{u()}\n\t\t)\n')
        return out
    def fp(ref, x, y, rot, n1, n2, bad=False):
        pads = ''.join(f'\t\t(pad "{k}" smd rect\n\t\t\t(at {px} 0' + (f' {rot}' if rot else '') + ')\n'
                       f'\t\t\t(size 0.5 0.5)\n\t\t\t(layers "F.Cu")\n\t\t\t(net "{nn}")\n\t\t\t{u()}\n\t\t)\n'
                       for k, px, nn in (('1', -.5, n1), ('2', .5, n2)))
        return (f'\t(footprint "R"\n\t\t(layer "F.Cu")\n\t\t{u()}\n\t\t(transform\n\t\t\t(translate {x} {y})\n'
                f'\t\t\t(rotate {rot})\n\t\t\t(scale 1 1)\n\t\t)\n\t\t(property "Reference" "{ref}"\n'
                f'\t\t\t(at 0 -1.5 0)\n\t\t\t(layer "F.SilkS")\n\t\t\t{u()}\n\t\t\t(effects\n\t\t\t\t(font\n'
                f'\t\t\t\t\t(size 1 1)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n' + lines(ref, x, y, rot, bad) + pads + '\t)\n')
    seg = lambda x0, y0, x1, y1, net: (f'\t(segment\n\t\t(start {x0} {y0})\n\t\t(end {x1} {y1})\n\t\t(width 0.2)\n'
                                       f'\t\t(layer "F.Cu")\n\t\t(net "{net}")\n\t\t{u()}\n\t)\n')
    p = os.path.join(d, 'writer.kicad_pcb')
    open(p, 'w').write(
        '(kicad_pcb\n\t(version 20260901)\n\t(generator "pcbnew")\n\t(generator_version "10.99")\n'
        '\t(layers\n\t\t(0 "F.Cu" signal)\n\t\t(2 "B.Cu" signal)\n\t\t(25 "Edge.Cuts" user)\n\t)\n'
        f'\t(gr_rect\n\t\t(start 0 0)\n\t\t(end 30 20)\n\t\t(layer "Edge.Cuts")\n\t\t{u()}\n\t)\n'
        + fp('R1', 5, 10, 0, 'A', 'B') + fp('R2', 25, 10, 90, 'A', 'C', bad=True) + fp('C1', 40, 10, 0, 'B', 'GND')
        + seg(15, 1, 15, 19, 'W') + seg(25, 9.5, 25, 8, '') + ')\n')
    return p


def typed_board(d, dru=True):
    """10 x 6: net A from TP1 (1,3) to TP2 (9,3) past U1's X/Y pads 0.4 mm apart at x=5
    (y 2.2..2.8 and 3.2..3.8), W walls above and below: a 0.15 track fits the gap only
    under the 0.1 Pad to Track rule (the 0.15 netclass needs 0.45)"""
    return _tab_board(_typed_dir(d, dru), 't.kicad_pcb', 10, 6,
                      _tab_fp('TP1', 1, 3, [('1', 0, 0, .6, .6, 'A')], (.4, .4))
                      + _tab_fp('TP2', 9, 3, [('1', 0, 0, .6, .6, 'A')], (.4, .4))
                      + _tab_fp('U1', 5, 3, [('1', 0, -0.5, 1, .6, 'X'), ('2', 0, 0.5, 1, .6, 'Y')], (.6, .9))
                      + _tseg(5, 0.2, 5, 2.0, 'W') + _tseg(5, 4.0, 5, 5.8, 'W'))


def stair_board(d):
    """10 x 14 beside typed_board's rules: net S a 0.15 staircase TP3 (1,2) -> TP4 (9,8)
    with four 90s; net L joins TP5/TP6 twice, straight at y=11 and by a detour at 12.5"""
    return _tab_board(d, 's.kicad_pcb', 10, 14,
                      _tab_fp('TP3', 1, 2, [('1', 0, 0, .6, .6, 'S')], (.4, .4))
                      + _tab_fp('TP4', 9, 8, [('1', 0, 0, .6, .6, 'S')], (.4, .4))
                      + _tab_fp('TP5', 1.5, 11, [('1', 0, 0, .6, .6, 'L')], (.4, .4))
                      + _tab_fp('TP6', 8.5, 11, [('1', 0, 0, .6, .6, 'L')], (.4, .4))
                      + ''.join(_tseg(*a, *c, 'S', 0.15) for a, c in zip([(1, 2), (3, 2), (3, 4), (6, 4), (6, 8)],
                                                                          [(3, 2), (3, 4), (6, 4), (6, 8), (9, 8)]))
                      + _tseg(1.5, 11, 8.5, 11, 'L') + _tseg(1.5, 11, 2.5, 12.5, 'L') + _tseg(2.5, 12.5, 7.5, 12.5, 'L')
                      + _tseg(7.5, 12.5, 8.5, 11, 'L'))


def dense_board(d):
    """20 x 12 beside typed_board's rules: net D TP20 (2,6) -> TP21 (18,6) routed the long way
    round by y=1 (26 mm vs a 16 mm MST: a detour `reroute` straightens). U2 at 10,9 (courtyard
    +/-3 x +/-1): pin 1 (E, x 8) free; pin 2 (B, x 10) in a tight W ring 0.45 mm out (no track
    or via gets out); pin 3 (V, x 12) in a W ring 1.2 mm out on F.Cu (room for a via inside).
    TP22/23/24 give E, V and B a pending link each (congest)."""
    sq = lambda cx, cy, r, net='W': ''.join(_tseg(*a, *b_, net) for a, b_ in zip(       # noqa: E731
        [(cx - r, cy - r), (cx + r, cy - r), (cx + r, cy + r), (cx - r, cy + r)],
        [(cx + r, cy - r), (cx + r, cy + r), (cx - r, cy + r), (cx - r, cy - r)]))
    return _tab_board(d, 'dn.kicad_pcb', 20, 12,
                      _tab_fp('TP20', 2, 6, [('1', 0, 0, .6, .6, 'D')]) + _tab_fp('TP21', 18, 6, [('1', 0, 0, .6, .6, 'D')])
                      + _tseg(2, 6, 2, 1, 'D') + _tseg(2, 1, 18, 1, 'D') + _tseg(18, 1, 18, 6, 'D')
                      + _tab_fp('U2', 10, 9, [('1', -2, 0, .3, .3, 'E'), ('2', 0, 0, .3, .3, 'B'), ('3', 2, 0, .3, .3, 'V')],
                                (3, 1))
                      + sq(10, 9, .45) + sq(12, 9, 1.2)
                      + _tab_fp('TP22', 2, 10.5, [('1', 0, 0, .6, .6, 'E')]) + _tab_fp('TP23', 18, 10.5, [('1', 0, 0, .6, .6, 'V')])
                      + _tab_fp('TP24', 10, 11.3, [('1', 0, 0, .6, .6, 'B')]))


def channel_board(d):
    """10 x 6 beside typed_board's rules: 1 mm W walls filling y 3..4 on F.Cu and B.Cu leave a
    1.2 mm gap at x 4.4..5.6; nets N0..N5 (TPs at y 1 and 5.5, x 3..7) all cross that row,
    four of them over solid wall (congest: no capacity there)"""
    walls = ''.join(_tseg(x0, 3.5, x1, 3.5, 'W', 1.0, ly) for x0, x1 in ((0, 4.4), (5.6, 10)) for ly in ('F.Cu', 'B.Cu'))
    tps = ''.join(_tab_fp(f'TP{30 + 2 * i + k}', 3 + 0.8 * i, 1 + 4.5 * k, [('1', 0, 0, .5, .5, f'N{i}')], (.3, .3))
                  for i in range(6) for k in (0, 1))
    return _tab_board(d, 'ch.kicad_pcb', 10, 6, walls + tps)


def graze_board(d):
    """10 x 6 beside typed_board's rules: net G a 0.2 track at y=1 that only grazes TP7 (1,1)
    and stops 0.2 short of TP8's centre (8,1), 0.1 inside its edge: left as laid; net K grazes TP10 (1,4) and TP11 (8,4), with a
    stub from the TP10 graze to its centre (that pad's only entry: no loop); net H ends 0.08
    left of TP12 (5,5.5)'s corner, off its line (a stub, not a slide); net J TP13 (1,2.5) ->
    TP14 (8,2.5) in two runs whose ends 4.5 and 4.65 meet only through their caps; net Z a
    stub from TP15 (9.3,5.3)'s centre to 4.95, just past its edge but in Z's pour: a pour tie"""
    return _tab_board(d, 'g.kicad_pcb', 10, 6,
                      _tab_fp('TP7', 1, 1, [('1', 0, 0, .6, .6, 'G')], (.4, .4))
                      + _tab_fp('TP8', 8, 1, [('1', 0, 0, .6, .6, 'G')], (.4, .4))
                      + _tab_fp('TP10', 1, 4, [('1', 0, 0, .6, .6, 'K')], (.4, .4))
                      + _tab_fp('TP11', 8, 4, [('1', 0, 0, .6, .6, 'K')], (.4, .4))
                      + _tab_fp('TP12', 5, 5.5, [('1', 0, 0, .6, .6, 'H')], (.4, .4))
                      + _tab_fp('TP13', 1, 2.5, [('1', 0, 0, .6, .6, 'J')], (.4, .4))
                      + _tab_fp('TP14', 8, 2.5, [('1', 0, 0, .6, .6, 'J')], (.4, .4))
                      + _tseg(1.35, 1, 7.8, 1, 'G') + _tseg(1.35, 4, 7.65, 4, 'K') + _tseg(1.35, 4, 1, 4, 'K')
                      + _tseg(3, 5.2, 4.62, 5.2, 'H') + _tseg(1, 2.5, 4.5, 2.5, 'J') + _tseg(4.65, 2.5, 8, 2.5, 'J')
                      + _tab_fp('TP15', 9.3, 5.3, [('1', 0, 0, .6, .6, 'Z')], (.4, .4)) + _tseg(9.3, 5.3, 9.3, 4.95, 'Z')
                      + _gzone('F.Cu', rect(8.9, 4.5, 9.9, 5.0), rect(8.9, 4.5, 9.9, 5.0), 'tie', net='Z', uid='ztie'))


def drift_board(d):
    """typed rules, 10 x 7: net D TP1 (1,2) -> (7,2.03) -> 45 -> TP2 (9,4.03), its first leg
    0.29 deg off 0 (30 um of drift: off-45 though under 0.3 deg); net E one 7 mm segment TP3
    (1,5) -> TP4 (8,5.03), as crooked, between two pads: its only dogleg has a 42 um leg"""
    return _tab_board(_typed_dir(os.path.join(d, 'drift')), 't.kicad_pcb', 10, 7,
                      _tab_fp('TP1', 1, 2, [('1', 0, 0, .6, .6, 'D')]) + _tab_fp('TP2', 9, 4.03, [('1', 0, 0, .6, .6, 'D')])
                      + _tab_fp('TP3', 1, 5, [('1', 0, 0, .6, .6, 'E')]) + _tab_fp('TP4', 8, 5.03, [('1', 0, 0, .6, .6, 'E')])
                      + _tseg(1, 2, 7, 2.03, 'D') + _tseg(7, 2.03, 9, 4.03, 'D') + _tseg(1, 5, 8, 5.03, 'E'))


def band_board(d):
    """Net Q: TP6 (1,2) -> TP5 (4,2, 1.6 x 1.2) on F; two vias in TP5 (3.6 and 4.4) carry a
    `route Q` B.Cu band (4..8 x 1.6..2.4) round a B run to 7.6, with a B track weaving out of
    the band (y 2.9) and back: the band hangs off ONE via cluster, dead, weave and all. Net R:
    TP7 (1,7) -> (5,7) w1 -> TP8 (5,9); a 0.12 mm w0.8 piece from that corner into its end cap,
    then a dead branch to (8,7): the piece goes with the branch"""
    return _tab_board(d, 'band.kicad_pcb', 10, 10,
                      _tab_fp('TP6', 1, 2, [('1', 0, 0, .6, .6, 'Q')]) + _tab_fp('TP5', 4, 2, [('1', 0, 0, 1.6, 1.2, 'Q')], (1, .8))
                      + _tseg(1, 2, 4, 2, 'Q', 0.3) + _tvia(3.6, 2, 'Q') + _tvia(4.4, 2, 'Q')
                      + _tseg(4.4, 2, 7.6, 2, 'Q', 0.3, 'B.Cu', uid='qrun')
                      + _tseg(5, 2.2, 5.5, 2.9, 'Q', 0.2, 'B.Cu') + _tseg(5.5, 2.9, 6.5, 2.9, 'Q', 0.2, 'B.Cu')
                      + _tseg(6.5, 2.9, 7, 2.2, 'Q', 0.2, 'B.Cu')
                      + _gzone('B.Cu', rect(4, 1.6, 8, 2.4), rect(4, 1.6, 8, 2.4), 'route Q', net='Q', uid='zq')
                      + _tab_fp('TP7', 1, 7, [('1', 0, 0, .6, .6, 'R')]) + _tab_fp('TP8', 5, 9, [('1', 0, 0, .6, .6, 'R')])
                      + _tseg(1, 7, 5, 7, 'R', 1.0) + _tseg(5, 7, 5, 9, 'R', 1.0)
                      + _tseg(5, 7, 5.12, 7, 'R', 0.8, uid='rpiece') + _tseg(5.12, 7, 8, 7, 'R', 0.8, uid='rdead'))


def prune_board(d):
    """G: TP1 -> track t1 to 6,2; an old dangling G stub elsewhere (8,8)-(9,8). P trunk
    TP2 (1,5) - TP3 (9,5) with C1.1 teed into it by a stub; C1.2 G to TP4 and on to TP5
    (a chain through C1.2: unhook C1 cuts TP5 off). A teardrop zone sits on track td1 (net Q)"""
    tear = ('\t(zone\n\t\t(net "Q")\n\t\t(layer "F.Cu")\n\t\t(uuid "tz1")\n\t\t(attr\n\t\t\t(teardrop\n'
            '\t\t\t\t(type padvia)\n\t\t\t)\n\t\t)\n\t\t(polygon\n\t\t\t(pts\n\t\t\t\t(xy 12 11.8) (xy 13 11.8)'
            ' (xy 13 12.2) (xy 12 12.2)\n\t\t\t)\n\t\t)\n\t)\n')
    return _tab_board(d, 'prune.kicad_pcb', 20, 14,
                      _tab_fp('TP1', 2, 2, [('1', 0, 0, .6, .6, 'G')], (.4, .4))
                      + _tab_fp('TP2', 1, 5, [('1', 0, 0, .6, .6, 'P')], (.4, .4))
                      + _tab_fp('TP3', 9, 5, [('1', 0, 0, .6, .6, 'P')], (.4, .4))
                      + _tab_fp('C1', 5, 7, [('1', -0.5, 0, .5, .5, 'P'), ('2', 0.5, 0, .5, .5, 'G')], (1, .5))
                      + _tab_fp('TP4', 8, 9, [('1', 0, 0, .6, .6, 'G')], (.4, .4))
                      + _tab_fp('TP7', 12, 12, [('1', 0, 0, .6, .6, 'Q')], (.4, .4))
                      + _tab_fp('TP5', 3, 9, [('1', 0, 0, .6, .6, 'G')], (.4, .4))
                      + _tseg(2, 2, 6, 2, 'G', uid='t1') + _tseg(8, 8, 9, 8, 'G') + _tseg(1, 5, 9, 5, 'P')
                      + _tseg(4.5, 7, 4.5, 5, 'P') + _tseg(5.5, 7, 8, 9, 'G') + _tseg(5.5, 7, 3, 9, 'G')
                      + _tseg(12, 12, 16, 12, 'Q', uid='td1')
                      + tear)


def ovia_board(d, offc=True):
    """typed rules. Net A: TP1 (8,5); ti 0.3 wide (8,5)->(10,5) ends on via V's centre, tj 0.6
    wide (8,5)->(14,5) runs over V; offc: tk ends inside V 0.1 mm off its centre, so deleting
    ti would leave V with an off-centre end and none centred (TRACK_NOT_CENTERED_ON_VIA)"""
    sd = _typed_dir(os.path.join(d, 'ovia' + ('1' if offc else '0')))
    return _tab_board(sd, 't.kicad_pcb', 20, 10, _tab_fp('TP1', 8, 5, [('1', 0, 0, .6, .6, 'A')], (.4, .4))
                      + _tseg(8, 5, 10, 5, 'A', 0.3) + _tseg(8, 5, 14, 5, 'A', 0.6) + _tvia(10, 5, 'A')
                      + (_tseg(10.1, 5, 10.1, 9, 'A', 0.2) if offc else ''))


def prec_board(d):
    """net A: a via at 10.12345,5.5 and a track 2,5.5 -> 10.12345,5.5 (copper must print every decimal)"""
    return _tab_board(d, 'prec.kicad_pcb', 20, 10, _tvia(10.12345, 5.5, 'A') + _tseg(2, 5.5, 10.12345, 5.5, 'A'))


def sliver_board(d):
    """typed rules. Net S: TP1 (2,5) -> 0.3 to (6,5) -> a 0.15 sliver to (6.1,5) -> 0.3 to TP2 (12,5)"""
    sd = _typed_dir(os.path.join(d, 'sliver'))
    return _tab_board(sd, 't.kicad_pcb', 14, 10, _tab_fp('TP1', 2, 5, [('1', 0, 0, .6, .6, 'S')], (.4, .4))
                      + _tab_fp('TP2', 12, 5, [('1', 0, 0, .6, .6, 'S')], (.4, .4))
                      + _tseg(2, 5, 6, 5, 'S', 0.3) + _tseg(6, 5, 6.1, 5, 'S', 0.15) + _tseg(6.1, 5, 12, 5, 'S', 0.3))


def sparse_board(d):
    """typed rules, 30 x 10: GND poured and filled on F and B, one GND via at 2,5: the far end
    of the pour is ~26 mm from a via"""
    sd = _typed_dir(os.path.join(d, 'sparse'))
    return _tab_board(sd, 't.kicad_pcb', 30, 10, _tvia(2, 5, 'GND') + _tab_fp('TP1', 2, 2, [('1', 0, 0, .6, .6, 'GND')], (.4, .4))
                      + _gzone('F.Cu', rect(.5, .5, 29.5, 9.5), rect(.5, .5, 29.5, 9.5))
                      + _gzone('B.Cu', rect(.5, .5, 29.5, 9.5), rect(.5, .5, 29.5, 9.5)))


def sparse_tht_board(d):
    """sparse_board plus J1, a 1.4 mm round GND THT pad (0.8 drill) at 28.5,5 in a notch of both
    fills (its relief: the centre is not in the fill): it already ties the far end, so the worst
    point is mid-board, and no via may land on its annular ring (TP1.2 / J4.2, 2026-10-27)"""
    sd = _typed_dir(os.path.join(d, 'sparse_tht'))
    tht = ('\t(footprint "x:J"\n\t\t(layer "F.Cu")\n\t\t(uuid "fj1")\n\t\t(at 28.5 5)\n'
           '\t\t(property "Reference" "J1"\n\t\t\t(at 0 -1.5 0)\n\t\t\t(layer "F.SilkS")\n\t\t\t(uuid "fj1r")\n\t\t)\n'
           '\t\t(pad "1" thru_hole circle\n\t\t\t(at 0 0)\n\t\t\t(size 1.4 1.4)\n\t\t\t(drill 0.8)\n'
           '\t\t\t(layers "*.Cu" "*.Mask")\n\t\t\t(net "GND")\n\t\t\t(uuid "fj1p")\n\t\t)\n\t)\n')
    notch = [(.5, .5), (29.5, .5), (29.5, 4), (27.5, 4), (27.5, 6), (29.5, 6), (29.5, 9.5), (.5, 9.5)]
    return _tab_board(sd, 't.kicad_pcb', 30, 10, _tvia(2, 5, 'GND') + tht
                      + _gzone('F.Cu', rect(.5, .5, 29.5, 9.5), notch) + _gzone('B.Cu', rect(.5, .5, 29.5, 9.5), notch))


def dead_board(d):
    """Net P: TP1 (2,5) -> TP2 (16,5) on F, the track overshooting TP2 to 17.5 (cut back to
    16). Via V1 (6,5) on it starts a pad-less cycle: F (6,5)->(9,8)->(12,8), via V2 (12,8), B
    (12,8)->(6,8)->(6,5), a B pour band round the B run: dead, V1 with it. TP3 (14,2) tees in
    at (14,5) with two thermal vias in its pad and a B pour under it: a heatsink, not dead. TP4
    (12,2) is fed from (9,5) through V3 (9,2) and V4 (11,2) on F and B in parallel: live, until
    `unhook TP4` leaves that cycle serving nothing"""
    body = (_tab_fp('TP1', 2, 5, [('1', 0, 0, 1, 1, 'P')], (.6, .6)) + _tab_fp('TP2', 16, 5, [('1', 0, 0, 1, 1, 'P')], (.6, .6))
            + _tab_fp('TP3', 14, 2, [('1', 0, 0, 2, 1.2, 'P')], (1.1, .7)) + _tab_fp('TP4', 12, 2, [('1', 0, 0, 1, 1, 'P')], (.6, .6))
            + _tseg(2, 5, 17.5, 5, 'P', 0.3, uid='live') + _tvia(6, 5, 'P')
            + _tseg(6, 5, 9, 8, 'P', 0.3, uid='df1') + _tseg(9, 8, 12, 8, 'P', 0.3, uid='df2') + _tvia(12, 8, 'P')
            + _tseg(12, 8, 6, 8, 'P', 0.3, 'B.Cu', uid='db1') + _tseg(6, 8, 6, 5, 'P', 0.3, 'B.Cu', uid='db2')
            + _tseg(14, 2, 14, 5, 'P', 0.3) + _tvia(13.5, 2, 'P') + _tvia(14.5, 2, 'P')
            + _tseg(9, 5, 9, 2, 'P', 0.3) + _tvia(9, 2, 'P') + _tvia(11, 2, 'P') + _tseg(9, 2, 11, 2, 'P', 0.3)
            + _tseg(9, 2, 11, 2, 'P', 0.3, 'B.Cu') + _tseg(11, 2, 12, 2, 'P', 0.3)
            + _gzone('B.Cu', rect(5.5, 7.6, 12.5, 8.4), rect(5.5, 7.6, 12.5, 8.4), 'band', net='P', uid='zband')
            + _gzone('B.Cu', rect(12.5, .8, 15.5, 3.2), rect(12.5, .8, 15.5, 3.2), 'sink', net='P', uid='zsink'))
    return _tab_board(d, 'dead.kicad_pcb', 20, 10, body)


def attach_stub_board(d):
    """Net S: TP1 (2,5) -> J (8,5) on F, 1.5 mm; a via on that trunk 0.42 mm short of J, out on B
    to a via at 4,8 and on F to TP2 (2,8); a dead 1.3 mm branch J -> (12,5), and sstub, a 31 um
    1.5 mm stub at J lying in the trunk and the via (the reference board's -BATT attach: KiCad's
    Cleanup took it with the branch, an item over both its ends crediting one)"""
    return _tab_board(d, 'astub.kicad_pcb', 14, 10, _tab_fp('TP1', 2, 5, [('1', 0, 0, 1, 1, 'S')])
                      + _tab_fp('TP2', 2, 8, [('1', 0, 0, 1, 1, 'S')]) + _tseg(2, 5, 8, 5, 'S', 1.5, uid='strunk')
                      + _tseg(8, 5, 8.022, 5.022, 'S', 1.5, uid='sstub') + _tseg(8, 5, 12, 5, 'S', 1.3, uid='sbr')
                      + _tvia(7.777, 4.65, 'S') + _tseg(7.777, 4.65, 4, 8, 'S', 0.3, 'B.Cu') + _tvia(4, 8, 'S')
                      + _tseg(4, 8, 2, 8, 'S', 0.3))


def micro_board(d):
    """typed rules. Net N: TP1 (2,5) -> (8,5), a 30 um link (8,5)->(8.03,5), -> TP2 (14,5): merged.
    Net M: TP3 (2,8) -> (8,8) w0.3, then a 20 um w0.2 dot at its end, under its cap: deleted"""
    sd = _typed_dir(os.path.join(d, 'micro'))
    return _tab_board(sd, 't.kicad_pcb', 16, 10, _tab_fp('TP1', 2, 5, [('1', 0, 0, .6, .6, 'N')]) + _tab_fp('TP2', 14, 5, [('1', 0, 0, .6, .6, 'N')])
                      + _tab_fp('TP3', 2, 8, [('1', 0, 0, .6, .6, 'M')]) + _tseg(2, 5, 8, 5, 'N') + _tseg(8, 5, 8.03, 5, 'N')
                      + _tseg(8.03, 5, 14, 5, 'N') + _tseg(2, 8, 8, 8, 'M', 0.3) + _tseg(8, 8, 8.02, 8, 'M', 0.2))


def pwr_inpour_board(d):
    """PWR (not a plane: 16 of 200 mm2) poured on F.Cu 3..11 x 4..6, its track (4,5)->(10,5) inside"""
    return _tab_board(d, 'pwrin.kicad_pcb', 20, 10, _tseg(4, 5, 10, 5, 'PWR', 0.3, uid='tpwr')
                      + _gzone('F.Cu', rect(3, 4, 11, 6), rect(3, 4, 11, 6), 'pwr', net='PWR', uid='zpwr'))


def inpour_board(d):
    """GND filled on F.Cu (a thermal zone: no connect_pads yes). t1 (4,5)->(8,5) lies in the
    fill; t2 (12,5)->(14,5) too, but ends in TP1, a thermal pad: its track is a spoke"""
    return _tab_board(d, 'inpour.kicad_pcb', 20, 10, _tab_fp('TP1', 14, 5, [('1', 0, 0, .6, .6, 'GND')], (.4, .4))
                      + _tseg(4, 5, 8, 5, 'GND', 0.3) + _tseg(12, 5, 14, 5, 'GND', 0.3)
                      + _gzone('F.Cu', rect(.5, .5, 19.5, 9.5), rect(.5, .5, 19.5, 9.5)))


def stale_pour_board(d):
    """GND zone over all of F.Cu, its saved fill only x < 8 (stale): TP1/TP3 in the fill, TP2
    at 15,5 inside the zone but not yet in any fill - a refill joins it, route must not"""
    return _tab_board(d, 'stale.kicad_pcb', 20, 10, _tab_fp('TP1', 3, 3, [('1', 0, 0, .6, .6, 'GND')], (.4, .4))
                      + _tab_fp('TP3', 3, 7, [('1', 0, 0, .6, .6, 'GND')], (.4, .4))
                      + _tab_fp('TP2', 15, 5, [('1', 0, 0, .6, .6, 'GND')], (.4, .4))
                      + _gzone('F.Cu', rect(.5, .5, 19.5, 9.5), rect(.5, .5, 8, 9.5)))


def join_board(d):
    """typed rules. Net N: run A TP1 (4,5.2) -> (9.8,5.2) ends inside P1 (1.0 x 1.4 at 10,5),
    run B starts inside it at (10.2,4.8) -> TP2 (16,4.8): joined only through P1's copper"""
    sd = _typed_dir(os.path.join(d, 'join'))
    return _tab_board(sd, 't.kicad_pcb', 20, 10, _tab_fp('TP1', 4, 5.2, [('1', 0, 0, .6, .6, 'N')], (.4, .4))
                      + _tab_fp('TP2', 16, 4.8, [('1', 0, 0, .6, .6, 'N')], (.4, .4))
                      + _tab_fp('P1', 10, 5, [('1', 0, 0, 1.0, 1.4, 'N')], (.6, .8))
                      + _tseg(4, 5.2, 9.8, 5.2, 'N', 0.3) + _tseg(10.2, 4.8, 16, 4.8, 'N', 0.3))


def stubpad_board(d):
    """typed rules. Net N: via V (10,7) -> P1's centre (10,5) -> a stub to (10.2,5.15), still
    inside P1 (1.0 x 0.4) -> TP1 (13,5.15). Both P1 nodes are two-track nodes whose other end
    sits in P1: neither may be released, or the DP cuts past P1 (U6.5, 2026-10-27)"""
    sd = _typed_dir(os.path.join(d, 'stubpad'))
    return _tab_board(sd, 't.kicad_pcb', 16, 10, _tab_fp('P1', 10, 5, [('1', 0, 0, 1.0, .4, 'N')], (.6, .3))
                      + _tab_fp('TP1', 13, 5.15, [('1', 0, 0, .6, .6, 'N')], (.4, .4)) + _tvia(10, 7, 'N')
                      + _tseg(10, 7, 10, 5, 'N') + _tseg(10, 5, 10.2, 5.15, 'N') + _tseg(10.2, 5.15, 13, 5.15, 'N'))


def twin_board(d):
    """typed rules. Net T: U1.1 (16,5.25) runs to R1.1 (0.6 x 0.6 at 10,5) along y 5.25, while
    via V (13,4.75) runs there along y 4.75: twins 0.5 mm apart"""
    sd = _typed_dir(os.path.join(d, 'twin'))
    return _tab_board(sd, 't.kicad_pcb', 20, 10, _tab_fp('U1', 16, 5.25, [('1', 0, 0, .6, .3, 'T')], (.4, .4))
                      + _tab_fp('R1', 10, 5, [('1', 0, 0, .6, .6, 'T')], (.4, .4)) + _tvia(13, 4.75, 'T')
                      + _tseg(16, 5.25, 10.1, 5.25, 'T') + _tseg(13, 4.75, 10.1, 4.75, 'T'))


def suite(tmp, mini):
    """Append this file's cases to CASES, yield while the runner runs them, then do the
    ad-hoc checks (the full run only: -k stops at the yield)."""
    T = lambda n: os.path.join(tmp.name, n)             # noqa: E731
    import shutil as _sh
    CASES.append(("kpcb box arg", ['kpcb.py', PCB, 'tracks', '--box', '1,2'], 2, ["argument --box: '1,2': want X0,Y0,X1,Y1"]))  # was an IndexError
    CASES.append(("kpcb box order", ['kpcb.py', PCB, 'tracks', '--box', '40,30,0,0'], 0, ["tracks in 0,0,40,30:"]))  # reversed: was empty
    CASES.append(("kpcb kind arg", ['kpcb.py', PCB, 'tracks', '--kind', 'cleanup,dedend'], 2, ["argument --kind: 'dedend': no such kind"]))
    CASES.append(("kpcb vias",    ['kpcb.py', PCB, 'vias'],                   0,
                  ["2 via(s), 2 net(s)", "0.45  0.20      1  through  +3V3 1"]))
    jb = jog_board(tmp.name)
    CASES.append(("kpcb tracks jog", ['kpcb.py', jb, 'tracks', '--kind', 'jog'], 0,
                  ["lane jogs 0.05-1 mm       1 visible", "A: via GND free 5.00,6.00 (--jogs moves it)", "B: track Q"]))
    CASES.append(("kpcb smooth --jogs", ['kpcb.py', jb, 'smooth', '--jogs', '-o', os.path.join(tmp.name, 'jog', 'j2.kicad_pcb')], 0,
                  ["jogs: 1 collapsed, 1 via(s) moved", "A: collapsed, GND via 5.00,6.00 -> "]))
    CASES.append(("kpcb smooth --jogs result", ['kpcb.py', os.path.join(tmp.name, 'jog', 'j2.kicad_pcb'), 'tracks', '--kind', 'jog'], 0,
                  ["lane jogs 0.05-1 mm       0 visible"]))
    CASES.append(("kpcb smooth --jogs --nudge", ['kpcb.py', jog_board(tmp.name, True), 'smooth', '--jogs', '--nudge',
                                                 '-o', os.path.join(tmp.name, 'nudge', 'j3.kicad_pcb')], 0,
                  ["jogs: 1 collapsed, 1 via(s) moved", "B: collapsed, Q via nudged 0.15 mm to 11.000,4.400"]))
    CASES.append(("kpcb smooth --jogs plane neck", ['kpcb.py', jog_board(tmp.name, 'neck'), 'smooth', '--jogs', '-o',
                                                    os.path.join(tmp.name, 'neck', 'j5.kicad_pcb')], 0,
                  ["S                            F.Cu   0.50 mm at 8.000,5.000  A: collapsed 70% of the way (the jog is now 0.15 mm)"]))
    CASES.append(("kpcb smooth --jogs antipad cusp", ['kpcb.py', cusp_board(tmp.name), 'smooth', '--jogs', '-o',
                                                     os.path.join(tmp.name, 'cusp', 'j6.kicad_pcb')], 0,
                  ["jogs: 0 collapsed", "!A: collapsed"]))
    CASES.append(("kpcb tracks jog antipad cusp", ['kpcb.py', os.path.join(tmp.name, 'cusp', 't.kicad_pcb'), 'tracks', '--kind', 'jog'], 0,
                  ["A: would neck the plane, or bend inside its own antipad", "!fix: smooth"]))
    CASES.append(("kpcb smooth --jogs --nudge fresh track", ['kpcb.py', jog_board(tmp.name, 'fresh'), 'smooth', '--jogs',
                                                           '--nudge', '-o', os.path.join(tmp.name, 'fresh', 'j4.kicad_pcb')], 0,
                  ["jogs: 2 collapsed", "Q                            F.Cu   0.30 mm at 13.000,3.000  A: collapsed",
                   "S                            F.Cu   0.50 mm at 8.000,5.000  A: collapsed 90%"]))
    wb = writer_board(tmp.name)
    w2, w3, w4 = (os.path.join(tmp.name, f'w{i}.kicad_pcb') for i in (2, 3, 4))
    CASES.append(("kpcb frame bug read corrected", ['kpcb.py', wb, 'where', 'R2'], 0,
                  ["fp_line graphics stored in the wrong frame", "courtyard : 24.50,9.00 .. 25.50,11.00"]))
    CASES.append(("kpcb fixlines", ['kpcb.py', wb, 'fixlines', '-o', w2], 0, ["fixlines: 4 fp_line(s) in 1 footprint(s)"]))
    CASES.append(("kpcb fixlines result", ['kpcb.py', w2, 'where', 'R2'], 0, ["courtyard : 24.50,9.00 .. 25.50,11.00"]))
    CASES.append(("kpcb airwires", ['kpcb.py', w2, 'airwires'], 0, ["airwires: 1 net(s) not in one piece", "R1.1 4.50,10.00"]))
    CASES.append(("kpcb route", ['kpcb.py', w2, 'route', 'A', '-o', w3], 0, ["A: R2.1 -> rest", "wrote "]))
    CASES.append(("kpcb route result", ['kpcb.py', w3, 'airwires', 'A'], 0, ["every net is one piece"]))
    CASES.append(("kpcb renet", ['kpcb.py', w3, 'renet', '-o', w4], 0, ["1 track(s) + 0 via(s) get the one net they touch"]))
    CASES.append(("kpcb place", ['kpcb.py', w4, 'place', 'C1', '--near', 'R1', '-r', '4'], 0, ["  1 ", "CLEAR"]))
    CASES.append(("kpcb place now", ['kpcb.py', w4, 'place', 'R1', '-r', '3', '--max', '2'], 0,
                  ["  now    5.00    10.00    0   F    4.00     0.00  where it sits",
                   "no clear spot has a shorter ratsnest than where R1 sits: leave it"]))
    CASES.append(("kpcb ripup", ['kpcb.py', w3, 'ripup', 'A'], 1, ["ripup: ", "on 1 net(s)", "add -o OUT"]))
    CASES.append(("kpcb move drags", ['kpcb.py', w3, 'move', 'R1', '5', '12', '-o', os.path.join(tmp.name, 'w5.kicad_pcb')], 0,
                  ["move R1 5.000,10.000 rot 0 -> 5.000,12.000", "dragged 3 track end(s) that sat on its pads"]))
    CASES.append(("kpcb move drag result", ['kpcb.py', os.path.join(tmp.name, 'w5.kicad_pcb'), 'airwires', 'A'], 0,
                  ["every net is one piece"]))
    CASES.append(("kpcb edit solid", ['kpcb.py', w3, 'edit', 'solid', 'R1.1', '-o', os.path.join(tmp.name, 'w6.kicad_pcb')], 0,
                  ["solid R1.1", "edit: 1 op(s)"]))
    rb = rip_board(tmp.name)
    CASES.append(("kpcb route boxed in, no rip-up", ['kpcb.py', rb, 'route', '--pending', '--layers', 'F.Cu', '--rips', '0'],
                  2, ["B: TP2.1 -> rest   w 0.2  8.00 mm", "A: TP4.1 - FAILED", "boxed in by W track on F.Cu"]))
    CASES.append(("kpcb route rip-up", ['kpcb.py', rb, 'route', '--pending', '--layers', 'F.Cu'], 0,
                  ["A: TP4.1 -> rest   w 0.2  12.00 mm", "- ripped up B, re-routed:",
                   "      B: TP2.1 -> rest   w 0.2  17.51 mm", "(dry run: 9 segment(s), 0 via(s), 29.5 mm"]))
    CASES.append(("kpcb route rip-up undone", ['kpcb.py', rip_board(tmp.name, sealed=True), 'route', '--pending',
                                               '--layers', 'F.Cu'], 2,
                  ["A: TP4.1 - FAILED: no path", "ripping B did not help, it could not re-route (undone)",
                   "(dry run: 2 segment(s), 0 via(s), 8.0 mm"]))
    pb = pour_board(tmp.name)
    CASES.append(("kpcb route no 1 mm path", ['kpcb.py', pb, 'route', 'P', '--layers', 'F.Cu', '--width', '1'], 2,
                  ["P: TP2.1 - FAILED: no path within 18 mm"]))
    CASES.append(("kpcb route --pour", ['kpcb.py', pb, 'route', 'P', '--layers', 'F.Cu', '--width', '1', '--pour', '0.3',
                                        '-o', os.path.join(tmp.name, 'pour2.kicad_pcb')], 0,
                  ["P: TP2.1 -> rest   w 0.3  14.00 mm", "POUR: 1 zone(s), a 1 mm band on F.Cu round a 0.3 mm corridor",
                   "wrote 0 segment(s), 0 via(s), 0.0 mm, 1 zone(s) ->"]))
    CASES.append(("kpcb pairs", ['kpcb.py', rb, 'pairs'], 0,
                  ["pairs: 1 diff pair(s)", "D_P / D_N   Default: no diff_pair_gap set",
                   "routed 6.00 / 7.00 mm   skew 1.00 mm   vias 0 / 0",
                   "coupled 6.00 / 6.00 mm (uncoupled 0.00 / 1.00), edge gap median 0.150, min 0.150, max 0.150 mm"]))
    T = lambda n: os.path.join(tmp.name, n)             # noqa: E731
    pw = power_board(tmp.name)
    CASES.append(("kpcb fatten", ['kpcb.py', pw, 'fatten', 'P', '--layers', 'F.Cu', '--width', '3', '-o', T('pw2.kicad_pcb')], 0,
                  ["fatten P F.Cu: 1 track(s) >= 0.5 mm ->", "a 3 mm band", "outline, 12 corners", "wrote "]))
    CASES.append(("kpcb fatten needs a purpose", ['kpcb.py', pw, 'fatten', 'P', '-o', T('pw4.kicad_pcb')], 1,
                  ["fatten needs a purpose: --amps A"]))
    CASES.append(("kpcb fatten --amps", ['kpcb.py', pw, 'fatten', 'P', '--amps', '3', '-o', T('pw5.kicad_pcb')], 0,
                  ["fatten P F.Cu: 1 track(s) >= 0.5 mm -> 1 zone(s), a 1.4 mm band", "fatten P B.Cu: 1 track(s)"]))
    CASES.append(("kpcb fatten --amps carried", ['kpcb.py', pw, 'fatten', 'P', '--amps', '1', '-o', T('pw6.kicad_pcb')], 1,
                  ["fatten P F.Cu: 1 track(s) already carry 1 A at 10 C (>= 0.35 mm), no band", "fatten: no tracks to widen"]))
    CASES.append(("kpcb fatten halo", ['kpcb.py', T('pw2.kicad_pcb'), 'copper', '9,3,11,7', '--layers', 'F.Cu'], 0,
                  ["Z F        P", "'fatten P'"]))
    CASES.append(("kpcb stitch", ['kpcb.py', pw, 'stitch', 'P'], 0,
                  ["stitch P: via 0.6/0.3 mm", "beside via 6.00,5.00: ", "(dry run: 4 via(s)"]))
    CASES.append(("kpcb stitch write", ['kpcb.py', pw, 'stitch', 'P', '10,5', '-r', '2', '--n', '1', '-o', T('pw3.kicad_pcb')], 0,
                  ["near 10.00,5.00: ", "wrote 1 via(s)"]))
    CASES.append(("kpcb stitch free", ['kpcb.py', T('pw3.kicad_pcb'), 'copper', '8,3,12,7', '--net', 'P'], 0, ["  free"]))
    CASES.append(("kpcb ampacity --fills", ['kpcb.py', pw, 'ampacity', '--from', 'TP1.1', '--to', 'TP2.1', '--amps', '2',
                                            '--fills'], 0,
                  ["THROUGH THE REAL FILLS (necks included): R ", "densest current off the pads and vias"]))
    CASES.append(("kpcb route neck-down", ['kpcb.py', neck_route_board(tmp.name), 'route', 'P', '--width', '1',
                                           '--layers', 'F.Cu'], 0, ["P: TP2.1 -> rest   w 1", "NECK: ", "out of a fine-pitch pad, then 1 mm"]))
    CASES.append(("kpcb route --rip-board", ['kpcb.py', prerouted_rip_board(tmp.name), 'route', 'A', '--layers', 'F.Cu',
                                             '--rip-board', '4'], 0,
                  ["--rip-board 4: 1 small unlocked signal net(s)", "- ripped up B, re-routed:", "ripped from the board: B"]))
    CASES.append(("kpcb route --avoid", ['kpcb.py', pair_board(tmp.name), 'route', 'D_P', '--layers', 'F.Cu',
                                         '--avoid', '14,12,16,20'], 2,
                  ["(--avoid 14,12,16,20: no track or via", "D_P: TP3.1 - FAILED", "a rule area"]))
    CASES.append(("kpcb route --pair", ['kpcb.py', pair_board(tmp.name), 'route', 'D_P', 'D_N', '--layers', 'F.Cu', '--pair'], 0,
                  ["D_N: following D_P at a 0.35 mm pitch", "coupled "]))
    po = pour_board(tmp.name)
    CASES.append(("kpcb copper", ['kpcb.py', po, 'copper', '9,0,11,10'], 0,
                  ["copper in 9.00,0.00 .. 11.00,10.00: 2 item(s)", "T F.Cu     W", "w0.20  10.000,0.000 -> 10.000,4.400  w0"]))
    CASES.append(("kpcb edit", ['kpcb.py', po, 'edit', 'width', 'w0', '0.3', 'del', 'w5.6', 'via', 'P', '10,8', '0.6/0.3',
                                '-o', T('pe.kicad_pcb')], 0, ["width w0 -> 0.3", "del   w5.6 (segment)", "edit: 3 op(s)"]))
    CASES.append(("kpcb edit result", ['kpcb.py', T('pe.kicad_pcb'), 'copper', '9,0,11,10'], 0,
                  ["w0.30  10.000,0.000 -> 10.000,4.400", "0.60/0.30  10.000,8.000  free"]))
    CASES.append(("kpcb edit refuses", ['kpcb.py', po, 'edit', 'del', 'nothing', '-o', T('px.kicad_pcb')], 1,
                  ["matches 0 item(s); nothing written"]))
    os.makedirs(T('sc0'))                               # its own dir: tmp holds mini_project's t.kicad_pro
    _sh.copy(wb, T('sc0'))
    tb = typed_board(T('typed'))
    CASES.append(("kpcb route typed DRU rules", ['kpcb.py', tb, 'route', 'A', '--layers', 'F.Cu', '--width', '0.15'], 0,
                  ["-> rest   w 0.15"]))
    CASES.append(("kpcb route netclass only", ['kpcb.py', typed_board(T('untyped'), dru=False), 'route', 'A', '--layers',
                                               'F.Cu', '--width', '0.15'], 2, ["FAILED"]))
    CASES.append(("kpcb vscan", ['kpcb.py', tb, 'vscan', 'A', '4,2,6,4', '--layers', 'F.Cu'], 0,
                  ["vscan A  4,2 .. 6,4", "F.Cu: # blocked, . free for the track", "   3.00 "]))
    sb = stair_board(T('typed'))
    CASES.append(("kpcb tracks census", ['kpcb.py', sb, 'tracks'], 0,
                  ["corners 46-90 deg         6 visible", "fix: smooth --corners", "pad end (smooth --square)"]))
    os.makedirs(T('capv'), exist_ok=True)              # a 45 deg V of two long legs shows; a 0.21 mm stub of a
    cv = _tab_board(T('capv'), 'c.kicad_pcb', 20, 8,      # 1 mm track reads as a blob (its cap fills the turn)
                    _tseg(2, 2, 6, 2, 'S') + _tseg(6, 2, 3, 5, 'S')
                    + _tseg(10, 2, 14, 2, 'S', 1.0) + _tseg(14, 2, 13.85, 2.15, 'S', 1.0))
    CASES.append(("kpcb tracks acute stub cap", ['kpcb.py', cv, 'tracks', '--kind', 'acute'], 0,
                  ["corners, acute            1 visible  (1 hidden", "S                        F.Cu       6.000,2.000    135 deg"]))
    CASES.append(("kpcb smooth", ['kpcb.py', sb, 'smooth', '-o', T('typed/s2.kicad_pcb')], 0,
                  ["chains: 3, re-laid 2", "5->2 segs", "wrote "]))
    CASES.append(("kpcb diff", ['kpcb.py', T('typed/s2.kicad_pcb'), 'diff', sb], 0,
                  ["tracks: ", "series R of the changed tracks", "identical: footprints (4)"]))
    CASES.append(("kpcb widen", ['kpcb.py', sb, 'widen', 'S'], 0, ["widen: 5 track(s)", "0.15 -> 0.2"]))
    CASES.append(("kpcb widen --uniform-power", ['kpcb.py', uniform_board(T('uni')), 'widen', '--uniform-power'], 0,
                  ["widen: 1 track(s)", "4 width step(s) left mid-run in power classes", "P    ", "1 -> 1.5"]))
    CASES.append(("kpcb loops", ['kpcb.py', sb, 'loops'], 0, ["loops: 1 redundant chain(s) on 1 net(s)", "L "]))
    CASES.append(("kpcb loops -o", ['kpcb.py', sb, 'loops', '-o', T('typed/s3.kicad_pcb')], 0,
                  ["loops: 3 item(s) selected", "-> "]))
    dn = dense_board(T('typed'))
    CASES.append(("kpcb fanout", ['kpcb.py', dn, 'fanout', 'U2'], 0,
                  ["0 routed, 1 escape on their layer (S 1), 1 need a dogbone via, 1 boxed in",
                   "U2.2       B                    boxed", "U2.3       V                    via     dogbone via 0.6/0.3",
                   "U2.1       E                    escape  F.Cu out S"]))
    CASES.append(("kpcb tracks detour", ['kpcb.py', dn, 'tracks', '--kind', 'detour'], 0,
                  ["detours (> 1.5x MST)      1 visible", "26.0 vs MST 16.0 mm, 0 via reroute D"]))
    CASES.append(("kpcb reroute", ['kpcb.py', dn, 'reroute', '-o', T('typed/dn2.kicad_pcb')], 0,
                  ["26.0 mm 0 via(s) (MST 16.0)  ->   16.0 mm 0 via(s)  REROUTED", "1 net(s) re-laid"]))
    CASES.append(("kpcb reroute result", ['kpcb.py', T('typed/dn2.kicad_pcb'), 'tracks', '--kind', 'detour'], 0,
                  ["detours (> 1.5x MST)      0 visible"]))
    CASES.append(("kpcb reroute failed", ['kpcb.py', dn, 'reroute', '--avoid', '-50,-50,100,100'], 0,   # the whole reason:
                  ["kept: the route failed (TP21.1 - FAILED: ", "it is covered by a rule area"]))       # it was cut at 70 chars
    CASES.append(("kpcb congest pending", ['kpcb.py', dn, 'congest'], 0,
                  ["congest: 3 unrouted link(s) over the copper on the board", "no cell over 50%"]))
    CASES.append(("kpcb congest hotspot", ['kpcb.py', channel_board(T('typed')), 'congest', '--cell', '1'], 0,
                  ["6 unrouted link(s)", "region(s) over 50%, worst first", "nets: N", "over capacity on every layer"]))
    gb = graze_board(T('typed'))
    CASES.append(("kpcb tracks pad ends", ['kpcb.py', gb, 'tracks', '--kind', 'pad'], 0,
                  ["ends at a pad edge        3 visible  (1 more end inside their pad off centre", "0.35 mm off TP7.1",
                   "fix: smooth --pads"]))
    CASES.append(("kpcb loops keeps a pad's only entry", ['kpcb.py', gb, 'loops', 'K'], 0, ["loops: no redundant chain"]))
    CASES.append(("kpcb smooth --pads", ['kpcb.py', gb, 'smooth', '--pads', '-o', T('typed/g2.kicad_pcb')], 0,
                  ["pads: 3 of 3 trace end(s)", "TP12.1", "wrote "]))
    CASES.append(("kpcb smooth --pads result", ['kpcb.py', T('typed/g2.kicad_pcb'), 'copper', '0,0,10,6'], 0,
                  ["1.000,1.000 -> 7.800,1.000", "8.000,4.000", "4.700,5.200 -> 5.000,5.500"]))
    CASES.append(("kpcb tracks anchor + joint", ['kpcb.py', gb, 'tracks', '--kind', 'anchor,joint'], 0,
                  ["ends off a small pad anchor    1 visible", "200 um off TP8.1", "150 um end to end    fix: smooth --joints"]))
    CASES.append(("kpcb smooth --joints", ['kpcb.py', gb, 'smooth', '--joints', '-o', T('typed/g3.kicad_pcb')], 0,
                  ["joints: 1 joint(s) held only by end caps closed", "150 um joint: 4.500,2.500 -> 4.650,2.500"]))
    CASES.append(("kpcb smooth --joints result", ['kpcb.py', T('typed/g3.kicad_pcb'), 'tracks', '--kind', 'joint'], 0,
                  ["joined only by end caps    0 visible"]))
    CASES.append(("kpcb diff --patch --base", ['kpcb.py', T('typed/g2.kicad_pcb'), 'diff', T('typed/g3.kicad_pcb'), '--patch',
                                               '--base', gb, '-o', T('typed/g4.kicad_pcb')], 0,   # --pads' edits + --joints'
                  ["1 trk changed;", "check ok: ", "with SCRATCH's 1 change(s)"]))
    gs = T('typed/gs.kicad_pcb')                 # SCRATCH moves J's joint end too, the other way: a clash
    open(gs, 'w').write(open(gb).read().replace('(end 4.5 2.5)', '(end 4.6 2.5)'))
    CASES.append(("kpcb diff --patch clash", ['kpcb.py', T('typed/g3.kicad_pcb'), 'diff', gs, '--patch', '--base', gb, '-o',
                                              T('typed/g5.kicad_pcb')], 0,
                  ["nothing to carry", "1 clash(es): changed on this board since", "check ok: "]))
    drb = drift_board(tmp.name)                  # 30 um of drift under 0.3 deg is off-45; E's only dogleg has a 42 um leg
    CASES.append(("kpcb tracks off45 drift", ['kpcb.py', drb, 'tracks', '--kind', 'off45'], 0,
                  ["off-45 segments           2 visible", "6.00 mm, end 30 um off 0 deg", "7.00 mm, end 30 um off 0 deg"]))
    CASES.append(("kpcb smooth drift", ['kpcb.py', drb, 'smooth', '-o', T('drift/t2.kicad_pcb')], 0,
                  ["chains: 2, re-laid 1 ", "2->2 segs  8.83->8.84 mm  at 1.00,2.00"]))
    CASES.append(("kpcb view --tracks", ['kpcb.py', sb, 'view', 'TP3', 'TP4', '--tracks', '--net', 'S', '-o',
                                         T('st.png')], 0, ["tracks/pads/vias, no fills", "S green"]))
    pb = prune_board(tmp.name)
    json.dump({'violations': [{'type': 'clearance', 'items': [{'uuid': 't1'}]}]}, open(T('prune.json'), 'w'))
    CASES.append(("kpcb ripup prune stays local", ['kpcb.py', pb, 'ripup', '--drc', T('prune.json')], 1,
                  ["ripup: 1 item(s) selected, 0 more pruned as dangling"]))
    CASES.append(("kpcb unhook", ['kpcb.py', pb, 'unhook', 'C1'], 1,
                  ["unhook: 3 item(s) selected, 0 more pruned",
                   "CUT  TP5.1 now off G's other 1 pad(s): its only link ran through C1", "add -o OUT"]))
    CASES.append(("kpcb tracks cleanup", ['kpcb.py', cleanup_board(tmp.name), 'tracks', '--kind', 'cleanup'], 0,
                  ["KiCad cleanup would change    8 visible", "8.000,5.000    collinear joint", "duplicate 4.00 mm segment",
                   "15.000,5.000    zero-length segment",
                   "0.40 mm wholly inside J1.1", "duplicate via", "6.000,11.000   collinear joint      KiCad merges",
                   "10.000,11.000   collinear joint after the dangling pass",
                   "6.000,13.000   collinear joint, one side necks KiCad may merge"]))
    dz = _tab_board(tmp.name, 'dupzone.kicad_pcb', 20, 10, _gzone('F.Cu', rect(2, 2, 10, 8), None, 'hand', net='P', uid='zh')
                    + _gzone('F.Cu', rect(3, 3, 9, 7), None, 'route P', net='P', uid='zr'))
    CASES.append(("kpcb tracks zonedup", ['kpcb.py', dz, 'tracks', '--kind', 'zonedup'], 0,
                  ["zones over own-net zone    1 visible", "'route P' 100% inside 'hand' delete the script band 'route P'"]))
    dz2 = _tab_board(tmp.name, 'dupzone2.kicad_pcb', 20, 10, _gzone('F.Cu', rect(3, 3, 9, 7), None, 'hand', net='P', uid='zh')
                     + _gzone('F.Cu', rect(2, 2, 10, 8), None, 'route P', net='P', uid='zr'))
    CASES.append(("kpcb tracks zonedup keeps a band round his zone", ['kpcb.py', dz2, 'tracks', '--kind', 'zonedup'], 0,
                  ["'hand' 100% inside 'route P' keep both: band 'route P' reaches 24.0 mm2 past 'hand'"]))
    CASES.append(("kpcb edit del teardrop", ['kpcb.py', pb, 'edit', 'del', 'td1', '-o', T('prune2.kicad_pcb')], 0,
                  ["1 teardrop(s) of deleted tracks dropped"]))
    with open(pb) as f:                       # the teardrop regenerated 0.5 mm over, under a new uuid
        tdm = f.read().replace('(xy 12 11.8) (xy 13 11.8) (xy 13 12.2) (xy 12 12.2)',
                               '(xy 12.5 11.8) (xy 13.5 11.8) (xy 13.5 12.2) (xy 12.5 12.2)').replace('"tz1"', '"tz2"')
    with open(T('tdmove.kicad_pcb'), 'w') as f:
        f.write(tdm)
    CASES.append(("kpcb diff teardrop moved", ['kpcb.py', T('tdmove.kicad_pcb'), 'diff', pb], 0,
                  ["teardrops: 1 -> 1: 1 moved, 0 added, 0 removed", "moved   Q F.Cu 12.50,12.00 -> 13.00,12.00"]))
    CASES.append(("kpcb smooth --overlaps keeps a via's centred end", ['kpcb.py', ovia_board(tmp.name), 'smooth', '--overlaps'],
                  0, ["overlaps: 0 deleted, 0 cut back"]))
    CASES.append(("kpcb smooth --overlaps deletes the doubled seg", ['kpcb.py', ovia_board(tmp.name, False), 'smooth',
                                                                       '--overlaps'], 0, ["overlaps: 1 deleted"]))
    CASES.append(("kpcb view --tracks two nets", ['kpcb.py', sb, 'view', 'TP3', 'TP4', '--tracks', '--net', 'S', '--net', 'L',
                                                  '-o', T('st2.png')], 0, ["S L green"]))
    CASES.append(("kpcb pairs stem", ['kpcb.py', rb, 'pairs', 'D_'], 0, ["pairs: 1 diff pair(s)"]))
    pc = prec_board(tmp.name)
    CASES.append(("kpcb copper full precision", ['kpcb.py', pc, 'copper', '9,5,11,6'], 0,
                  ["10.12345,5.500", "2.000,5.500 -> 10.12345,5.500"]))
    CASES.append(("kpcb edit seg snaps to a via centre", ['kpcb.py', pc, 'edit', 'seg', 'A', 'F.Cu', '0.2', '10.1239,5.5',
                                                          '10.1239,8', '-o', T('prec2.kicad_pcb')], 0, ["(snapped onto the centre"]))
    CASES.append(("kpcb edit seg snapped", ['kpcb.py', T('prec2.kicad_pcb'), 'copper', '9,5,11,9'], 0,
                  ["10.12345,5.500 -> 10.1239,8.000"]))
    CASES.append(("kpcb diff vias + box -v", ['kpcb.py', T('pe.kicad_pcb'), 'diff', po, '--box', '9,0,11,10', '-v'], 0,
                  ["added   P 0.6/0.3 10.000,8.000  free", "a SUM over them", "- F.Cu    w0.2  10.0000,5.6000", "~ F.Cu    w0.2->0.3"]))
    CASES.append(("kpcb tracks --box", ['kpcb.py', sb, 'tracks', '--box', '0,0,10,9'], 0, ["tracks in 0,0,10,9: "]))
    CASES.append(("kpcb widen --uniform", ['kpcb.py', sliver_board(tmp.name), 'widen', '--uniform', '--width', '0.01'], 0,
                  ["widen: 1 track(s)", "0.15 -> 0.3"]))
    CASES.append(("kpcb stitch --sparse", ['kpcb.py', sparse_board(tmp.name), 'stitch', 'GND', '--sparse', '5'], 0,
                  ["stitch GND --sparse 5", "via 0.6/0.3 at", "pour > 5 mm from a via:", "(dry run: -o OUT writes them, free)"]))
    stb = sparse_tht_board(tmp.name)
    CASES.append(("kpcb stitch --sparse THT anchor", ['kpcb.py', stb, 'stitch', 'GND', '--sparse', '5'], 0,
                  ["for 14.0 mm at 15.25,0.50", "worst 14.0 -> 4.7 mm"]))
    CASES.append(("kpcb stitch off a THT ring", ['kpcb.py', stb, 'stitch', 'GND', '28.5,5', '-r', '1.5', '--n', '4'], 0,
                  ["near 28.50,5.00: 28.50,6.30 (1.30 mm), 28.50,3.65 (1.35 mm)"]))
    mb = micro_board(tmp.name)
    CASES.append(("kpcb smooth --micro", ['kpcb.py', mb, 'smooth', '--micro', '-o', os.path.join(tmp.name, 'micro', 'm2.kicad_pcb')], 0,
                  ["micro: 1 segment(s) < 0.05 mm merged into a neighbour, 1 deleted (under other copper), 0 left"]))
    CASES.append(("kpcb smooth --micro result", ['kpcb.py', os.path.join(tmp.name, 'micro', 'm2.kicad_pcb'), 'tracks'], 0,
                  ["segments < 0.05 mm        0 visible", "tracks: 3 segments, 18.0 mm"]))
    pib = pwr_inpour_board(tmp.name)
    CASES.append(("kpcb tracks inpourpwr", ['kpcb.py', pib, 'tracks', '--kind', 'inpour,inpourpwr'], 0,
                  ["plane tracks inside fill    0 visible", "other tracks inside fill    1 visible",
                   "ripup PWR --inpour (opt-in: may it rely on its fill?)"]))
    CASES.append(("kpcb ripup NET --inpour non-plane", ['kpcb.py', pib, 'ripup', 'PWR', '--inpour', '-o',
                                                       os.path.join(tmp.name, 'pwrin2.kicad_pcb')], 0,
                  ["inpour: 1 track(s) wholly inside their own saved fill", "1 track(s) + 0 via(s) on 1 net(s)"]))
    CASES.append(("kpcb ripup --inpour leaves non-plane", ['kpcb.py', pib, 'ripup', '--inpour'], 0,
                  ["inpour: 0 plane-net track(s)"]))
    db = dead_board(tmp.name)
    CASES.append(("kpcb view --by-net", ['kpcb.py', db, 'view', '--box', '0,0,20,10', '--by-net', '-o',
                                         os.path.join(tmp.name, 'bynet.svg')], 0,
                  ["F.Cu/B.Cu by net, fills included, GND grey", "largest: P "]))
    CASES.append(("kpcb tracks deadend", ['kpcb.py', db, 'tracks', '--kind', 'deadend'], 0,
                  ["dead branches (no pad)    2 visible", "F.Cu/B.Cu 16.2 mm, 2 via, 6 mm2 pour off F.Cu track; ripup --deadend",
                   "df1 df2 db2 db1", "zone zband", "F.Cu 1.5 mm          off TP2.1; ripup --deadend", "cut live",
                   "KiCad's Cleanup takes none of it (every end of it joins something); ripup --deadend takes it all",
                   "KiCad's Cleanup takes live whole (it cannot cut a track back) and 2 more it then leaves dangling"]))
    sb = attach_stub_board(tmp.name)
    CASES.append(("kpcb tracks deadend attach stub", ['kpcb.py', sb, 'tracks', '--kind', 'deadend'], 0,
                  ["F.Cu 4.0 mm          off F.Cu track; ripup --deadend", "KiCad's Cleanup takes all of it and 1 more it "
                   "then leaves dangling: sstub"]))
    CASES.append(("kpcb ripup --deadend attach stub", ['kpcb.py', sb, 'ripup', '--deadend', '-o', T('astub2.kicad_pcb')], 0,
                  ["2 item(s) deleted (1 more pruned as dangling), 0 cut back"]))
    CASES.append(("kpcb check DEADCU", ['kpcb.py', db, 'check', '--only', 'DEADCU'], 0,
                  ["[WARN] DEADCU", "P F.Cu 1.5 mm off TP2.1 @16.00,5.00 serves no pad - `ripup --deadend P`"]))
    CASES.append(("kpcb net dead branch", ['kpcb.py', db, 'net', 'P'], 0,
                  ["dead    branch F.Cu/B.Cu 16.2 mm, 2 via, 6 mm2 pour off F.Cu track @6.00,5.00: serves no pad",
                   "zonedef zband  prio 0   B.Cu           'band'             5.50,7.60 .. 12.50,8.40"]))
    CASES.append(("kpcb ripup --deadend", ['kpcb.py', db, 'ripup', '--deadend', '-o', os.path.join(tmp.name, 'dead2.kicad_pcb')], 0,
                  ["deadend: 2 branch(es) serving no pad, 5 track(s), 2 via(s), 1 whole zone(s)",
                   "6 item(s) deleted (0 more pruned as dangling), 1 cut back, 1 zone(s)"]))
    CASES.append(("kpcb ripup --deadend result", ['kpcb.py', os.path.join(tmp.name, 'dead2.kicad_pcb'), 'tracks', '--kind', 'deadend'], 0,
                  ["dead branches (no pad)    0 visible"]))
    CASES.append(("kpcb diff --patch", ['kpcb.py', db, 'diff', os.path.join(tmp.name, 'dead2.kicad_pcb'), '--patch', '-o',
                                        os.path.join(tmp.name, 'dead3.kicad_pcb')], 0,
                  ["1 trk changed, 4 trk removed, 2 via removed, 1 zone removed", "(no --base: ", "check ok: "]))
    CASES.append(("kpcb tracks deadend band off a via cluster", ['kpcb.py', band_board(tmp.name), 'tracks', '--kind', 'deadend'], 0,
                  ["B.Cu 5.9 mm, 2 via, 3 mm2 pour off TP5.1", "qrun", "zone zq", "rdead rpiece"]))
    CASES.append(("kpcb unhook leaves no cycle", ['kpcb.py', db, 'unhook', 'TP4', '-o', os.path.join(tmp.name, 'dead3.kicad_pcb')], 0,
                  ["unhook: 1 item(s) selected, 5 more pruned as dangling", "4 trk  2 via"]))
    CASES.append(("kpcb fatten/stitch skip dead", ['kpcb.py', db, 'fatten', 'P', '--layers', 'B.Cu', '--minw', '0.2', '--width', '2', '-o',
                                                    os.path.join(tmp.name, 'dead4.kicad_pcb')], 0,
                  ["fatten P: 4 track(s) serve no pad, left out", "fatten P B.Cu: 1 track(s) >= 0.2 mm -> 1 zone(s)"]))
    ib = inpour_board(tmp.name)
    CASES.append(("kpcb tracks inpour", ['kpcb.py', ib, 'tracks', '--kind', 'inpour'], 0,
                  ["plane tracks inside fill    2 visible", "ripup --inpour"]))
    gs = _tab_board(tmp.name, 'gstub.kicad_pcb', 20, 10, _tab_fp('TP1', 6, 5, [('1', 0, 0, .6, .6, 'GND')], (.4, .4))
                    + _tseg(6, 5, 11, 5, 'GND', 0.3) + _gzone('F.Cu', rect(.5, .5, 19.5, 9.5), rect(.5, .5, 8, 9.5)))
    CASES.append(("kpcb tracks deadend plane stub", ['kpcb.py', gs, 'tracks', '--kind', 'deadend'], 0,
                  ["dead branches (no pad)    1 visible", "F.Cu 5.0 mm          off TP1.1; ripup --deadend"]))
    CASES.append(("kpcb ripup --inpour", ['kpcb.py', ib, 'ripup', 'GND', '--inpour'], 0,
                  ["inpour: 2 plane-net track(s) wholly inside their own saved fill, 1 run(s) kept", "(feeds TP1.1)",
                   "(dry run: 1 track(s)"]))
    CASES.append(("kpcb route leaves a stale pour's pad to the refill", ['kpcb.py', stale_pour_board(tmp.name), 'route', 'GND'],
                  0, ["GND: TP2.1 - left to the pour: TP2.1 sits in its F.Cu zone 'GND' and 4 spoke(s) land"]))
    jn = join_board(tmp.name)
    CASES.append(("kpcb tracks overlap", ['kpcb.py', jn, 'tracks', '--kind', 'overlap'], 0,
                  ["joined only through pad    1 visible", "two runs only through P1.1"]))
    CASES.append(("kpcb smooth --overlaps merge", ['kpcb.py', jn, 'smooth', '--overlaps', '-o', T('join/j2.kicad_pcb')], 0,
                  ["merge: 1 pair(s) of runs joined only through a pad", "wrote "]))
    CASES.append(("kpcb smooth --overlaps merge result", ['kpcb.py', T('join/j2.kicad_pcb'), 'tracks', '--kind', 'overlap'], 0,
                  ["joined only through pad    0 visible"]))
    jg = _tab_board(_typed_dir(T('joing')), 't.kicad_pcb', 20, 10,   # both runs near P1's top edge: one straight
                    _tab_fp('TP1', 4, 5.55, [('1', 0, 0, .6, .6, 'N')], (.4, .4))   # run 0.55 off its centre would only graze it
                    + _tab_fp('TP2', 16, 5.55, [('1', 0, 0, .6, .6, 'N')], (.4, .4)) + _tab_fp('P1', 10, 5, [('1', 0, 0, 1.0, 1.4, 'N')], (.6, .8))
                    + _tseg(4, 5.55, 9.8, 5.55, 'N', 0.3) + _tseg(10.2, 5.55, 16, 5.55, 'N', 0.3))
    CASES.append(("kpcb smooth --overlaps merge refuses a graze", ['kpcb.py', jg, 'smooth', '--overlaps', '-o', T('joing/j2.kicad_pcb')], 0,
                  ["merge: 0 pair(s) of runs joined only through a pad"]))
    mk = _tab_board(_typed_dir(T('mk')), 't.kicad_pcb', 16, 10,     # a 40 um side-step between 2 mm legs: either merge tilts one
                    _tab_fp('TP1', 6, 2, [('1', 0, 0, .6, .6, 'K')]) + _tab_fp('TP2', 10, 2.04, [('1', 0, 0, .6, .6, 'K')])
                    + _tseg(6, 2, 8, 2, 'K') + _tseg(8, 2, 8, 2.04, 'K') + _tseg(8, 2.04, 10, 2.04, 'K'))
    CASES.append(("kpcb smooth --micro keeps 0/45/90", ['kpcb.py', mk, 'smooth', '--micro', '-o', T('mk/m2.kicad_pcb')], 0,
                  ["micro: 0 segment(s) < 0.05 mm merged into a neighbour, 0 deleted (under other copper), 1 left",
                   "neighbours 40 um apart side to side (a micro lane jog): a merge tilts one"]))
    vc = _tab_board(tmp.name, 'viacut.kicad_pcb', 20, 10,          # the strap overshoots a live via 0.1 off its line
                    _tab_fp('TP1', 2, 5, [('1', 0, 0, 1, 1, 'P')], (.6, .6)) + _tab_fp('TP2', 16, 5.1, [('1', 0, 0, 1, 1, 'P')], (.6, .6))
                    + _tseg(2, 5, 10, 5, 'P', 0.3) + _tvia(8, 5.1, 'P') + _tseg(8, 5.1, 14, 5.1, 'P', 0.3, 'B.Cu')
                    + _tvia(14, 5.1, 'P') + _tseg(14, 5.1, 16, 5.1, 'P', 0.3))
    CASES.append(("kpcb ripup --deadend stubs onto an off-line via", ['kpcb.py', vc, 'ripup', '--deadend', '-o', T('viacut2.kicad_pcb')], 0,
                  ["ends in a via off its line: to 8,5 + a 0.3 mm stub onto the centre 8,5.1 (clear)",
                   "1 cut back (1 with a stub onto its via)"]))
    vb = _tab_board(_typed_dir(T('viacutb')), 't.kicad_pcb', 20, 10,   # a Q track 0.35 past the via centre blocks the stub
                    _tab_fp('TP1', 2, 5, [('1', 0, 0, 1, 1, 'P')], (.6, .6)) + _tab_fp('TP2', 16, 5.1, [('1', 0, 0, 1, 1, 'P')], (.6, .6))
                    + _tseg(2, 5, 10, 5, 'P', 0.3) + _tvia(8, 5.1, 'P') + _tseg(8, 5.1, 14, 5.1, 'P', 0.3, 'B.Cu')
                    + _tvia(14, 5.1, 'P') + _tseg(14, 5.1, 16, 5.1, 'P', 0.3) + _tseg(7, 5.45, 9, 5.45, 'Q', 0.2))
    CASES.append(("kpcb ripup --deadend leaves a blocked stub", ['kpcb.py', vb, 'ripup', '--deadend', '-o', T('viacutb/v2.kicad_pcb')], 0,
                  ["1 track(s) reported, not cut", "0 cut back"]))
    ip2 = _tab_board(tmp.name, 'inpour2.kicad_pcb', 20, 10,        # a via-to-via pair in the fill goes as one run; a leg whose
                     _tab_fp('TP1', 17, 5, [('1', 0, 0, .6, .6, 'GND')], (.4, .4))   # rest runs on out of the fill stays
                     + _tvia(3, 5, 'GND') + _tseg(3, 5, 6, 5, 'GND', 0.3) + _tseg(6, 5, 6, 8, 'GND', 0.3) + _tvia(6, 8, 'GND')
                     + _tvia(10, 5, 'GND') + _tseg(10, 5, 13, 5, 'GND', 0.3) + _tseg(13, 5, 17, 5, 'GND', 0.3)
                     + _gzone('F.Cu', rect(.5, .5, 19.5, 9.5), rect(.5, .5, 14, 9.5)))
    CASES.append(("kpcb ripup --inpour guards", ['kpcb.py', ip2, 'ripup', 'GND', '--inpour'], 0,
                  ["inpour: 3 plane-net track(s) wholly inside their own saved fill, 1 run(s) kept",
                   "(the rest would end loose @13.00,5.00)", "(dry run: 2 track(s)"]))
    sp2 = stubpad_board(tmp.name)
    CASES.append(("kpcb smooth keeps a pad a chain ran through", ['kpcb.py', sp2, 'smooth', '-o', T('stubpad/s2.kicad_pcb')],
                  0, ["chains: "]))
    CASES.append(("kpcb smooth keeps a pad: result", ['kpcb.py', T('stubpad/s2.kicad_pcb') if True else sp2, 'net', 'N'], 0,
                  ["copper  one piece joins all 2 pad(s)"]))
    tw = twin_board(tmp.name)
    CASES.append(("kpcb tracks twin", ['kpcb.py', tw, 'tracks', '--kind', 'twin'], 0,
                  ["twin runs into one pad    1 visible", "smooth --twins"]))
    CASES.append(("kpcb smooth --twins", ['kpcb.py', tw, 'smooth', '--twins', '-o', T('twin/t2.kicad_pcb')], 0,
                  ["twins: 1 pair(s)", "to R1.1: ", "-> 3.0", "to 13.00,4.75"]))
    CASES.append(("kpcb smooth --jogs partial", ['kpcb.py', jog_board(T('part'), True), 'smooth', '--jogs',
                                                 '-o', os.path.join(T('part'), 'nudge', 'j4.kicad_pcb')], 0,
                  ["jogs: 1 collapsed", "of the way (the jog is now"]))
    yield
    import kcommon, kdrc, kpcb_board, kpcb_copper, kpcb_fillet, kpcb_route, kpcb_smooth, kpcb_view, random, shutil                # the checks below call them in-process
    check(kpcb_smooth.selftest() == 'smooth geometry ok', "smooth geometry: staircase, chamfer, connectors, pad distance")
    ip = os.path.join(tmp.name, 'inproc'); os.makedirs(ip, exist_ok=True)   # own rules: tmp's .kicad_pro is another suite's
    open(os.path.join(ip, 'ip.kicad_pro'), 'w').write('{}')
    open(os.path.join(ip, 'ip.kicad_dru'), 'w').write('(version 1)\n')    # KiCad's defaults, said so: no WARN
    pp = os.path.join(ip, 'pours.kicad_pcb')
    sq = lambda x0, y0, x1, y1: f'(pts (xy {x0} {y0}) (xy {x1} {y0}) (xy {x1} {y1}) (xy {x0} {y1}))'   # noqa: E731
    open(pp, 'w').write('(kicad_pcb (version 20240108) (generator "pcbnew")'
                        ' (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))'
                        ' (gr_rect (start 0 0) (end 20 10) (layer "Edge.Cuts"))'
                        f' (zone (net "GND") (layer "F.Cu") (polygon {sq(0, 0, 10, 10)}) (filled_polygon (layer "F.Cu") {sq(.5, .5, 9.5, 9.5)}))'
                        f' (zone (net "P") (layer "F.Cu") (polygon {sq(12, 3, 16, 7)}) (filled_polygon (layer "F.Cu") {sq(12, 3, 16, 7)})))')
    g = kpcb_route.Grid(kpcb_board.Board(pp), 'A', (0, 0, 20, 10), 0.1, 0.2, 0.6, 0.3, ['F.Cu', 'B.Cu'])
    at = lambda x, y: int(round(y / 0.1)) * g.W + int(round(x / 0.1))                                   # noqa: E731
    ok8 = (not g.blk['F.Cu'][at(5, 5)] and g.pour['F.Cu'][at(5, 5)] and g.blk['F.Cu'][at(14, 5)]
           and not g.blk['B.Cu'][at(14, 5)] and g.vpour[at(14, 5)] and not g.vpour[at(5, 5)]
           and not g.vblk[at(14, 5)])
    check(ok8, "route: GND plane passable at a cost, a power-island pour blocks tracks, costs a via")
    # touches() with tol > cell/2 must scan the middle grid cell too (0.10 mm from the edge)
    sqi = kpcb_board.PolyIndex([(0.55, 0.55), (0.65, 0.55), (0.65, 0.95), (0.55, 0.95)])
    check(sqi.touches((0.75, 0.75), 0.3) and not sqi.touches((0.75, 0.75), 0.05),
                   "PolyIndex.touches scans every cell inside tol")
    # 2026-11-25 routing pass: a stroked gr_poly pad grows by half its stroke; the router grid keeps
    # a track off a hole by the hole rule (here 0.6, past ring + clearance); a width-step corner is
    # never cut; a board beside one other project is checked under that project's rules
    pr = kcommon.parse_sexp('(pad "1" smd custom (primitives (gr_poly (pts (xy 0 0) (xy 1 0) (xy 1 1)) (width 0.2))))')
    pr = pr[0] if isinstance(pr[0], list) else pr
    gb = kpcb_board.bbox([q for poly in kpcb_board.Board._pad_prims(pr) for q in poly])
    check(gb[0] < -0.09 and gb[3] > 1.09, f"stroked gr_poly pad not grown by its half-width: {gb}")
    hd = os.path.join(tmp.name, 'hole'); os.makedirs(hd, exist_ok=True)
    open(os.path.join(hd, 'h.kicad_dru'), 'w').write('(version 1)\n(rule "h" (constraint hole_clearance (min 0.6mm)))\n')
    seg = lambda x0, y0, x1, y1, w: (f' (segment (start {x0} {y0}) (end {x1} {y1}) (width {w}) (layer "F.Cu")'   # noqa: E731
                                     f' (net "S") (uuid "s{x0}{y0}{w}"))')
    open(os.path.join(hd, 'h.kicad_pcb'), 'w').write(
        '(kicad_pcb (version 20240108) (generator "pcbnew") (layers (0 "F.Cu" signal) (2 "B.Cu" signal)'
        ' (25 "Edge.Cuts" user)) (gr_rect (start 0 0) (end 10 10) (layer "Edge.Cuts"))'
        ' (footprint "x:TP" (layer "F.Cu") (at 5 5) (property "Reference" "TP1") (attr smd)'
        ' (pad "1" thru_hole circle (at 0 0) (size 0.5 0.5) (drill 0.2) (layers "*.Cu") (net "X")))'
        + seg(1, 1, 3, 1, 0.2) + seg(3, 1, 3, 3, 0.4) + seg(6, 1, 8, 1, 0.3) + seg(8, 1, 8, 3, 0.3) + ')')
    open(os.path.join(hd, 'h.kicad_pro'), 'w').write('{}')
    hb = kpcb_board.Board(os.path.join(hd, 'h.kicad_pcb'))
    g = kpcb_route.Grid(hb, 'S', (4, 4, 6, 6), 0.05, 0.2, 0.6, 0.3, ['F.Cu'])
    at = lambda x, y: g.blk['F.Cu'][round((y - g.y0) / g.res) * g.W + round((x - g.x0) / g.res)]   # noqa: E731
    check(at(5.75, 5) and not at(5.95, 5), "Grid: a track kept off a hole only by ring + clearance, not the hole rule")
    cn = kpcb_smooth.corner_nodes(hb, set(), kpcb_smooth.Index(hb))
    check([round(c[3][0]) for c in cn] == [8], f"corner_nodes: a width-step corner offered for a cut: {cn}")
    shutil.copy(os.path.join(hd, 'h.kicad_pcb'), os.path.join(hd, 'n.kicad_pcb'))
    bp, bs = kdrc.borrowed_copy(os.path.join(hd, 'n.kicad_pcb'))
    check(bs == 'h' and bp and os.path.exists(bp) and kdrc.borrowed_copy(os.path.join(hd, 'h.kicad_pcb')) == (None, None),
                   f"kdrc: a writer's output not checked under the project beside it: {bp} {bs}")
    if bp:
        shutil.rmtree(os.path.dirname(bp), ignore_errors=True)
    bnd = kpcb_board.Board(_tab_board(ip, 'band.kicad_pcb', 20, 10, _tab_fp('TP1', 1, 5, [('1', 0, 0, .6, .6, 'Q')])
                                      + _tab_fp('TP2', 18, 5, [('1', 0, 0, .6, .6, 'Q')]) + _tseg(1, 5, 18, 5, 'Q', 0.3)
                                      + _gzone('F.Cu', rect(3, 3, 4, 7), rect(3, 3, 4, 7), 'band', net='Q', uid='zq')))
    check(len(kpcb_copper.Copper(bnd, 'Q').pieces()) == 1, "Copper joins a fill crossing a track mid-span")
    # 1 x 1 roundrect pads (r 0.25), 0.1 mm tracks: Q's end 0.03 past the corner diagonally is
    # 0.146 off the rounded copper (the old box grown by w/2 joined it); R's end 0.04 off the
    # straight edge has its cap on the pad
    rr = lambda s: s.replace('smd rect', 'smd roundrect').replace('(layers "F.Cu")', '(layers "F.Cu")\n\t\t\t(roundrect_rratio 0.25)')  # noqa: E731
    rnd = kpcb_board.Board(_tab_board(ip, 'round.kicad_pcb', 20, 10, rr(
        _tab_fp('TP1', 5, 3, [('1', 0, 0, 1, 1, 'Q')]) + _tab_fp('TP2', 5, 7, [('1', 0, 0, 1, 1, 'R')]))
        + _tab_fp('TP3', 15, 3, [('1', 0, 0, .6, .6, 'Q')]) + _tab_fp('TP4', 15, 7, [('1', 0, 0, .6, .6, 'R')])
        + _tseg(15, 3, 5.53, 2.47, 'Q', 0.1) + _tseg(15, 7, 5.54, 7, 'R', 0.1)))
    check(len(kpcb_copper.Copper(rnd, 'Q').pieces()) == 2 and len(kpcb_copper.Copper(rnd, 'R').pieces()) == 1,
                   "Copper joins a cap on a roundrect's edge, not one past its rounded corner")
    # a 0.2 track along x + y = 11.1 passes 0.071 off TP1's corner (5.5,5.5): no end on TP1, its
    # centreline misses, its edge overlaps 29 um. KiCad joins it (CC2 / C33.1, 2026-10-28)
    clb = kpcb_board.Board(_tab_board(ip, 'clip.kicad_pcb', 12, 10, _tab_fp('TP1', 5, 5, [('1', 0, 0, 1, 1, 'Q')])
                                      + _tab_fp('TP2', 4.1, 7, [('1', 0, 0, .6, .6, 'Q')]) + _tseg(4.1, 7, 7, 4.1, 'Q', 0.2)))
    cq = kpcb_copper.Copper(clb, 'Q')
    co = cq.clip_only()
    check(len(cq.pieces()) == 1 and len(co) == 1 and co[0][1].ref == 'TP1' and abs(co[0][3] - 0.0293) < 1e-3,
                   "Copper joins a track body clipping a pad's corner; clip_only names it")
    rg = random.Random(7)
    pads = [p for f in kpcb_board.Board(PCB).fps.values() for p in f.pads] + [p for f in rnd.fps.values() for p in f.pads]
    agree = all(kpcb_copper.pad_within(p, pt, d, r) == (kpcb_copper.pad_dist(p, pt, r) <= d)
                for p in pads for _ in range(40)
                for pt in [(p['x'] + rg.uniform(-2, 2), p['y'] + rg.uniform(-2, 2))] for d in (-0.1, 0, 0.3)
                for r in (False, True))
    fl1, fl2, ns = {'pts': [(0, 0), (1, 0), (1, 1)]}, {'pts': [(5, 5), (6, 5), (6, 6)]}, type('B', (), {})()
    i1 = kpcb_board._pidx(ns, fl1)
    ns._pidx[id(fl2)] = (fl1, i1)                    # a freed fill's id now naming another fill
    check(agree and kpcb_board._pidx(ns, fl2) is not i1 and (5.5, 5.2) in kpcb_board._pidx(ns, fl2),
                   "pad_within agrees with pad_dist; _pidx never serves a reused id's index")
    # drop_layer: an F+B zone, F joining TP1/TP2, its B fill one fragment on a via joined by F:
    # B can go. A B.Cu pad TP3 in a second B fragment (via to F): B carries a pad, so no
    sq = lambda pts: ''.join(f'\t\t\t\t(xy {x} {y})\n' for x, y in pts)   # noqa: E731
    fz = lambda ly, pts: f'\t\t(filled_polygon\n\t\t\t(layer "{ly}")\n\t\t\t(pts\n{sq(pts)}\t\t\t)\n\t\t)\n'   # noqa: E731
    mz = lambda extra: ('\t(zone\n\t\t(net "Z")\n\t\t(layers "F.Cu" "B.Cu")\n\t\t(uuid "zz")\n\t\t(name "Z")\n'   # noqa: E731
                        f'\t\t(polygon\n\t\t\t(pts\n{sq(rect(1, 1, 19, 9))}\t\t\t)\n\t\t)\n'
                        + fz('F.Cu', rect(1, 1, 19, 9)) + fz('B.Cu', rect(8, 3, 10, 7)) + extra + '\t)\n')
    zb = _tab_fp('TP1', 3, 5, [('1', 0, 0, 1, 1, 'Z')]) + _tab_fp('TP2', 17, 5, [('1', 0, 0, 1, 1, 'Z')]) + _tvia(9, 5, 'Z')
    dz1 = kpcb_board.Board(_tab_board(ip, 'drop1.kicad_pcb', 20, 10, zb + mz('')))
    dz2 = kpcb_board.Board(_tab_board(ip, 'drop2.kicad_pcb', 20, 10, zb + _tvia(13, 5, 'Z')
                                      + _tab_fp('TP3', 15, 5, [('1', 0, 0, 1, 1, 'Z')]).replace('"F.Cu"', '"B.Cu"')
                                      + mz(fz('B.Cu', rect(12, 3, 17, 7)))))
    check(kpcb_copper.drop_layer(dz1, 'zz', 'B.Cu') == ['F.Cu'] and kpcb_copper.drop_layer(dz2, 'zz', 'B.Cu') is None
                   and kpcb_copper.drop_layer(dz1, 'zz', 'F.Cu') is None,
                   "drop_layer: a zone's B fill joining only an F-joined via can go; not with a pad on it")
    pj = kpcb_board.Board(_tab_board(ip, 'pj.kicad_pcb', 20, 10, rr(_tab_fp('P1', 10, 5, [('1', 0, 0, 1, 1, 'N')]))
                                     + _tab_fp('TP1', 5, 5, [('1', 0, 0, .6, .6, 'N')])
                                     + _tab_fp('TP2', 15, 5, [('1', 0, 0, .6, .6, 'N')])
                                     + _tseg(5, 5, 9.8, 5, 'N') + _tseg(10.2, 5, 15, 5, 'N') + _tseg(10, 5.2, 10.4355, 5.4355, 'N')))
    rows = kpcb_smooth.pad_joins(pj, set())
    check(len(rows) == 1 and rows[0][2] == 'P1.1' and len(rows[0][6]) == 1,
                   f"pad_joins on the drawn roundrect: a sliver capped past the corner arc is a bridge {[(r[2], len(r[6])) for r in rows]}")
    tk = lambda a, b, w: {'a': a, 'b': b, 'w': w, 'mid': ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)}   # noqa: E731
    fat = tk((0, 0), (5, 0), 3)                      # a 0.1 mm leg at 90 deg under its 1.5 mm end cap: hidden
    check(kpcb_smooth.leg_in_cap(tk((5, 0), (5, 0.1), 0.2), fat)
                   and not kpcb_smooth.leg_in_cap(tk((5, 0), (5, 1.5), 0.2), fat)
                   and not kpcb_smooth.leg_in_cap(fat, tk((5, 0), (5, 0.1), 0.2)),
                   "leg_in_cap: a stub under a fat end cap, not one poking out")
    win = (-1, -1, 6, 4)                             # straddles the outline corner
    gf = kpcb_route.Grid(rnd, 'Q', win, 0.05, 0.1, 0.6, 0.3, ['F.Cu'])
    gt = kpcb_route.Grid(rnd, 'Q', win, 0.05, 0.1, 0.6, 0.3, ['F.Cu'], vias=False)
    try:
        gt.vblk[0]
        rd = False
    except TypeError:
        rd = True                                    # reading the skipped raster fails loudly
    check(gf.blk == gt.blk and any(gf.blk['F.Cu']) and rd,
                   "Grid(vias=False) paints the same track raster, its via raster unreadable")
    q1 = kpcb_fillet.octilinear([(0, 0), (10, 0), (10.98, 1.0), (11, 5), (0, 5)])
    q2 = kpcb_fillet.octilinear([(0, 0), (4, 0), (5.732, 1), (0, 1)])
    check(sorted(q1) == [(0, 0), (0, 5), (10, 0), (11, 1), (11, 5)] and (5.732, 1.0) in q2,
                   f"octilinear: 45.6/89.7 deg edges snapped {q1}, 30 deg kept {q2}")
    vbox = kpcb_view.crop('<svg width="297mm" height="210mm" viewBox="0 0 297 210">', (10, 20, 30, 50))
    vpng = os.path.join(TMP, 'selftest_view.png')
    if shutil.which('kicad-cli') or shutil.which('kicad-cli-nightly'):
        vc, vo = run(['kpcb.py', PCB, 'view', 'U1', '-r', '1', '-o', vpng])
        vreal = vc == 0 and '6.8,6.8 - 13.2,13.2 mm' in vo and os.path.getsize(vpng) > 1000
    else:
        vreal, vo = True, 'kicad-cli not installed, plot skipped'
    ok13 = vbox == '<svg width="20mm" height="30mm" viewBox="10 20 20 30">' and vreal
    check(ok13, f"kpcb view crop + plot: {vo.strip()[-70:]}")
