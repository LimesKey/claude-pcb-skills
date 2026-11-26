"""Self-test cases: knet.py (netlist queries and checks), kverify.py, kmerge.py.

selftest.py runs suite(); see its docstring for the case format."""
import os
from st_common import CASES, NET, REPEAT, TMP, check, run, svg1


def also_net(d):
    """U1.1 on the global net IRQ with two other ICs and a pull-up: `draw U1` puts
    the other ICs on a note line of their own."""
    os.makedirs(os.path.join(d, 'also'))                # no sidecar .kicad_sch beside it
    p = os.path.join(d, 'also', 'also.net')
    ic = lambda r: f' (comp (ref "{r}") (value "IC") (libsource (lib "x") (part "ic3")))'
    nd = lambda *rp: ''.join(f' (node (ref "{r}") (pin "{q}"))' for r, q in rp)
    open(p, 'w').write(
        '(export (version "E") (design (source "also.kicad_sch"))'
        ' (components' + ic('U1') + ic('U2') + ic('U3')
        + ' (comp (ref "R1") (value "10k") (libsource (lib "Device") (part "R"))))'
        ' (libparts (libpart (lib "x") (part "ic3") (pins (pin (num "1") (name "IRQ") (type "output"))'
        ' (pin (num "2") (name "A") (type "input")) (pin (num "3") (name "B") (type "input"))))'
        ' (libpart (lib "Device") (part "R") (pins (pin (num "1") (name "~") (type "passive"))'
        ' (pin (num "2") (name "~") (type "passive")))))'
        ' (nets (net (code "1") (name "IRQ")' + nd(('U1', '1'), ('U2', '1'), ('U3', '1'), ('R1', '1')) + ')'
        ' (net (code "2") (name "VP")' + nd(('R1', '2')) + ')'
        ' (net (code "3") (name "/A")' + nd(('U1', '2'), ('U2', '2'), ('U3', '2')) + ')'
        ' (net (code "4") (name "/B")' + nd(('U1', '3'), ('U2', '3'), ('U3', '3')) + ')))')
    return p


def xref_net(d):
    """U1.2 -> R1 -> /B -> R2 -> GND, and U1.3 on /B too: the second visit to /B is
    one stub row naming the parts drawn above (rows were allocated that way)."""
    os.makedirs(os.path.join(d, 'xref'))
    p = os.path.join(d, 'xref', 'xref.net')
    r = lambda q: f' (comp (ref "{q}") (value "10k") (libsource (lib "Device") (part "R")))'
    nd = lambda *rp: ''.join(f' (node (ref "{a}") (pin "{q}"))' for a, q in rp)
    open(p, 'w').write(
        '(export (version "E") (design (source "xref.kicad_sch"))'
        ' (components (comp (ref "U1") (value "IC") (libsource (lib "x") (part "ic3")))' + r('R1') + r('R2') + ')'
        ' (libparts (libpart (lib "x") (part "ic3") (pins (pin (num "1") (name "IRQ") (type "output"))'
        ' (pin (num "2") (name "A") (type "input")) (pin (num "3") (name "B") (type "input"))))'
        ' (libpart (lib "Device") (part "R") (pins (pin (num "1") (name "~") (type "passive"))'
        ' (pin (num "2") (name "~") (type "passive")))))'
        ' (nets (net (code "1") (name "/A")' + nd(('U1', '2'), ('R1', '1')) + ')'
        ' (net (code "2") (name "/B")' + nd(('R1', '2'), ('U1', '3'), ('R2', '1')) + ')'
        ' (net (code "3") (name "GND")' + nd(('R2', '2')) + ')))')
    return p


def multi_net(d):
    """U1 with a BAT54S (D1), a Kelvin R_Shunt (R1) and a Device:D (D2, pin 1 = K)
    on its pins: real symbols, every pin ended, and D2's cathode toward U1."""
    os.makedirs(os.path.join(d, 'multi'))
    p = os.path.join(d, 'multi', 'multi.net')
    pins = lambda *pn: ' (pins' + ''.join(f' (pin (num "{n}") (name "{m}") (type "passive"))'
                                          for n, m in pn) + ')'
    comp = lambda r, v, lib, part: f' (comp (ref "{r}") (value "{v}") (libsource (lib "{lib}") (part "{part}")))'
    nd = lambda *rp: ''.join(f' (node (ref "{r}") (pin "{q}"))' for r, q in rp)
    open(p, 'w').write(
        '(export (version "E") (design (source "multi.kicad_sch"))'
        ' (components' + comp('U1', 'IC', 'x', 'ic3') + comp('D1', 'BAT54S', 'Diode', 'BAT54S')
        + comp('R1', '5m', 'Device', 'R_Shunt') + comp('D2', 'BZX', 'Device', 'D')
        + comp('R2', '1k', 'Device', 'R') + ')'
        ' (libparts (libpart (lib "x") (part "ic3")' + pins(('1', 'IN'), ('2', 'CS'), ('3', 'G')) + ')'
        ' (libpart (lib "Diode") (part "BAT54S")' + pins(('1', 'A'), ('2', 'K'), ('3', 'COM')) + ')'
        ' (libpart (lib "Device") (part "R_Shunt")' + pins(('1', ''), ('2', ''), ('3', ''), ('4', '')) + ')'
        ' (libpart (lib "Device") (part "D")' + pins(('1', 'K'), ('2', 'A')) + ')'
        ' (libpart (lib "Device") (part "R")' + pins(('1', '~'), ('2', '~')) + '))'
        ' (nets (net (code "1") (name "GND")' + nd(('D1', '1'), ('R1', '1'), ('R1', '4'), ('D2', '2'), ('R2', '2')) + ')'
        ' (net (code "2") (name "/NIN")' + nd(('U1', '1'), ('D1', '2')) + ')'
        ' (net (code "3") (name "/MID")' + nd(('D1', '3'), ('R2', '1')) + ')'
        ' (net (code "4") (name "/NCS")' + nd(('U1', '2'), ('R1', '2')) + ')'
        ' (net (code "5") (name "/NCSN")' + nd(('R1', '3')) + ')'
        ' (net (code "6") (name "/NG")' + nd(('U1', '3'), ('D2', '1')) + ')))')
    return p


def power_net(d):
    """BT1 -> F1 -> VSYS -> U1 buck (SW -> L1, FB 402k/174k) -> +3V3 -> U3 eFuse (ILM
    549 R to GND) -> 3V3_OUT -> U2; and J1 VBUS -> R5 0 R -> VSYS, a second way in.
    +3V3 -> D1 Schottky -> U4 switch IN -> +3V3_EXT (a series diode is a link); U4's
    open-drain ST sinks R6 -> LED D2 -> +3V3 (resistor first: still a pull-up).
    knet.json beside it gives VFB and the ILIM table row."""
    os.makedirs(os.path.join(d, 'pwr'))
    open(os.path.join(d, 'pwr', 'knet.json'), 'w').write(
        '{"vref": {"BUCK": 1.0}, "ilim": {"TPS25947": {"549": "5.40/6.07/6.60 A"}}}')
    p = os.path.join(d, 'pwr', 'pwr.net')
    pins = lambda *pn: ' (pins' + ''.join(f' (pin (num "{i + 1}") (name "{m}") (type "passive"))'
                                          for i, m in enumerate(pn)) + ')'
    comp = lambda r, v, part: f' (comp (ref "{r}") (value "{v}") (libsource (lib "x") (part "{part}")))'
    net = lambda c, name, *rp, cls='Default': (f' (net (code "{c}") (name "{name}") (class "{cls}")'
                                               + ''.join(f' (node (ref "{r}") (pin "{q}"))' for r, q in rp) + ')')
    open(p, 'w').write(
        '(export (version "E") (design (source "pwr.kicad_sch")) (components'
        + comp('BT1', 'cell', 'cell') + comp('F1', '1A', 'Fuse') + comp('U1', 'BUCK1', 'buck')
        + comp('L1', '2.2u', 'L') + comp('R1', '402k', 'R') + comp('R2', '174k', 'R')
        + comp('U3', 'TPS25947', 'efuse') + comp('R4', '549', 'R') + comp('U2', 'MCU', 'load')
        + comp('J1', 'USB', 'conn') + comp('R5', '0', 'R') + comp('D1', 'BAT54', 'D_Schottky')
        + comp('U4', 'LSW', 'lsw') + comp('D2', 'RED', 'LED') + comp('R6', '1k', 'R') + ')'
        ' (libparts (libpart (lib "x") (part "cell")' + pins('+', '-') + ')'
        ' (libpart (lib "x") (part "D_Schottky")' + pins('K', 'A') + ') (libpart (lib "x") (part "LED")' + pins('K', 'A') + ')'
        ' (libpart (lib "x") (part "lsw") (pins (pin (num "1") (name "IN") (type "power_in"))'
        ' (pin (num "2") (name "OUT") (type "power_out")) (pin (num "3") (name "ST") (type "open_collector"))'
        ' (pin (num "4") (name "GND") (type "power_in"))))'
        ' (libpart (lib "x") (part "Fuse")' + pins('1', '2') + ')'
        ' (libpart (lib "x") (part "buck")' + pins('VIN', 'SW', 'FB', 'GND') + ')'
        ' (libpart (lib "x") (part "L")' + pins('1', '2') + ') (libpart (lib "x") (part "R")' + pins('1', '2') + ')'
        ' (libpart (lib "x") (part "efuse")' + pins('IN', 'OUT', 'ILM', 'GND') + ')'
        ' (libpart (lib "x") (part "load")' + pins('VCC') + ') (libpart (lib "x") (part "conn")' + pins('VBUS') + '))'
        ' (nets' + net(1, 'N_BT', ('BT1', '1'), ('F1', '1'))
        + net(2, 'GND', ('BT1', '2'), ('U1', '4'), ('R2', '2'), ('R4', '2'), ('U3', '4'), ('U4', '4'))
        + net(3, 'VSYS', ('F1', '2'), ('U1', '1'), ('R5', '2'), cls='PWR_HIGH')
        + net(4, 'Net-(U1-SW)', ('U1', '2'), ('L1', '1')) + net(5, 'Net-(U1-FB)', ('U1', '3'), ('R1', '2'), ('R2', '1'))
        + net(6, '+3V3', ('L1', '2'), ('R1', '1'), ('U3', '1'), ('D1', '2'), ('D2', '2'))
        + net(7, 'Net-(U3-ILM)', ('U3', '3'), ('R4', '1'))
        + net(8, '3V3_OUT', ('U3', '2'), ('U2', '1')) + net(9, 'VBUS', ('J1', '1'), ('R5', '1'))
        + net(10, 'Net-(D1-K)', ('D1', '1'), ('U4', '1')) + net(11, '+3V3_EXT', ('U4', '2'))
        + net(12, 'Net-(D2-K)', ('D2', '1'), ('R6', '1')) + net(13, 'Net-(U4-ST)', ('U4', '3'), ('R6', '2')) + '))')
    return p


def i2c_net(d):
    """U1 (an MCU, IO1/IO2) with two TCAL9539: U2 A0 via R1 10k to +3V3, A1 GND (0x75);
    U3 A0 straight to +3V3, A1 GND (0x75 again: a duplicate). R3 pulls SDA up; J1's
    SDA_RAW hangs off it through R4 33 ohm (one bus, not a second)."""
    os.makedirs(os.path.join(d, 'i2c'))
    p = os.path.join(d, 'i2c', 'i2c.net')
    pins = lambda *pn: ' (pins' + ''.join(f' (pin (num "{i + 1}") (name "{m}") (type "passive"))'
                                          for i, m in enumerate(pn)) + ')'
    comp = lambda r, v, part: f' (comp (ref "{r}") (value "{v}") (libsource (lib "x") (part "{part}")))'
    net = lambda c, name, *rp: (f' (net (code "{c}") (name "{name}")'
                                + ''.join(f' (node (ref "{r}") (pin "{q}"))' for r, q in rp) + ')')
    open(p, 'w').write(
        '(export (version "E") (design (source "i2c.kicad_sch")) (components'
        + comp('U1', 'MCU', 'mcu') + comp('U2', 'TCAL9539', 'io') + comp('U3', 'TCAL9539', 'io')
        + comp('R1', '10k', 'R') + comp('R3', '2.2k', 'R') + comp('R4', '33', 'R') + comp('J1', 'I2C', 'R') + ')'
        ' (libparts (libpart (lib "x") (part "mcu")' + pins('IO1', 'IO2') + ')'
        ' (libpart (lib "x") (part "io")' + pins('SDA', 'SCL', 'A0', 'A1') + ')'
        ' (libpart (lib "x") (part "R")' + pins('1', '2') + '))'
        ' (nets' + net(1, 'SDA', ('U1', '1'), ('U2', '1'), ('U3', '1'), ('R3', '1'), ('R4', '1'))
        + net(2, 'SCL', ('U1', '2'), ('U2', '2'), ('U3', '2'))
        + net(3, '+3V3', ('R1', '2'), ('U3', '3'), ('R3', '2')) + net(4, 'Net-(U2-A0)', ('U2', '3'), ('R1', '1'))
        + net(5, 'GND', ('U2', '4'), ('U3', '4')) + net(6, 'SDA_RAW', ('R4', '2'), ('J1', '1')) + '))')
    return p


def fet_pinout_project(d):
    """Q1 (Q_NMOS_DGS) on a footprint that numbers its pads by function like KiCad's
    VSONP-8: pad 1 three pins (S), pad 2 the gate, pad 3 four pins + EP (D)"""
    os.makedirs(os.path.join(d, 't.pretty'))
    open(os.path.join(d, 'fp-lib-table'), 'w').write(
        '(fp_lib_table (lib (name "t") (type "KiCad") (uri "${KIPRJMOD}/t.pretty")))')
    open(os.path.join(d, 't.pretty', 'SON.kicad_mod'), 'w').write(
        '(footprint "SON" ' + ' '.join(f'(pad "{n}" smd rect (at 0 0) (size 1 1) (layers "F.Cu"))'
                                       for n in '111233333') + ')')
    p = os.path.join(d, 'q.net')
    open(p, 'w').write(
        '(export (version "E") (design (source "q.kicad_sch"))'
        ' (components (comp (ref "Q1") (value "CSD18512Q5B") (footprint "t:SON")'
        ' (libsource (lib "Transistor_FET") (part "Q_NMOS_DGS"))))'
        ' (libparts (libpart (lib "Transistor_FET") (part "Q_NMOS_DGS") (pins (pin (num "1") (name "D") (type "passive"))'
        ' (pin (num "2") (name "G") (type "input")) (pin (num "3") (name "S") (type "passive")))))'
        ' (nets (net (code "1") (name "/D") (node (ref "Q1") (pin "1")))'
        ' (net (code "2") (name "/G") (node (ref "Q1") (pin "2")))'
        ' (net (code "3") (name "/S") (node (ref "Q1") (pin "3")))))')
    return p


def suite(tmp, mini):
    """Append this file's cases to CASES, yield while the runner runs them, then do the
    ad-hoc checks (the full run only: -k stops at the yield)."""
    T = lambda n: os.path.join(tmp.name, n)             # noqa: E731
    # 5 warn: /DATA's third part C2 is a shunt to GND, not a stub (RFSTUB is
    # exercised by rf.net in mini_project instead)
    CASES.append(("knet check",   ['knet.py', NET, 'check'],                 2, ["4 error, 5 warn, 2 info"]))
    CASES.append(("knet divider", ['knet.py', NET, 'divider', '/VSENSE'],    0, ["1.6667 V", "1.6445 - 1.6890 V"]))
    CASES.append(("knet unconnected", ['knet.py', NET, 'unconnected'], 0,
                  ["=== symbol pins present in the schematic but on no net ===", "DualBattFET"]))
    CASES.append(("knet walk",    ['knet.py', NET, 'walk', '/DANGLE'],       0, ["R2.2", "DNP"]))
    CASES.append(("knet usage",   ['knet.py', NET, 'path', 'U1'],            1, ["usage: knet.py FILE path R13 U2"]))   # was an IndexError
    # -h before the required positionals: was "the following arguments are required"
    CASES.append(("knet help",    ['knet.py', '--help'],                     0, ["knet.py v3"]))
    CASES.append(("knet no cmd",  ['knet.py', NET],                          2, ["no command given", "knet.py FILE summary"]))  # was the flags' usage block
    CASES.append(("knet summary next", ['knet.py', NET, 'summary'],          0, ["R      4  next R5    R1-R4"]))
    CASES.append(("knet draw",    ['knet.py', NET, 'draw', 'U1', '-d', '2', '-o', svg1], 0, []))
    CASES.append(("knet repeated sheet", ['knet.py', REPEAT, 'around', 'R2'], 0, ["sheet /B/  at (100,100)mm"]))
    CASES.append(("knet sheets",  ['knet.py', REPEAT, 'sheets'],             0, ["/A/  (1)", "/B/  (1)\n  R2     10k"]))
    CASES.append(("knet notes",   ['knet.py', REPEAT, 'notes'],              0,
                  ["=== /", "(50,30)  [1 mm  SMALL]  A and B are one sub.kicad_sch", "notes under 1.27 mm text"]))
    CASES.append(("knet comp",    ['knet.py', NET, 'comp', 'U1'],            0,
                  ["=== U1  MCU3V3 ===", "supply    : +3V3 (3.3 V)", "4     TX               output       4      /DATA"]))
    CASES.append(("knet net",     ['knet.py', NET, 'net', '/VSENSE'],        0, ["=== /VSENSE   [Default]  2 nodes", "R4     pin 1"]))
    CASES.append(("knet pin",     ['knet.py', NET, 'pin', 'U1.1'],           0, ["U1.1 [VDD] -> +3V3  (3 nodes)", "FB1    pin 2"]))
    CASES.append(("knet find",    ['knet.py', NET, 'find', 'VSENSE|R4'],     0,
                  ["components:\n  R4     5k 1%", "nets:\n  /VSENSE                            2 nodes"]))
    CASES.append(("knet revpol", ['knet.py', mini, 'revpol'], 0,
                  ["D2    SMF10A", "NO FUSE in this loop", "U2.1    IN           -4.2 V below its GND, via 10ohm (R1)"]))
    CASES.append(("knet pinout", ['knet.py', mini, 'check', '--only', 'PINOUT'], 2,
                  ["D1 BAV199 on Device:D_Dual_Series_ACK", "use Device:D_Dual_Series_AKC"]))
    CASES.append(("knet fppad+parpin", ['knet.py', mini, 'check', '--only', 'FPPAD,PARPIN'], 2,
                  ["U3.4 (VIN) has no pad of its own in QFN: fused into pad 3 (VIN)",
                   "U3 pad 5 (smd) of QFN has no symbol pin", "U3.6 (X) is on NX but t:QFN has no pad 6", '!pad MP']))
    CASES.append(("knet rfstub",['knet.py', os.path.join(tmp.name, 'rf.net'), 'check', '--only', 'RFSTUB'], 0,
                  ["ANT [RF_50OHM] has 3 populated parts on it (J1, R1, U1)", "3 warn",
                   "RFA [RF_50OHM]: DNP JP1 bridges it to RF net RFB", "RFB [RF_50OHM]: DNP JP1 bridges it to RF net RFA"]))
    # /Root/CS has one node, /Root/Sub/CS the rest: a local label on parent and child
    sp = os.path.join(tmp.name, 'split.net')
    open(sp, 'w').write(
        '(export (version "E") (design (source "s.kicad_sch")) (components'
        ' (comp (ref "U1") (value "X") (libsource (lib "x") (part "y")))'
        ' (comp (ref "J1") (value "C") (libsource (lib "x") (part "y")))) (libparts)'
        ' (nets (net (code "1") (name "/Root/CS") (node (ref "U1") (pin "1")))'
        ' (net (code "2") (name "/Root/Sub/CS") (node (ref "J1") (pin "1")) (node (ref "U1") (pin "2")))))')
    # diff: FILE is NEW; unix-order misuse (OLD exported later) gets a note
    for nm, dt, refs in (('d0', '2026-01-01T00:00:00', 'R1 R2'), ('d1', '2026-01-02T00:00:00', 'R1')):
        open(os.path.join(tmp.name, nm + '.net'), 'w').write(
            f'(export (version "E") (design (source "s.kicad_sch") (date "{dt}")) (components'
            + ''.join(f' (comp (ref "{r}") (value "1k") (libsource (lib "x") (part "R")))' for r in refs.split())
            + ') (libparts) (nets))')
    CASES.append(("knet diff order note", ['knet.py', os.path.join(tmp.name, 'd0.net'), 'diff',
                                           os.path.join(tmp.name, 'd1.net')], 0,
                  ["was exported after the NEW side", "=== components added (1) ===", "R2 [1k]"]))
    CASES.append(("knet solo split label", ['knet.py', sp, 'check', '--only', 'SOLO'], 2,
                  ["net /Root/CS has only U1.1 on it; /Root/Sub/CS (J1.1, U1.2) has the same name on another sheet"]))
    CASES.append(("knet i2c", ['knet.py', i2c_net(tmp.name), 'i2c'], 2,
                  ["=== SDA + SDA_RAW  /  SCL", "pull-ups : R3 2.2k (SDA) to +3V3", "connectors: J1",
                   "target   : U2    TCAL9539             0x75        A0: R1 10k to +3V3; A1: GND",
                   "controller: U1 MCU (IO1)", "ERROR address 0x75 used by U2 U3"]))
    CASES.append(("knet powertree", ['knet.py', power_net(tmp.name), 'powertree'], 0,
                  ["cells BT1: N_BT", "-> F1 1A -> VSYS  (also fed from VBUS via R5)",
                   "-> U1 BUCK1  [FB 402k/174k: Vout = 3.310 V] -> L1 2.2u -> +3V3  3.3 V",
                   "-> U3 TPS25947  [ILIM 5.40/6.07/6.60 A (R4 549)] -> 3V3_OUT  3.3 V  loads U2",
                   "J1 VBUS: VBUS  5 V", "-> D1 BAT54  [-Vf ~0.3-0.5 V] -> U4 LSW -> +3V3_EXT  3.3 V"]))
    CASES.append(("knet ocnopull R then LED", ['knet.py', os.path.join(tmp.name, 'pwr', 'pwr.net'), 'check',
                                               '--only', 'OCNOPULL'], 0, ["0 error, 0 warn"]))
    CASES.append(("knet rails powertree", ['knet.py', os.path.join(tmp.name, 'pwr', 'pwr.net'), 'rails'], 0,
                  ["=== VSYS   ? V", "source : F1 [1A] from N_BT  (powertree)"]))
    fet = os.path.join(tmp.name, 'fet.net')
    CASES.append(("knet revpol fet", ['knet.py', fet, 'revpol'], 0,
                  ["FET channel(s) on, gate driven from the cells: Q1", "FET channels vs normal: Q1 off",
                   "isolated from the cells: U1", "bidirectional TVS/ESD, breakdown not in the part number: D1"]))
    bomcsv = os.path.join(tmp.name, 'bom.csv')            # Designator (not Reference), a range, a space list
    with open(bomcsv, 'w') as fh:
        fh.write('"Designator","Qty","MPN","LCSC Part","DNP"\n"R1,R3-R4","3","","",""\n"C1 C2","2","","C1525",""\n'
                 '"R9","1","","",""\n"R2","1","","",""\n')
    CASES.append(("knet bom csv", ['knet.py', NET, 'bom', '--csv', bomcsv], 2,
                  ["7 refs; compared MPN, LCSC, DNP", "in the CSV only, not in the netlist's BOM (1): R9",
                   "in the netlist only, populated (5): FB1 J1 U1-U3", "C1      LCSC  CSV C1525", "R2      DNP   CSV -",
                   "3 ref(s) agree"]))
    CASES.append(("kfront draw powertree", ['kfront.py', os.path.join(tmp.name, 'pwr', 'pwr.net'), 'draw', 'powertree',
                                            '-o', T('pt.kicad_sch')], 0, ["kfront draw powertree: ", "graphic item(s)"]))
    CASES.append(("kfront draw i2c", ['kfront.py', os.path.join(tmp.name, 'i2c', 'i2c.net'), 'draw', 'i2c',
                                      '-o', T('i2c.kicad_sch')], 0, ["kfront draw i2c: "]))
    CASES.append(("knet draw also-line", ['knet.py', also_net(tmp.name), 'draw', 'U1', '--spec'], 0,
                  ['note 6.4,0.6 IRQ\nnote 6.4,0.05 "+ U2 U3"']))
    CASES.append(("knet draw xref", ['knet.py', xref_net(tmp.name), 'draw', 'U1', '--spec'], 0,
                  ['note -12.69,4.18 "to U1.3"\nwire R1.2 -10.5,4',
                   'note -11.54,10.18 "to R1.2 R2.1 (drawn above)"\nwire U1.3 -4.5,10']))
    mn = multi_net(tmp.name)
    CASES.append(("knet draw multi-pin spec", ['knet.py', mn, 'draw', 'U1', '--spec'], 0,
                  ["d2s D1 ", "rsense R1 ", "label MID D1.3", "gnd R1.4", "wire U1.3 D2.1"]))
    CASES.append(("knet draw multi-pin verify", ['knet.py', mn, 'draw', 'U1', '-o', os.path.join(TMP, 'selftest_multi.svg')],
                  0, ["wrote", '!ERROR', '!overlaps']))
    CASES.append(("knet pinout power-FET", ['knet.py', fet_pinout_project(os.path.join(tmp.name, 'qfet')),
                                            'check', '--only', 'PINOUT'], 2,
                  ["Q1 CSD18512Q5B on Transistor_FET:Q_NMOS_DGS: SON numbers its pads by function",
                   "pins 1-3 must be SGD; as drawn they are DGS and the FET mounts with D and S swapped",
                   "use Transistor_FET:Q_NMOS_SGD"]))
    CASES.append(("knet nc-stub+stale", ['knet.py', mini, 'around', 'U1'], 0,
                  ["NC (flagged)", "floating  <-- no NC flag", "1.0 h older than t.kicad_sch",
                   "lacks top-level sheet(s) Other"]))
    yield
    import kverify                # the checks below call them in-process
    rc2 = open(os.path.join(tmp.name, 'silkart', 'rc2.kicad_pcb')).read() if os.path.exists(
        os.path.join(tmp.name, 'silkart', 'rc2.kicad_pcb')) else ''
    check('(render_cache "RC"' in rc2 and '(xy 6 16.5) (xy 8 16.5)' in rc2.replace('\n\t\t\t\t\t', ' ')
                   or '(xy 6 16.5)' in rc2 and '(xy 8 18)' in rc2,
                   "edit text keep: a TrueType text's render_cache moves with it (5..7 -> 6..8), not dropped")
    t4 = open(os.path.join(tmp.name, 'silkrev', 't4.kicad_pcb')).read()
    check('(property "Value" "VR1"\n\t\t\t(at 0 2 0)' in t4 and t4.count('(hide yes)') == 1,
                   "edit value: R1's Value at local 0,2 (board 5,7), R2's hidden, nothing else")
    # a sheet saved after the .net triggers kmerge; one that fails keeps the old
    # netlist and says so, next to the stale warning
    code, out = run(['knet.py', mini, 'summary'], {'KREVIEW_NO_REGEN': '', 'KICAD_CLI': 'false'})
    ok5 = 'auto-regenerate of t.net failed' in out and '1.0 h older than t.kicad_sch' in out
    check(ok5, "stale netlist auto-regenerate (failure path)")
    va = '(sheet_instances (path "/" (page "4"))) (at 10 20) (xy 1 2) (start 0 0)'
    vb = '(sheet_instances (path "/" (page "6"))) (at 7.46 20) (xy -1.54 2) (start -2.54 0)'
    vs = kverify.delta_summary(va, vb)
    ok19 = vs == 'page 4 -> 6; 3 coordinates moved, all by (-2.54,+0)' \
        and kverify.delta_summary(va, va.replace('(at', '(foo (at')).startswith('structure changed')
    check(ok19, f"kverify sheet delta: {vs}")
