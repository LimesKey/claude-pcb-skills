"""Self-test cases: kfp.py (footprints), kdoc.py (datasheets), kdrc.py (kicad-cli DRC).

selftest.py runs suite(); see its docstring for the case format."""
import os
from st_common import PCB, CASES, _tab_board, check, run, sym


def symlib(*syms):
    return '(kicad_symbol_lib\n\t(version 20251024)\n\t(generator "t")\n' + ''.join(s + '\n' for s in syms) + ')\n'


def placed(lib_id, uuid, ref, fp=None, lib_name=None):
    return ('\t(symbol\n' + (f'\t\t(lib_name "{lib_name}")\n' if lib_name else '') + f'\t\t(lib_id "{lib_id}")\n'
            f'\t\t(uuid "{uuid}")\n\t\t(property "Reference" "{ref}"\n\t\t)\n'
            + (f'\t\t(property "Footprint" {fp}\n\t\t)\n' if fp else '') + '\t)\n')


def vendor_proj(d):
    """a project whose board takes ext:R from a library outside it, with a 3D model there too,
    and a schematic naming ext:R in a placed symbol and in its lib_symbols cache. Symbols: Q1
    and Q2 (KiCad's lib_name variant Q_1) from extsym outside the repo, U1 from the project's
    ps with an MPN field added in the schematic (erc.json: ERC's lib_symbol_mismatch on it).
    Subsheet sub/s.kicad_sch (R2 on ext:R) is in the hierarchy; orig/v.kicad_sch, a backup
    copy, is not and must stay untouched"""
    pj, ext = os.path.join(d, 'vend'), os.path.join(d, 'vend_ext')
    for x in (pj, os.path.join(pj, 'lib', 'p.pretty'), os.path.join(ext, 'ext.pretty'), os.path.join(pj, 'sub'),
              os.path.join(pj, 'orig')):
        os.makedirs(x, exist_ok=True)
    mod = ('(footprint "R"\n\t(version 20240108)\n\t(generator "pcbnew")\n\t(layer "F.Cu")\n'
           '\t(property "Reference" "REF**"\n\t\t(at 0 -1.5 0)\n\t\t(layer "F.SilkS")\n\t)\n'
           '\t(attr smd)\n\t(pad "1" smd rect\n\t\t(at -0.5 0)\n\t\t(size 0.5 0.5)\n\t\t(layers "F.Cu")\n\t)\n'
           '\t(pad "2" smd rect\n\t\t(at 0.5 0)\n\t\t(size 0.5 0.5)\n\t\t(layers "F.Cu")\n\t)\n'
           f'\t(model "{ext}/R.step"\n\t\t(offset\n\t\t\t(xyz 0 0 0)\n\t\t)\n\t)\n)\n')
    for path, txt in ((os.path.join(ext, 'ext.pretty', 'R.kicad_mod'), mod), (os.path.join(ext, 'R.step'), 'step\n'),
                      (os.path.join(pj, 'v.kicad_pro'), '{}'),
                      (os.path.join(pj, 'fp-lib-table'), '(fp_lib_table\n\t(version 7)\n'
                       f'\t(lib (name "p") (type "KiCad") (uri "${{KIPRJMOD}}/lib/p.pretty") (options "") (descr ""))\n'
                       f'\t(lib (name "ext") (type "KiCad") (uri "{ext}/ext.pretty") (options "") (descr ""))\n)\n'),
                      (os.path.join(pj, 'sym-lib-table'), '(sym_lib_table\n\t(version 7)\n'
                       '\t(lib (name "ps") (type "KiCad") (uri "${KIPRJMOD}/lib/ps.kicad_sym") (options "") (descr ""))\n'
                       f'\t(lib (name "extsym") (type "KiCad") (uri "{ext}/extsym.kicad_sym") (options "") (descr ""))\n)\n'),
                      (os.path.join(pj, 'lib', 'ps.kicad_sym'), symlib(sym('S', 1))),
                      (os.path.join(ext, 'extsym.kicad_sym'), symlib(sym('Q', 1, '"ext:R"'))),
                      (os.path.join(pj, 'erc.json'), '{"sheets": [{"violations": [{"type": "lib_symbol_mismatch", '
                       '"items": [{"description": "Symbol U1 [S]", "uuid": "u1"}]}]}]}'),
                      (os.path.join(pj, 'erc0.json'), '{"sheets": []}'),
                      (os.path.join(pj, 'v.kicad_sch'), '(kicad_sch\n\t(version 20250114)\n\t(lib_symbols\n'
                       '\t\t(symbol "Device:R"\n\t\t\t(property "Footprint" "ext:R"\n\t\t\t)\n\t\t)\n'
                       + sym('Q', 2, '"ext:R"', 'extsym:Q', 'Q1') + '\n' + sym('Q_1', 2, '"ext:R"', ref='Q2', extra='Rev')
                       + '\n' + sym('S', 2, name='ps:S', ref='U1', extra='MPN') + '\n\t)\n'
                       + placed('Device:R', 'r1', 'R1', '"ext:R"') + placed('extsym:Q', 'q1', 'Q1', '"ext:R"')
                       + placed('extsym:Q', 'q2', 'Q2', lib_name='Q_1') + placed('ps:S', 'u1', 'U1')
                       + '\t(sheet\n\t\t(uuid "sh1")\n\t\t(property "Sheetname" "sub"\n\t\t)\n'
                       '\t\t(property "Sheetfile" "sub/s.kicad_sch"\n\t\t)\n\t)\n)\n'),
                      (os.path.join(pj, 'sub', 's.kicad_sch'), '(kicad_sch\n\t(version 20250114)\n'
                       + placed('Device:R', 'r2', 'R2', '"ext:R"') + ')\n')):
        with open(path, 'w') as fh:
            fh.write(txt)
    with open(os.path.join(pj, 'orig', 'v.kicad_sch'), 'w') as fh:       # a backup copy, outside the hierarchy
        fh.write(open(os.path.join(pj, 'v.kicad_sch')).read())
    body = mod.replace('(footprint "R"', '(footprint "ext:R"').replace('"REF**"', '"R1"').replace(
        '\t(layer "F.Cu")\n', '\t(layer "F.Cu")\n\t(at 10 5)\n', 1)
    body = ''.join('\t' + ln + '\n' for ln in body.rstrip('\n').split('\n'))
    with open(os.path.join(ext, 'D.step'), 'w') as fh:       # kfp vendor D1 --model: the one stock never shipped
        fh.write('step\n')
    _tab_board(pj, 'v.kicad_pcb', 20, 10, body + '\t(footprint "Gone:D"\n\t\t(layer "F.Cu")\n\t\t(at 4 5)\n'
               '\t\t(property "Reference" "D1"\n\t\t\t(at 0 -1.5 0)\n\t\t\t(layer "F.SilkS")\n\t\t)\n'
               '\t\t(pad "1" smd rect\n\t\t\t(at 0 0)\n\t\t\t(size 0.5 0.5)\n\t\t\t(layers "F.Cu")\n\t\t)\n'
               '\t\t(model "${KICAD10_3DMODEL_DIR}/Diode.3dshapes/D.step"\n\t\t)\n\t)\n')
    return pj


def kfp_project(d):
    """kfp: t.pretty with GOOD (clean 0402-like), BAD (no courtyard or Fab, silk across pad 1,
    origin 0.5 mm off the pads) and EP (exposed pad 5 with no paste, thermal via numbered 6);
    t.kicad_pcb holds GOOD as R1 (rot 90, top), R2 (rot 90, back: y mirrored, layers swapped)
    and R3 (top, pad 1 resized on the board)"""
    d = os.path.join(d, 'kfp')
    os.makedirs(os.path.join(d, 't.pretty'), exist_ok=True)
    open(os.path.join(d, 't.kicad_pro'), 'w').write('{}')
    open(os.path.join(d, 'fp-lib-table'), 'w').write(
        '(fp_lib_table (lib (name "t") (type "KiCad") (uri "${KIPRJMOD}/t.pretty")))')
    st = lambda w: f'(stroke (width {w}) (type solid))'               # noqa: E731
    head = lambda n: (f'(footprint "{n}" (version 20241229) (generator "pcbnew") (generator_version "9.0") (layer "F.Cu")\n'
                      f'  (property "Reference" "REF**" (at 0 -1.2 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))\n'
                      f'  (property "Value" "{n}" (at 0 1.2 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))\n'
                      '  (attr smd)\n')                              # noqa: E731
    pad = lambda n, x, y, sx, sy, lay='"F.Cu" "F.Mask" "F.Paste"', k='smd', sh='roundrect': (   # noqa: E731
        f'  (pad "{n}" {k} {sh} (at {x} {y}) (size {sx} {sy})' + (' (drill 0.3)' if k == 'thru_hole' else '')
        + f' (layers {lay})' + (' (roundrect_rratio 0.25)' if sh == 'roundrect' else '') + ')\n')
    good = (head('GOOD') + f'  (fp_rect (start -0.5 -0.25) (end 0.5 0.25) {st(0.1)} (fill no) (layer "F.Fab"))\n'
            f'  (fp_rect (start -0.91 -0.46) (end 0.91 0.46) {st(0.05)} (fill no) (layer "F.CrtYd"))\n'
            f'  (fp_line (start -0.2 -0.6) (end 0.2 -0.6) {st(0.12)} (layer "F.SilkS"))\n'
            '  (fp_text user "${REFERENCE}" (at 0 0 0) (layer "F.Fab") (effects (font (size 0.25 0.25) (thickness 0.04))))\n'
            + pad(1, -0.48, 0, 0.56, 0.62) + pad(2, 0.48, 0, 0.56, 0.62) + ')\n')
    bad = (head('BAD') + f'  (fp_line (start 0 -1) (end 0 1) {st(0.12)} (layer "F.SilkS"))\n'
           + pad(1, 0, 0, 0.5, 0.5) + pad(2, 1, 0, 0.5, 0.5) + ')\n')
    ep = (head('EP') + f'  (fp_rect (start -1.5 -1.5) (end 1.5 1.5) {st(0.1)} (fill no) (layer "F.Fab"))\n'
          f'  (fp_rect (start -2 -2) (end 2 2) {st(0.05)} (fill no) (layer "F.CrtYd"))\n'
          + ''.join(pad(n, x, y, 0.3, 0.3) for n, x, y in ((1, -1.3, -1.3), (2, 1.3, -1.3), (3, 1.3, 1.3), (4, -1.3, 1.3)))
          + pad(5, 0, 0, 1.6, 1.6, '"F.Cu" "F.Mask"', sh='rect') + pad(6, 0, 0, 0.5, 0.5, '"*.Cu"', 'thru_hole', 'circle')
          + ')\n')
    fet = (head('FET') + f'  (fp_rect (start -1 -1) (end 1 1) {st(0.1)} (fill no) (layer "F.Fab"))\n'
           f'  (fp_rect (start -1.3 -1.3) (end 1.3 1.3) {st(0.05)} (fill no) (layer "F.CrtYd"))\n'
           + pad(1, -0.5, 0.6, 0.4, 0.6, sh='rect') + pad(2, 0, 0, 1.6, 1.2, sh='rect') + ')\n')   # drain into the tab
    for n, t in (('GOOD', good), ('BAD', bad), ('EP', ep), ('FET', fet)):
        open(os.path.join(d, 't.pretty', n + '.kicad_mod'), 'w').write(t)

    def inst(ref, x, y, rot, back, p1='0.56 0.62'):
        m = (lambda v: -v) if back else (lambda v: v)                 # noqa: E731
        L = (lambda s: s.replace('F.', 'B.')) if back else (lambda s: s)   # noqa: E731
        return (f'\t(footprint "t:GOOD"\n\t\t(layer "{L("F.Cu")}")\n\t\t(uuid "{ref}-u")\n'
                f'\t\t(transform (translate {x} {y}) (rotate {rot}) (scale 1 1))\n'
                f'\t\t(property "Reference" "{ref}" (at 0 {m(-1.2)} {rot}) (layer "{L("F.SilkS")}"))\n'
                f'\t\t(attr smd)\n'
                f'\t\t(fp_rect (start -0.5 {m(-0.25)}) (end 0.5 {m(0.25)}) {st(0.1)} (fill no) (layer "{L("F.Fab")}"))\n'
                f'\t\t(fp_rect (start -0.91 {m(-0.46)}) (end 0.91 {m(0.46)}) {st(0.05)} (fill no) (layer "{L("F.CrtYd")}"))\n'
                f'\t\t(fp_line (start -0.2 {m(-0.6)}) (end 0.2 {m(-0.6)}) {st(0.12)} (layer "{L("F.SilkS")}"))\n'
                f'\t\t(fp_text user "${{REFERENCE}}" (at 0 0 {rot}) (layer "{L("F.Fab")}"))\n'
                f'\t\t(pad "1" smd roundrect (at -0.48 0 {rot}) (size {p1}) (layers {L(chr(34) + "F.Cu" + chr(34))} '
                f'"{L("F.Mask")}" "{L("F.Paste")}") (roundrect_rratio 0.25) (net "A") (uuid "{ref}-1"))\n'
                f'\t\t(pad "2" smd roundrect (at 0.48 0 {rot}) (size 0.56 0.62) (layers "{L("F.Cu")}" "{L("F.Mask")}" '
                f'"{L("F.Paste")}") (roundrect_rratio 0.25) (net "B") (uuid "{ref}-2"))\n\t)\n')
    open(os.path.join(d, 't.kicad_pcb'), 'w').write(
        '(kicad_pcb\n\t(version 20260901)\n\t(generator "pcbnew")\n\t(generator_version "10.99")\n'
        '\t(layers\n\t\t(0 "F.Cu" signal)\n\t\t(2 "B.Cu" signal)\n\t)\n'
        + inst('R1', 10, 10, 90, False) + inst('R2', 20, 10, 90, True) + inst('R3', 30, 10, 0, False, '0.6 0.6') + ')\n')
    return d


def kdoc_docs(d):
    """kdoc's inputs, no poppler needed: an uploader page container named .pdf (3 pages, an image
    for p1; a phrase broken across lines, 'keepout' and TI's U+2212 minus) and a csv. A third
    doc is indexed into the cache (KDOC_CACHE, set by main) and its source deleted, for prune"""
    import zipfile
    d = os.path.join(d, 'kdoc')
    os.makedirs(d, exist_ok=True)
    zp, cp, gone = (os.path.join(d, n) for n in ('LM1234-Q1.pdf', 'pinout.csv', 'gone.csv'))
    with zipfile.ZipFile(zp, 'w') as z:
        z.writestr('manifest.json', '{"pages": 3}')
        z.writestr('1.txt', 'LM1234 Buck Regulator\nThe device has a soft\nstart of 2 ms and an\nenable pin EN.\n')
        z.writestr('2.txt', '7.3 Feature Description\nThe keepout zone under the\ninductor; range −40 C to 125 C.\n')
        z.writestr('3.txt', '8 Layout\nPlace the input capacitor next to VIN and GND.\n')
        z.writestr('1.jpeg', b'\xff\xd8\xff')
    open(cp, 'w').write('pin,name\n1,VIN\n2,GND\n3,EN\n')
    open(gone, 'w').write('x\n')
    run(['kdoc.py', 'index', gone])
    os.remove(gone)
    return zp, cp


def kdoc_pdf(d):
    """a real two-page PDF, written by hand (stdlib): p1 text in Helvetica, p2 no text layer (as
    a scan reads), for `_pdf`'s one pdftotext call, form-feed page split and `.scan` tag"""
    objs = ['<< /Type /Catalog /Pages 2 0 R >>', None, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    kids = []
    for lines in (['TPS9999 Boost Converter', 'The switch current limit is 2.5 A.'], []):
        st = ('BT /F1 12 Tf 72 720 Td 14 TL ' + ' '.join(f'({t}) Tj T*' for t in lines) + ' ET') if lines else ''
        objs.append(f'<< /Length {len(st)} >>\nstream\n{st}\nendstream')
        objs.append('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >>'
                    f' /Contents {len(objs)} 0 R >>')
        kids.append(f'{len(objs)} 0 R')
    objs[1] = f'<< /Type /Pages /Kids [{" ".join(kids)}] /Count {len(kids)} >>'
    out, offs = '%PDF-1.4\n', []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f'{i} 0 obj\n{o}\nendobj\n'
    x = len(out)
    out += (f'xref\n0 {len(objs) + 1}\n0000000000 65535 f \n' + ''.join(f'{o:010d} 00000 n \n' for o in offs)
            + f'trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n')
    p = os.path.join(d, 'kdocpdf', 'TPS9999.pdf')
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='latin-1').write(out)
    return p


def suite(tmp, mini):
    """Append this file's cases to CASES, yield while the runner runs them, then do the
    ad-hoc checks (the full run only: -k stops at the yield)."""
    T = lambda n: os.path.join(tmp.name, n)             # noqa: E731
    CASES.append(("kdoc usage",   ['kdoc.py', 'near', 'x'],                  1, ["usage: kdoc.py near 'bias-t' 'resistor'"]))
    CASES.append(("kdrc flags", ['kdrc.py', PCB, 'flags'], 0, ["no PWR_FLAG symbols in"]))
    CASES.append(("kdrc selftest", ['kdrc.py', '--selftest'],                0, [" passed"]))     # the count moves; its exit code gates it
    CASES.append(("kdrc scratch", ['kdrc.py', os.path.join(T('sc0'), 'writer.kicad_pcb'), 'scratch', T('scr')], 0,
                  ["board: writer.kicad_pcb", "WARN: no .kicad_pro beside the board"]))
    kd = kfp_project(tmp.name)
    KP = lambda n: os.path.join(kd, n)                    # noqa: E731
    CASES.append(("kfp lint", ['kfp.py', KP('t.pretty'), 'lint'], 2,
                  ["4 footprint(s): 3 error, 4 warn", "BAD: no courtyard", "BAD: silk over 1 pad(s): 1",
                   "BAD: origin 0.50 mm from the pad extent (no Fab outline) centre", "BAD: no body outline on F.Fab",
                   "EP: thermal via pad(s) 6 sit in pad 5 under other numbers", "EP: exposed pad 5 gets no paste", "FET: differently numbered pads overlap: 1+2"]))
    CASES.append(("kfp lint clean", ['kfp.py', KP('t.pretty/GOOD.kicad_mod'), 'lint'], 0,
                  ["1 footprint(s): 0 error, 0 warn, 1 info", "GOOD: no 3D model"]))
    CASES.append(("kfp show", ['kfp.py', 't:EP', 'show', '--proj', kd], 0,
                  ["pads      : 6 (5 smd, 1 thru_hole)", "body      : 3.000 x 3.000 mm", "courtyard : -2.00,-2.00 .. 2.00,2.00"]))
    CASES.append(("kfp libs", ['kfp.py', KP('t.kicad_pcb'), 'libs'], 0,
                  ["3 footprints, 1 distinct, from 1 libraries", "unused in t: BAD EP FET", "3 part(s) have none",
                   "no model          t:GOOD  (R1-R3)"]))
    CASES.append(("kfp edit", ['kfp.py', KP('t.pretty/BAD.kicad_mod'), 'edit', 'origin', 'pads', 'fab', 'pads', 'crtyd', 'klc',
                               '-o', KP('t.pretty/BAD2.kicad_mod')], 0,
                  ["origin: moved to the copper centre (everything shifted -0.500,-0.000)",
                   "crtyd: 0 item(s) -> rect -1,-0.5 .. 1,0.5 (2.00 x 1.00 mm, 0.25 mm default)", "- [ERROR] CRTYD", "- [WARN] ORIGIN", "- [WARN] FAB"]))
    CASES.append(("kfp edit result lints", ['kfp.py', KP('t.pretty/BAD2.kicad_mod'), 'lint'], 2,
                  ["silk over 1 pad(s)"]))
    CASES.append(("kfp diff: rotation + flip undone, a board-side pad edit found",
                  ['kfp.py', KP('t.kicad_pcb'), 'diff'], 0,
                  ["R3  t:GOOD  DIFFERS", "pad 1: size 0.56 0.62 -> 0.6 0.6", "1 differ as DRC counts it (R3)", "2 identical"]))
    CASES.append(("kfp board show", ['kfp.py', KP('t.kicad_pcb'), 'show', 'R2'], 0,
                  ["rot 90  back side (un-mirrored here)", "courtyard : -0.91,-0.46 .. 0.91,0.46"]))
    vp = vendor_proj(tmp.name)
    vend = ['kfp.py', os.path.join(vp, 'v.kicad_pcb'), 'vendor', '--erc', os.path.join(vp, 'erc.json')]
    CASES.append(("kfp vendor dry run", vend, 0,
                  ["vendor into p (lib/p.pretty), models into lib/3dmodels", "footprint ext:R -> p:R  (R1): library file",
                   "models: 1 file(s) from", "-> ${KIPRJMOD}/lib/3dmodels/R.step  (R1)", "schematic v.kicad_sch: 2 Footprint field(s)",
                   "schematic sub/s.kicad_sch: 1 Footprint field(s)",
                   "board: 1 footprint(s) re-pointed", "(dry run: --apply", "symbol extsym:Q -> ps:Q  (Q1): outside the repo",
                   "symbol extsym:Q -> ps:Q_1  (Q2): outside the repo",
                   "symbol ps:S  (U1): edited in the schematic; the schematic's copy replaces the library's",
                   "symbols: 3 written into ps (lib/ps.kicad_sym, 1 replacing its own copy), 3 instance(s) re-pointed in 1"]))
    CASES.append(("kfp vendor --apply", vend + ['--apply', '--force'], 0,
                  ["wrote 1 footprint(s), 1 symbol library, 1 model file(s), the board, 2 schematic(s)"]))
    CASES.append(("kfp vendor result", vend[:-1] + [os.path.join(vp, 'erc0.json')], 0,
                  ["nothing outside the repo: already self-contained"]))
    vend0 = vend[:-1] + [os.path.join(vp, 'erc0.json'), 'D1', '--model', os.path.join(tmp.name, 'vend_ext', 'D.step')]
    CASES.append(("kfp vendor named", vend0, 0,
                  ["footprint Gone:D -> p:D  (D1): D1's board copy", "model ${KICAD10_3DMODEL_DIR}/Diode.3dshapes/D.step -> "
                   "${KIPRJMOD}/lib/3dmodels/D.step (it was missing)", "models: 1 file(s)", "board: 1 footprint(s) re-pointed"]))
    CASES.append(("kfp vendor named --apply", vend0 + ['--apply', '--force'], 0, ["wrote 1 footprint(s)"]))
    CASES.append(("kfp vendor named result", ['kfp.py', os.path.join(vp, 'lib', 'p.pretty', 'D.kicad_mod'), 'show'], 0,
                  ["${KIPRJMOD}/lib/3dmodels/D.step"]))
    os.environ['KDOC_CACHE'] = T('kdoc-cache')        # never the user's ~/.cache/kdoc
    zp, cp = kdoc_docs(tmp.name)
    CASES.append(("kdoc index", ['kdoc.py', 'index', zp, cp], 0, ["   3 pages  img", "   1 pages  text"]))
    CASES.append(("kdoc grep", ['kdoc.py', 'grep', 'soft-start', '-d', zp], 0, ["LM1234_Q1:p1:l2", ">>soft start<<"]))
    CASES.append(("kdoc grep -p", ['kdoc.py', 'grep', '-40', '-p', '2-3', '-d', zp], 0,
                  [">>−40<<", "1 hits across 1 doc(s), 1 page(s)"]))
    CASES.append(("kdoc grep keepout", ['kdoc.py', 'grep', 'keep-out', '-d', zp], 0, ["LM1234_Q1:p2:l2  ...", ">>keepout<<"]))
    CASES.append(("kdoc grep none", ['kdoc.py', 'grep', 'nothinghere', '-d', zp], 1, ["no hits for 'nothinghere' in 1 doc(s)"]))
    CASES.append(("kdoc text range", ['kdoc.py', 'text', zp, '2-3'], 0, ["=== LM1234_Q1 p2", "=== LM1234_Q1 p3", "8 Layout"]))
    CASES.append(("kdoc page", ['kdoc.py', 'page', zp, 'p1'], 0, [os.path.join('LM1234_Q1', '1.jpeg')]))
    CASES.append(("kdoc near", ['kdoc.py', 'near', 'capacitor', 'GND', '-d', zp], 0, ["LM1234_Q1:p3", "1 page(s) contain both"]))
    CASES.append(("kdoc toc", ['kdoc.py', 'toc', '-d', zp], 0, ["  p2       7.3 Feature Description"]))
    CASES.append(("kdoc csv", ['kdoc.py', 'grep', 'EN', '-d', cp], 0, ["pinout_csv:p1:l4"]))
    CASES.append(("kdoc list", ['kdoc.py', 'list'], 0, ["gone_csv", "(source gone: `kdoc.py prune`)"]))
    CASES.append(("kdoc prune", ['kdoc.py', 'prune'], 0, ["removed gone_csv", "pruned 1 slot(s) whose source is gone"]))
    import shutil
    if shutil.which('pdftotext') and shutil.which('pdfinfo'):     # poppler: CI may lack it
        rp = kdoc_pdf(tmp.name)
        CASES.append(("kdoc index real pdf", ['kdoc.py', 'index', rp], 0, ["TPS9999", "2 pages  scan 1/2"]))
        CASES.append(("kdoc grep real pdf", ['kdoc.py', 'grep', 'current limit', '-d', rp], 0,
                      ["TPS9999:p1:l2", ">>current limit<<", "1 hits across 1 doc(s), 1 page(s)"]))
    else:
        print("skip  2 kdoc real-PDF case(s): poppler (pdftotext, pdfinfo) not installed")
    yield
    import argparse, contextlib, io, kcommon, kdoc, kfp_diff, kfp_vendor, kpcb_board                # the checks below call them in-process
    vl, vs = (open(os.path.join(vp, f)).read() for f in ('lib/ps.kicad_sym', 'v.kicad_sch'))
    check(all(x in vl for x in ('\t(symbol "Q"\n\t\t(property "Reference" "Q"', '(symbol "Q_0_1"', '\t(symbol "Q_1"\n',
                                          '(symbol "Q_1_0_1"', '(property "Footprint" "p:R"', '(property "MPN"'))
                   and vl.count('\t(symbol "S"') == 1 and 'ext:R' not in vl and 'lib_name' not in vs
                   and all(x in vs for x in ('(symbol "ps:Q"', '(symbol "ps:Q_1"', '(lib_id "ps:Q_1")', '(symbol "ps:S"'))
                   and vs.count('"p:R"') == 4 and '(lib_id "Device:R")' in vs
                   and '"ext:R"' in open(os.path.join(vp, 'orig', 'v.kicad_sch')).read(),
                   "kfp vendor symbols: cached copies in ps (Reference prefix, units named, footprint re-pointed in "
                   "library and cache), S replaced once, lib_id/lib_name re-pointed, Device:R untouched, orig/ backup untouched")
    kpcb_board.Board.warn_rules = lambda self: None              # fixtures have no project rules; the CLI case checks it
    fid = lambda pad: kfp_diff.canon(kcommon.parse_sexp(f'(footprint "F" (layer "F.Cu") {pad})'))   # noqa: E731
    lib = fid('(pad "" smd circle (at 0 0) (size 1 1) (layers "F.Cu") (property pad_prop_fiducial_glob))')
    check(not kfp_vendor._adds(lib, fid('(pad "" smd circle (at 0 0) (size 1 1) (layers "F.Cu"))'))
                   and kfp_vendor._adds(lib, fid('(pad "" smd circle (at 0 0) (size 1.2 1.2) (layers "F.Cu"))')),
                   "kfp vendor stock rank: a board pad that only lacks a stock field is stale, a resized one a local fix")
    ok3 = bool(kdoc.smart_re('keep-out').search('antenna keepout zone')
               and kdoc.smart_re('-40').search('−40 C')
               and not kdoc.smart_re(' EN').search('ENABLE')
               and kdoc._fkey('docs/datasheets/max17320.pdf') == kdoc._fkey('max17320'))
    check(ok3, "kdoc pattern folding + -d path")
    kdoc.CACHE = os.path.join(tmp.name, 'kdoc')
    for sub in 'ab':
        os.makedirs(os.path.join(tmp.name, 'kd' + sub))
        open(os.path.join(tmp.name, 'kd' + sub, 'X1.txt'), 'w').write(sub * 9)
    with contextlib.redirect_stderr(io.StringIO()):
        ka, kb = (kdoc.extract(os.path.join(tmp.name, 'kd' + sub, 'X1.txt')) for sub in 'ab')
    ok14 = ka != kb and kdoc.docs('X1.txt') == ['X1_txt'] and kb.endswith('X1_txt_kdb') \
        and kdoc._pageset('2,5-7,p9') == {2, 5, 6, 7, 9}
    # a replaced source with fewer pages drops the old slot's extra pages
    xa = os.path.join(tmp.name, 'kda', 'X1.txt')
    open(xa, 'w').write('x\n' * 450)
    os.utime(xa, (1, 1))
    with contextlib.redirect_stderr(io.StringIO()):
        n3 = len(kdoc.pages(kdoc.extract(xa)))
        open(xa, 'w').write('y\n')
        n1 = len(kdoc.pages(kdoc.extract(xa)))
    ok14 &= (n3, n1) == (3, 1)
    # prune drops only the slot whose source was deleted
    os.remove(os.path.join(tmp.name, 'kdb', 'X1.txt'))
    with contextlib.redirect_stdout(io.StringIO()):
        kdoc.c_prune(argparse.Namespace(doc=None))
    ok14 &= kdoc.docs() == ['X1_txt']
    ok14 &= kdoc._doc_and_page(argparse.Namespace(pages=None, doc=None, args=['X1', '5-7'])) == ('X1', [5, 6, 7])
    check(ok14, f"kdoc same-basename slots {os.path.basename(ka)}, {os.path.basename(kb)}; -p sets; "
          "a replaced source drops stale pages; prune drops the deleted one; `text DOC 5-7`")
