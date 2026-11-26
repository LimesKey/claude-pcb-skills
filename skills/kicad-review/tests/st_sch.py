"""Self-test cases: ksch.py, ksheet.py, kproj.py, kfront.py (schematic side).

selftest.py runs suite(); see its docstring for the case format."""
import json, os, re
from st_common import CASES, KSCH, PCB2, REPEAT, check, svg2


def kproj_project(d):
    """a/ (navigator first, page 2) owns child c.kicad_sch (page 3) via sheet symbol
    U1; b/ is page 1. The board names c.kicad_sch on two footprints."""
    os.makedirs(d)
    open(os.path.join(d, 't.kicad_pro'), 'w').write(json.dumps(
        {'schematic': {'top_level_sheets': [{'filename': 'a.kicad_sch', 'name': 'A', 'uuid': 'ua'},
                                            {'filename': 'b.kicad_sch', 'name': 'B', 'uuid': 'ub'}]},
         'sheets': [['ua', 'A'], ['ub', 'B'], ['U1', 'C']]}, indent=2) + '\n')
    inst = lambda pg: f'\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "{pg}")\n\t\t)\n\t)\n'
    open(os.path.join(d, 'a.kicad_sch'), 'w').write(
        '(kicad_sch\n\t(version 20260830)\n\t(generator_version "10.99")\n\t(sheet\n\t\t(at 10 10)\n'
        '\t\t(uuid "U1")\n\t\t(property "Sheetname" "C")\n\t\t(property "Sheetfile" "c.kicad_sch")\n'
        '\t\t(instances\n\t\t\t(project "t"\n\t\t\t\t(path "/ua"\n\t\t\t\t\t(page "3")\n'
        '\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)\n' + inst(2) + ')\n')
    open(os.path.join(d, 'b.kicad_sch'), 'w').write('(kicad_sch\n' + inst(1) + ')\n')
    open(os.path.join(d, 'c.kicad_sch'), 'w').write('(kicad_sch\n)\n')
    open(os.path.join(d, 't.kicad_pcb'), 'w').write(
        '(kicad_pcb\n\t(footprint "R"\n\t\t(sheetfile "c.kicad_sch")\n\t)\n'
        '\t(footprint "C"\n\t\t(sheetfile "c.kicad_sch")\n\t)\n)\n')
    return d


def front_project(d):
    """main.kicad_sch (page 1) holds U8 (BQ25798) and J1; front.kicad_sch (page 2,
    no parts) quotes them: a right pair, a wrong address, a wrong part, a missing
    ref, a range running past J1, and a cover page table one row stale."""
    os.makedirs(d)
    open(os.path.join(d, 't.kicad_pro'), 'w').write(json.dumps(
        {'schematic': {'top_level_sheets': [{'filename': 'main.kicad_sch', 'name': 'Main', 'uuid': 'um'},
                                            {'filename': 'front.kicad_sch', 'name': 'Front', 'uuid': 'uf'}]}},
        indent=2) + '\n')
    open(os.path.join(d, 't.net'), 'w').write(
        '(export (version "E") (design (source "main.kicad_sch") (sheet (number "1") (name "/Main/"))'
        ' (sheet (number "2") (name "/Front/"))) (components'
        ' (comp (ref "U8") (value "BQ25798") (libsource (lib "x") (part "c")) (sheetpath (names "/Main/")))'
        ' (comp (ref "J1") (value "USB") (libsource (lib "x") (part "j")) (sheetpath (names "/Main/"))))'
        ' (libparts) (nets (net (code "1") (name "N") (node (ref "U8") (pin "1")) (node (ref "J1") (pin "1")))))')
    txt = lambda s, x, y: f' (text "{s}" (at {x} {y} 0))'
    cell = lambda s, pg: f' (table_cell "{s}" (at 0 0 0) (effects (href "#{pg}")))'
    open(os.path.join(d, 'main.kicad_sch'), 'w').write('(kicad_sch (sheet_instances (path "/" (page "1"))))')
    open(os.path.join(d, 'front.kicad_sch'), 'w').write(
        '(kicad_sch' + txt('BQ25798 (U8)', 50, 50) + txt('0x6A', 50, 52) + txt('TPS25751 (U8)', 90, 50)
        + txt('debug header U99', 90, 60) + txt('USB (J1-J2)', 90, 70) + txt('CHARGER (E2-E0 by U8)', 90, 80)
        + ' (table (column_count 2) (cells' + cell('PAGE', 1) + cell('SHEET', 1) + cell('1', 1) + cell('Main', 1)
        + cell('2', 3) + cell('Front', 3) + '))' + ' (sheet_instances (path "/" (page "2"))))')
    return os.path.join(d, 't.net')


def lint2_project(d):
    """C1 and C2 (horizontal) feed one vertical GND wire at x=50 from opposite sides
    with no GND symbol on it (SHUNTBUS, both forms); R9's reference sits on C2's
    value (TEXTOVER). A pages/ project: navigator B, A; pages A=1, its child C=3, B=2."""
    os.makedirs(d)
    lib = ('(lib_symbols (symbol "x:C" (pin_names (hide yes)) (pin_numbers (hide yes))'
           ' (symbol "C_0_1" (rectangle (start -0.5 1) (end 0.5 -1)))'
           ' (symbol "C_1_1" (pin passive line (at 0 2.54 270) (length 1.27) (name "~") (number "1"))'
           ' (pin passive line (at 0 -2.54 90) (length 1.27) (name "~") (number "2")))))')
    fld = lambda k, v, x, y: f' (property "{k}" "{v}" (at {x} {y} 0) (effects (font (size 1.27 1.27))))'
    sym = lambda ref, val_, x, y, rx, ry: (f' (symbol (lib_id "x:C") (at {x} {y} 90) (unit 1)'
                                          + fld('Reference', ref, rx, ry) + fld('Value', val_, x, y + 3) + ')')
    open(os.path.join(d, 'lint2.kicad_sch'), 'w').write(
        '(kicad_sch ' + lib + sym('C1', '1u', 45, 50, 45, 47) + sym('C2', '1u', 55, 50, 55, 47)
        + sym('R9', 'x', 70, 70, 55.3, 53)
        + ' (wire (pts (xy 50 40) (xy 50 60))) (wire (pts (xy 47.54 50) (xy 50 50)))'
        ' (wire (pts (xy 50 50) (xy 52.46 50))) (sheet_instances (path "/" (page "1"))))')
    open(os.path.join(d, 'lint2.net'), 'w').write(
        '(export (version "E") (design (source "lint2.kicad_sch") (sheet (number "1") (name "/")))'
        ' (components' + ''.join(f' (comp (ref "{r}") (value "1u") (libsource (lib "x") (part "C")))'
                                 for r in ('C1', 'C2', 'R9')) + ')'
        ' (nets (net (code "1") (name "GND") (node (ref "C1") (pin "2")) (node (ref "C2") (pin "1")))'
        ' (net (code "2") (name "/A") (node (ref "C1") (pin "1"))) (net (code "3") (name "/B") (node (ref "C2") (pin "2")))))')
    pg = os.path.join(d, 'pages')
    os.makedirs(pg)
    open(os.path.join(pg, 't.kicad_pro'), 'w').write(
        '{"schematic": {"top_level_sheets": [{"filename": "b.kicad_sch", "name": "B"},'
        ' {"filename": "a.kicad_sch", "name": "A"}]}}')
    open(os.path.join(pg, 'a.kicad_sch'), 'w').write(
        '(kicad_sch (sheet (at 10 10) (size 10 10) (property "Sheetname" "C") (property "Sheetfile" "c.kicad_sch")'
        ' (instances (project "t" (path "/u1" (page "3"))))) (sheet_instances (path "/" (page "1"))))')
    open(os.path.join(pg, 'b.kicad_sch'), 'w').write('(kicad_sch (sheet_instances (path "/" (page "2"))))')
    open(os.path.join(pg, 'c.kicad_sch'), 'w').write('(kicad_sch)')
    return os.path.join(d, 'lint2.net'), pg


def suite(tmp, mini):
    """Append this file's cases to CASES, yield while the runner runs them, then do the
    ad-hoc checks (the full run only: -k stops at the yield)."""
    CASES.append(("ksch syms", ['ksch.py', 'syms'], 0, ["anchor at", "resistor (IEC box"]))
    CASES.append(("ksch help", ['ksch.py', 'help'], 0, ["render a KiCad-convention schematic"]))
    CASES.append(("ksch render",  ['ksch.py', 'render', '-o', svg2, KSCH],   0, ['!ERROR', '!overlaps']))
    # J1 -> J2 only through the crossing at 5,5: 2 x 7.071 mm of 0.3 x 0.035 = 23.17 mohm by hand
    # one resistor in a sheet used twice: R1 in /A/, R2 in /B/, each on its own nets
    CASES.append(("ksheet repeated sheet", ['ksheet.py', REPEAT, 'sch', 'R2', '-r', '7'], 0,
                  ["sheet sub.kicad_sch (/B/)", "100,96.19         /B/SIG", "SIG (label) at 100,90  /B/SIG"]))
    lnet = os.path.join(tmp.name, 'lint', 'lint.net')
    wide = os.path.join(tmp.name, 'wide.ksch')
    open(wide, 'w').write('r R1 0,0 v 1k\nr R2 120,0 v 1k\nwire R1.2 R2.2\n')
    CASES.append(("ksch --paper", ['ksch.py', 'check', '--paper', 'A4', wide], 0,
                  ["over A4's usable 277 x 190 mm"]))
    l2net, pages = lint2_project(os.path.join(tmp.name, 'lint2'))
    fn = front_project(os.path.join(tmp.name, 'front'))
    CASES.append(("kfront check", ['kfront.py', fn, 'check'], 2,
                  ["0x6A under \"BQ25798 (U8)\" but `knet i2c` gives 0x6B for U8",
                   "\"TPS25751 (U8)\" but U8 is BQ25798", "U99 is not in the netlist", "J2 is not in the netlist",
                   "4 error(s)"]))
    CASES.append(("kfront pages", ['kfront.py', fn, 'pages'], 2, ["row 2: page 2 links to #3"]))
    kp = kproj_project(os.path.join(tmp.name, 'kproj'))
    for lab, args, ex, want in (
            ("kproj renumber", ['renumber'], 0, ["a.kicad_sch: 1 page 2 -> 1 (A)", "page 3 -> 2 (C in a.kicad_sch)",
                                                "b.kicad_sch: 1 page 1 -> 3 (B)"]),
            ("kproj rename", ['rename', 'c.kicad_sch', 'd.kicad_sch'], 0,
             ["a.kicad_sch: 1 Sheetfile c.kicad_sch -> d.kicad_sch", "t.kicad_pcb: 2 (sheetfile) c.kicad_sch -> d.kicad_sch"]),
            ("kproj order", ['order', 'B'], 0, ["navigator order B, A"]),
            ("kproj add-sheet", ['add-sheet', 'n.kicad_sch', 'N', '--after', 'B'], 0,
             ["n.kicad_sch: created", "at position 2", "n.kicad_sch: 1 page 0 -> 2 (N)"]),
            ("kproj refuses on a lock", ['renumber'], 3, ["KiCad holds the project"])):
        if lab.endswith('lock'):         # a second copy, so the sequence above still runs
            kp = kproj_project(os.path.join(tmp.name, 'kproj2'))
            open(os.path.join(kp, '~a.kicad_sch.lck'), 'w').close()
        else:                            # a KiCad open on any project must not fail the edits
            args = args + ['--force']
        CASES.append((lab, ['kproj.py', kp] + args, ex, want))
    CASES.append(("ksheet lint shunt+text", ['ksheet.py', l2net, 'lint', '--only', 'SHUNTBUS,TEXTOVER'], 2,
                  ["C1 C2: horizontal 2-pin shunts into one vertical GND wire at x=50 with no GND symbol within any distance",
                   "C1 and C2 meet the vertical GND wire at 50,50 from opposite sides",
                   "C2 value '1u' overlaps R9 reference 'R9'"]))
    CASES.append(("ksheet labelspot", ['ksheet.py', l2net, 'labelspot', 'GND'], 0,
                  ["label 'GND' on GND:", "lint2.kicad_sch      at 50 50.8 270  justify right bottom  clear 2.54 mm",
                   '(label "GND" (at 50 50.8 270)']))
    CASES.append(("ksheet labelspot none", ['ksheet.py', l2net, 'labelspot', '/A', 'X'], 1, ["no wire of it"]))
    CASES.append(("ksheet lint", ['ksheet.py', lnet, 'lint'], 2,
                  ["R1's body", "/NA ends at 70,40 and /NB starts 2.54 mm", "U1.1 (A) at 94.92,94.92: /J runs 1.27 mm",
                   "U1: 1 object(s) within 2.54 mm of its pin ends: R3.2 (1.27 mm from pin 2)"]))
    CASES.append(("ksheet sch", ['ksheet.py', lnet, 'sch', 'U1', '-r', '2'], 0,
                  ["1     A            L     94.92,94.92       /J", "body 97.46,93.65 - 102.54,108.89",
                   "R3         at 89.84,97.46  1 unconnected, 2 /L"]))
    yield
    import argparse, kcommon, kcommon as kc, kfront, kmerge, kpcb_board, ksch, ksheet                # the checks below call them in-process
    cov = os.path.join(tmp.name, 'cover.kicad_sch')
    cell = lambda t, x, y, pg: (f'\n\t\t\t(table_cell "{t}"\n\t\t\t\t(at {x} {y} 0)\n\t\t\t\t(effects\n\t\t\t\t\t(href "#{pg}")'
                                f'\n\t\t\t\t)\n\t\t\t\t(uuid "u{t}{y}")\n\t\t\t)')         # noqa: E731
    open(cov, 'w').write('(kicad_sch\n\t(table\n\t\t(column_count 2)\n\t\t(row_heights 6 6)\n\t\t(cells'
                         + cell('PAGE', 10, 20, 1) + cell('SHEET', 22, 20, 1) + cell('1', 10, 26, 1) + cell('Main', 22, 26, 1)
                         + '\n\t\t)\n\t)\n)\n')
    kfront.write_table(cov, [('1', 'Main'), ('2', 'Front')], cov + '2')
    t2 = open(cov + '2').read()
    check(re.findall(r'table_cell "([^"]*)"', t2) == ['PAGE', 'SHEET', '1', 'Main', '2', 'Front']
                   and '(row_heights 6 6 6)' in t2 and '(at 10 32 0)' in t2 and '(href "#2")' in t2,
                   "kfront pages -o: a missing row added below the last, href and row height with it")
    pd, keep = os.path.join(tmp.name, 'cache'), kcommon.CACHE
    os.makedirs(os.path.join(pd, 'svg', 'old'))
    for i, f in enumerate(('svg/old/a.svg', 'svg/old/b.svg', 'old.bin', 'new.bin')):
        open(os.path.join(pd, f), 'wb').write(b'x' * 100)
        os.utime(os.path.join(pd, f), (i, i))
    os.utime(os.path.join(pd, 'svg', 'old'), (1, 1))
    kcommon.CACHE = pd
    kcommon.cache_prune(250)
    kcommon.CACHE = keep
    ok8 = sorted(os.listdir(pd)) == ['new.bin', 'old.bin', 'svg'] and not os.listdir(os.path.join(pd, 'svg'))
    # kmerge's raw round trip: an escaped string survives parse -> dump byte-exact
    tree = kcommon.parse_sexp('(design (source "C:\\\\x \\"q\\"") (n 1))', mark='\0')
    ok8 &= kcommon.parse_sexp(kmerge.dump(tree), mark='\0') == tree and \
        kmerge.val(tree, 'source') == 'C:\\x "q"' and kmerge.q('C:\\x "q"') == tree[1][1]
    # the regen root is <pro>.kicad_sch, not a front-matter page listed first (exports empty)
    pr = os.path.join(tmp.name, 'proot')
    os.makedirs(pr)
    open(os.path.join(pr, 'p.kicad_pro'), 'w').write(
        '{"schematic": {"top_level_sheets": [{"filename": "front.kicad_sch"}, {"filename": "p.kicad_sch"}]}}')
    for f in ('front', 'p'):
        open(os.path.join(pr, f + '.kicad_sch'), 'w').close()
    ok8 &= kcommon.project_root(pr) == 'p.kicad_sch' and kcommon.project_root(pages) == 'b.kicad_sch'
    check(ok8, "cache_prune drops oldest/whole dirs; kmerge escaped round trip; project_root")
    pa = argparse.ArgumentParser(add_help=False)
    pa.add_argument('args', nargs='*'); pa.add_argument('--net', default=''); pa.add_argument('-d', default='')
    pn = kcommon.parse_args(pa, ['net', '-BATT', '--net', '-VIN', '-dX', '-40'])
    open(os.path.join(tmp.name, '~t.kicad_sch.lck'), 'w').close()
    ok15 = pn.args == ['net', '-BATT', '-40'] and pn.net == '-VIN' and pn.d == 'X' \
        and any('lock file' in r for r in kcommon.kicad_running(tmp.name))
    check(ok15, f"parse_args dash values {pn.args} --net {pn.net}; lock guard")
    # ad-hoc scripts guess dict access on FP and Zone; both answer it, the tuple unpack stays
    zb = kpcb_board.Board(PCB2); z, f = zb.zones[0], next(iter(zb.fps.values()))
    n_, l_ = z
    check(z['net'] == z.net == z.get('net') == n_ == z[0] and z['layers'] == l_ and z.get('x', 1) == 1
                   and f['pads'] is f.pads and f.get('nope') is None and vars(f)['ref'] == dict(f)['ref'] == f.ref
                   and '_edge' not in vars(f), "FP / Zone dict-style access (vars, dict, items too)")
    po = ksheet.page_order(pages)[0]
    ok16 = [x['rule'] for x in po] == ['PAGEORDER', 'NAVORDER'] and '1 /A/, 3 /A/C/, 2 /B/' in po[0]['msg'] \
        and kcommon._xf(1, 0, 270, 'x') == (0, -1) and kcommon._xf(1, 0, 90, '') == (0, -1)
    check(ok16, f"ksheet PAGEORDER/NAVORDER {[x['rule'] for x in po]}; _xf rotate-then-mirror")
    kd = ksch.Doc({})
    kd.parse('c C1 0,0 h 10nF\nntc T1 0,3 hr 10k\nnote 0,6 "a long note running right"\nnote 4,6 x')
    cv = [f[2] for f in kd.syms['C1'].fields() if f[-1] == 'val'][0]
    tr = [f[2] for f in kd.syms['T1'].fields() if f[-1] == 'ref'][0]
    ow = [m for _sv, m in ksch.check_doc(kd) if 'overlaps' in m]
    ok11 = tr - .35 > cv + .075 and len(ow) == 1 and "'x'" in ow[0]
    check(ok11, f"ksch row-pitch text: C1 value {cv:.2f}, T1 ref {tr:.2f}; {ow}")
    # an ic's top pin name sits inside its body, clear of the first left pin's name
    pr, _pn, bb = ksch.s_ic({'L': [('2', 'ENABLE')], 'T': [('1', 'VCC_RF')], 'B': [('3', 'GND')]})
    tt = [q for q in pr if q[0] == 't']
    tn = next(q for q in tt if q[3] == 'VCC_RF')
    w = ksch.twid('VCC_RF', tn[4])
    t0, t1 = (tn[2], tn[2] + w) if tn[5] == 'end' else (tn[2] - w, tn[2])
    ln = next(q for q in tt if q[3] == 'ENABLE')
    bn = next(q for q in tt if q[3] == 'GND')
    ok12 = 0 < t0 and t1 < ln[2] - .35 and bn[2] < bb[3] and bn[2] - ksch.twid('GND', bn[4]) > ln[2]
    check(ok12, f"ksch ic top/bottom pin names inside the body: VCC_RF y {t0:.2f}..{t1:.2f}, "
          f"ENABLE baseline {ln[2]:.2f}, body h {bb[3]:.2f}")
    # ksch papercuts: KiCad's junction rule (a wire through a pin end gets a dot, two
    # wires up one stub from a pin do not), an ic with bottom pins keeps its value
    # above the body, a TVS2200-style part maps onto a diode (GND = anode), and a
    # note laid over a wire is reported
    j = (ksch.junctions([((0, 0), (4, 0))], [(2, 0)]), ksch.junctions([((0, 0), (0, -1)), ((0, -1), (0, 0))], [(0, 0)]))
    sy = ksch.Sym('ic', 'U9', 0, 0, sides={'L': [('1', 'IN')], 'B': [('2', 'GND')]}, value='X')
    vy = [f[2] for f in sy.fields() if f[-1] == 'val']
    bn = ksch.by_name(ksch.s_d('dz')[1], {'1': ('IN', 'p'), '2': ('GND', 'p'), '3': ('IN', 'p'), '7': ('EP', 'p')})
    kx = ksch.Doc({})
    kx.parse('r R1 0,0 h 1k\nr R2 6,0 h 1k\nwire R1.2 R2.1\nnote 2.5,0.2 "over the wire"')
    cr = [m for _s, m in ksch.check_doc(kx) if 'running through' in m]
    ok17 = j == ([(2, 0)], []) and vy and vy[0] < sy.bbox()[1] and bn \
        and bn[1] == {'1': 'k', '2': 'a', '3': 'k', '7': 'a'} and len(cr) == 1 and 'over the wire' in cr[0]
    check(ok17, f"ksch junction rule {j}, ic value above body, TVS pin map, text-over-wire")
    lib = kc.parse_sexp('(symbol "x:U" (symbol "U_0_1" (rectangle (start -5.08 5.08) (end 5.08 -5.08)))'
                        ' (symbol "U_1_1" (pin input line (at -7.62 2.54 0) (length 2.54) (name "IN") (number "1"))'
                        ' (pin output line (at 7.62 0 180) (length 2.54) (name "OUT") (number "2"))'
                        ' (pin power_in line (at 0 -7.62 90) (length 2.54) (name "GND") (number "3"))'
                        ' (pin power_in line (at 0 -7.62 90) (length 2.54) (name "GND") (number "4"))))')
    _pr, lp, lbb, lnm = ksch.s_lib(lib, 1)
    spr = ksch.stretch(*ksch.s_r(), 3)[1]
    ok18 = lp == {'1': (-1.0, 1.0, 'L'), '2': (5.0, 2.0, 'R'), '3': (2.0, 5.0, 'D'), '4': (2.0, 5.0, 'D')} \
        and lbb == (0.0, 0.0, 4.0, 4.0) and lnm['2'] == 'OUT' and spr == {'1': (0, 0, 'U'), '2': (0, 3, 'D')}
    check(ok18, f"ksch lib-symbol geometry 1:1 {lbb}, stretched R span {spr['2'][1]}")
