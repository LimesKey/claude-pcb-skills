#!/usr/bin/env python3
"""kfp.py - footprints as files: read, lint, view, compare with the board, edit.

  kfp.py FP show                 pads, pitch, copper gaps, mask webs, body, courtyard, model, format
  kfp.py FP lint                 KLC F5.1-F5.3 + assembly checks; exit 2 on an ERROR
  kfp.py FP view [-o PNG]        kicad-cli's own plot (pads sketched + numbered), as a PNG
  kfp.py FP edit OP... -o OUT    scripted edits on a library footprint (`edit` alone lists them)
  kfp.py BOARD diff [REF...]     each board footprint vs its library copy, field by field: what
                                 DRC's lib_footprint_mismatch means and what Update Footprint changes
  kfp.py BOARD libs              where every board footprint and 3D model comes from, and what a
                                 clone of the repo would lack

FP is a .kicad_mod, a .pretty (show/lint: every footprint in it), Lib:Name through the project's
fp-lib-table (then the global one), or BOARD.kicad_pcb REF: the board's own copy, turned back
into library form (rotation and flip undone, nets, uuids and symbol fields dropped).
"""
import argparse, glob, math, os, re, shutil, subprocess, sys, tempfile
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kcommon import (expand_vars, fp_lib_dirs, kicad_cli, kicad_env, kid, kids, natkey, parse_sexp,  # noqa: E402
                     print_findings)

Q = '\0'                         # parse_sexp(mark=Q): a quoted atom keeps its quotes on the way back out
GFX = ('fp_line', 'fp_rect', 'fp_arc', 'fp_circle', 'fp_poly', 'fp_curve')
BOARD_ONLY = {'at', 'transform', 'uuid', 'tstamp', 'path', 'sheetname', 'sheetfile', 'units', 'locked',
              'placed', 'component_classes'}
PAD_BOARD_ONLY = {'net', 'pinfunction', 'pintype', 'uuid', 'tstamp', 'teardrops', 'locked', 'die_length',
                  'die_delay'}
SIDE_FLAGS = {'dnp', 'exclude_from_bom', 'exclude_from_pos_files'}   # the symbol's to set, not the library's


def u(x):
    """a marked atom as plain text"""
    return x[1:].replace('\\"', '"').replace('\\\\', '\\') if isinstance(x, str) and x.startswith(Q) else x


def q(s):
    return Q + str(s).replace('\\', '\\\\').replace('"', '\\"')


def V(n, tag, d=''):
    k = kid(n, tag)
    return u(k[1]) if k and len(k) > 1 and isinstance(k[1], str) else d


def F(x, d=0.0):
    try:
        return float(u(x))
    except (TypeError, ValueError):
        return d


def num(v):
    s = f"{v:.6f}".rstrip('0').rstrip('.')
    return '0' if s in ('', '-0') else s


def dump(n, ind=0):
    """KiCad's own layout: a node of atoms on one line, anything else one child per line"""
    if isinstance(n, str):
        return '"%s"' % n[1:] if n.startswith(Q) else n
    if all(isinstance(x, str) for x in n):
        return '(' + ' '.join(dump(x) for x in n) + ')'
    head = [dump(x) for x in n[:next(i for i, x in enumerate(n) if isinstance(x, list))]]
    body = ''.join('\n' + '\t' * (ind + 1) + dump(x, ind + 1) for x in n[len(head):])
    return '(' + ' '.join(head) + body + '\n' + '\t' * ind + ')'


# ---------------------------------------------------------------- loading

class Fp:
    """one footprint in library form: `t` the marked tree, `name`, `src` where it came from"""
    def __init__(self, t, src, ref=None, board=None):
        self.t, self.src, self.ref, self.board = t, src, ref, board
        self.name = u(t[1]) if len(t) > 1 else '?'
        self.legacy = t[0] == 'module'
        self._g = None

    @property
    def label(self):
        return f"{self.ref} ({self.name})" if self.ref else self.name

    @property
    def g(self):
        """the kpcb_board footprint object (pads, courtyard rings, silk lines), placed at 0,0"""
        if self._g is None:
            from kpcb_board import Board
            body = dump(['footprint', q('x:' + self.name), ['at', '0', '0']]
                        + [c for c in self.t[2:] if not (isinstance(c, list) and c and c[0] in ('at', 'transform'))])
            fd, p = tempfile.mkstemp(suffix='.kicad_pcb', prefix='kfp_')
            with os.fdopen(fd, 'w') as fh:
                fh.write('(kicad_pcb (version 20240108) (generator "kfp")\n' + body + '\n)\n')
            try:
                b = Board(p)
            finally:
                os.remove(p)
            self._g = next(iter(b.fps.values()))
        return self._g


def proj_of(path):
    """the project dir a file belongs to: the nearest parent with a .kicad_pro, else the cwd"""
    d = os.path.dirname(os.path.abspath(path))
    while d != os.path.dirname(d):
        if glob.glob(os.path.join(d, '*.kicad_pro')):
            return d
        d = os.path.dirname(d)
    return os.getcwd()


def read_mod(path):
    with open(path, encoding='utf-8') as fh:
        return Fp(parse_sexp(fh.read(), mark=Q), path)


def board_spans(path):
    """{ref: footprint text} of a board, without parsing all of it"""
    with open(path, encoding='utf-8') as fh:
        txt = fh.read()
    out = {}
    for m in re.finditer(r'\n\t\(footprint ', txt):
        s = m.start() + 1
        e = txt.index('\n\t)', s) + 3
        r = re.search(r'\(property "Reference" "((?:[^"\\]|\\.)*)"', txt[s:e])
        ref = r.group(1) if r else '?'
        k, n = ref, 2
        while k in out:
            k, n = f"{ref}~dup{n}", n + 1
        out[k] = txt[s:e]
    mc = re.search(r'\(pad_to_mask_clearance ([-\d.]+)\)', txt)
    return out, float(mc.group(1)) if mc else 0.0


def _flip_layer(s):
    if not isinstance(s, str):
        return s
    m = Q if s.startswith(Q) else ''
    b = s[len(m):]
    return m + ('B.' + b[2:] if b.startswith('F.') else 'F.' + b[2:] if b.startswith('B.') else b)


def localise(node):
    """a board footprint node -> library form: the footprint's rotation taken back off pad and
    text angles (stored absolute), a back-side part un-mirrored (KiCad stores its local y
    negated and its layers swapped) and every board-only field dropped"""
    tr, at = kid(node, 'transform'), kid(node, 'at')
    rot = F((kid(tr, 'rotate') or [0, 0])[1]) if tr else F(at[3]) if at and len(at) > 3 else 0.0
    back = V(node, 'layer') == 'B.Cu'

    def fix(n, ctx):
        out = [n[0]]
        for c in n[1:]:
            if not isinstance(c, list):
                out.append(c)
                continue
            if not c or (ctx == 'footprint' and c[0] in BOARD_ONLY) or (ctx == 'pad' and c[0] in PAD_BOARD_ONLY) \
                    or c[0] == 'filled_polygon':
                continue
            c = fix(c, c[0])
            if c[0] in ('at', 'start', 'end', 'mid', 'center', 'xy') and len(c) >= 3:
                if back:
                    c[2] = num(-F(c[2]))
                if c[0] == 'at' and ctx in ('pad', 'property', 'fp_text', 'fp_text_box'):
                    a = (F(c[3]) if len(c) > 3 else 0.0) - rot
                    a = ((-a if back else a) + 180) % 360 - 180
                    c = c[:3] + ([num(a)] if abs(a) > 1e-6 or len(c) > 3 and ctx != 'pad' else [])
            elif c[0] in ('layer', 'layers') and back:
                c = [c[0]] + [_flip_layer(x) for x in c[1:]]
            elif c[0] == 'justify' and back:                 # back-side text reads mirrored
                c = [x for x in c if x != 'mirror']
                if len(c) == 1:
                    continue
            out.append(c)
        return out

    t = fix(node, 'footprint')
    t[1] = q(u(t[1]).partition(':')[2] or u(t[1]))
    if back:
        t = [x if not (isinstance(x, list) and x and x[0] == 'layer') else ['layer', q('F.Cu')] for x in t]
    return t, u(node[1]), rot, back


def load(spec, refs=(), proj=None):
    """[Fp] for a FP spec (see the module doc)"""
    proj = proj or proj_of(spec)
    if spec.endswith('.kicad_pcb'):
        spans, mc = board_spans(spec)
        out = []
        for r in refs or sorted(spans, key=natkey):
            if r not in spans:
                raise SystemExit(f"kfp: no footprint {r!r} on {spec}")
            node = parse_sexp(spans[r], mark=Q)
            t, fpid, rot, back = localise(node)
            f = Fp(t, f"{spec} {r}", ref=r, board=(fpid, rot, back))
            f.nets = {u(p[1]): V(p, 'net') for p in kids(node, 'pad') if len(p) > 1}
            f.mask_clear = mc
            out.append(f)
        return out
    if os.path.isdir(spec):
        return [read_mod(p) for p in sorted(glob.glob(os.path.join(spec, '*.kicad_mod')))]
    if spec.endswith('.kicad_mod'):
        return [read_mod(spec)]
    lib, _, name = spec.partition(':')
    d = fp_lib_dirs(proj).get(lib)
    if not (d and name and os.path.isfile(os.path.join(d, name + '.kicad_mod'))):
        raise SystemExit(f"kfp: {spec!r} is not a .kicad_mod, .pretty, board, or Lib:Name in the lib tables")
    return [read_mod(os.path.join(d, name + '.kicad_mod'))]


def lib_copy(fpid, proj):
    """the library's Fp for a board footprint id, or (None, why)"""
    lib, _, name = fpid.partition(':')
    d = fp_lib_dirs(proj).get(lib)
    if not d:
        return None, f"library {lib!r} is in no fp-lib-table"
    p = os.path.join(d, name + '.kicad_mod')
    if not os.path.isfile(p):
        return None, f"{name}.kicad_mod is not in {d}"
    return read_mod(p), ''


# ---------------------------------------------------------------- geometry

def _width(g):
    return F(V(kid(g, 'stroke') or [], 'width') or V(g, 'width'), 0.0)


def pad_gap(p, o):
    """copper edge-to-edge distance of two pads (circles exact; others as their boxes,
    exact for 0/90 rotations, which is nearly every footprint)"""
    from kpcb_board import pad_box
    if p['shape'] == 'circle' and o['shape'] == 'circle' and not p['prims'] and not o['prims']:
        return math.dist((p['x'], p['y']), (o['x'], o['y'])) - (p['sx'] + o['sx']) / 2
    a, b = pad_box(p), pad_box(o)
    dx, dy = max(a[0] - b[2], b[0] - a[2], 0), max(a[1] - b[3], b[1] - a[3], 0)
    if dx == dy == 0:
        return -min(a[2] - b[0], b[2] - a[0], a[3] - b[1], b[3] - a[1])
    return math.hypot(dx, dy)


def _mask(f, p):
    """a pad's solder mask expansion: its own (or the footprint's) margin, else the board's"""
    return p['mask'] or getattr(f, 'mask_clear', 0.0)


def in_pad(h, pads):
    """the SMD pad a plated hole sits inside (a thermal via in an exposed pad), else None"""
    from kpcb_board import pad_box
    return next((p for p in pads if p['kind'] == 'smd' and p is not h
                 and pad_box(p)[0] <= h['x'] <= pad_box(p)[2] and pad_box(p)[1] <= h['y'] <= pad_box(p)[3]), None)


def thermal_pad(f, cu):
    """the exposed/thermal pad: the biggest SMD pad, >= 1 mm2, 3x the median pad, centred on the body"""
    smd = [p for p in cu if p['kind'] == 'smd']
    if len(smd) < 3:
        return None
    big = max(smd, key=lambda p: p['sx'] * p['sy'])
    med = sorted(p['sx'] * p['sy'] for p in smd)[len(smd) // 2]
    b, _ = body(f)
    near = abs(big['x'] - (b[0] + b[2]) / 2) < 0.15 * (b[2] - b[0]) + 0.05 and \
        abs(big['y'] - (b[1] + b[3]) / 2) < 0.15 * (b[3] - b[1]) + 0.05
    return big if big['sx'] * big['sy'] >= 1.0 and big['sx'] * big['sy'] > 3 * med and near else None


def copper(f):
    return [p for p in f.g.pads if any(l.endswith('.Cu') for l in p['layers'])]


def extent(f):
    from kpcb_board import pad_box, bbox
    pts = [c for p in copper(f) for b in [pad_box(p)] for c in (b[:2], b[2:])]
    return bbox(pts) if pts else None


def body(f):
    """(bbox, from what): the Fab outline, else the copper extent"""
    if f.g.fab:
        return f.g.fab, 'Fab outline'
    e = extent(f)
    return (e, 'pad extent (no Fab outline)') if e else ((0, 0, 0, 0), 'nothing drawn')


def klc_clearance(f):
    """(mm, why) KLC F5.3's courtyard clearance for this kind of part"""
    s = ' '.join([f.name, V(f.t, 'tags')]).lower()          # not descr: prose names nets ("CSP")
    if re.search(r'bga|wlcsp|\b(csp|wlp|ucsp)\b', s):
        return 1.0, 'BGA/WLCSP'
    if re.search(r'conn|header|socket|usb|sma\b|u\.fl|jst|molex|terminal|hdr', s):
        return 0.5, 'connector'
    if re.search(r'crystal|xtal|resonator', s):
        return 0.5, 'crystal'
    if re.search(r'cp_elec|elko|canned', s):
        return 0.5, 'canned capacitor'
    b, _ = body(f)
    if max(b[2] - b[0], b[3] - b[1]) < 1.5:
        return 0.15, 'part < 1.5 mm'
    return 0.25, 'default'


def models(f, proj):
    """[(as written, resolved path, exists)]"""
    env = kicad_env(proj)
    out = []
    for m in kids(f.t, 'model'):
        w = u(m[1]) if len(m) > 1 else ''
        r = expand_vars(w, env)
        if not os.path.isabs(r) and '${' not in r:
            r = os.path.join(proj, r)
        hit = os.path.isfile(r) or os.path.isfile(os.path.splitext(r)[0] + '.step') \
            or os.path.isfile(os.path.splitext(r)[0] + '.wrl')
        out.append((w, r, hit))
    return out


# ---------------------------------------------------------------- show

def c_show(fps, a):
    for f in fps:
        g = f.g
        print(f"=== {f.label}   [{f.src}]")
        ver, gen = V(f.t, 'version'), V(f.t, 'generator_version')
        fmt = ('legacy (module ...) KiCad 5 format' if f.legacy else f"version {ver or '?'} generator {gen or '?'}"
               + ('  -> only KiCad nightly opens it' if gen.endswith('.99') else ''))
        print(f"  format    : {fmt}" if not f.board else
              f"  on board  : {f.board[0]}  rot {f.board[1]:g}" + ('  back side (un-mirrored here)' if f.board[2] else ''))
        if V(f.t, 'descr'):
            print(f"  descr     : {V(f.t, 'descr')[:150]}")
        attr = [u(x) for x in (kid(f.t, 'attr') or [])[1:]]
        print(f"  attr      : {' '.join(attr) or '(none)'}")
        cu = copper(f)
        kinds = Counter(p['kind'] for p in cu)
        print(f"  pads      : {len(g.pads)} ({', '.join(f'{n} {k}' for k, n in kinds.items())}"
              + (f", {len(g.pads) - len(cu)} non-copper" if len(g.pads) > len(cu) else '') + ')')
        rows = []
        for p in sorted(g.pads, key=lambda p: natkey(p['num'] or '~')):
            lay = ' '.join(sorted(l.replace('.Cu', '').replace('.Paste', 'P').replace('.Mask', 'M') for l in p['layers']))
            rows.append(f"    {p['num'] or '-':<5} {p['kind']:<12} {p['shape']:<9} {p['x']:8.3f},{p['y']:8.3f}"
                        f"  {p['sx']:.3f}x{p['sy']:.3f}" + (f" r{p['prot']:g}" if p['prot'] else '')
                        + (f" drill {p['drill']:g}" if p['drill'] else '') + (f" rr {p['rr']:.3f}" if p['rr'] else '')
                        + f"  [{lay}]")
        print('\n'.join(rows[:a.max]) + (f"\n    ... +{len(rows) - a.max} more (--max)" if len(rows) > a.max else ''))
        if len(cu) > 1:
            pair = [(math.dist((p['x'], p['y']), (o['x'], o['y'])), p, o) for i, p in enumerate(cu) for o in cu[i + 1:]
                    if p['num'] != o['num']]
            if pair:
                d, p, o = min(pair, key=lambda x: x[0])
                gp, gpp, gpo = min(((pad_gap(p, o), p, o) for _d, p, o in pair), key=lambda x: x[0])
                web = gp - _mask(f, gpp) - _mask(f, gpo)
                print(f"  pitch     : {d:.3f} mm min centre-centre ({p['num']}-{o['num']})")
                print(f"  copper gap: {gp:.3f} mm min edge-edge ({gpp['num']}-{gpo['num']}); mask web {web:.3f} mm"
                      f" at {_mask(f, gpp):g}/{_mask(f, gpo):g} mm mask expansion")
        e = extent(f)
        if e:
            print(f"  copper    : {e[0]:.3f},{e[1]:.3f} .. {e[2]:.3f},{e[3]:.3f}  ({e[2]-e[0]:.3f} x {e[3]-e[1]:.3f} mm,"
                  f" centre {(e[0]+e[2])/2:+.3f},{(e[1]+e[3])/2:+.3f})")
        b, how = body(f)
        if g.fab:
            print(f"  body      : {b[2]-b[0]:.3f} x {b[3]-b[1]:.3f} mm, centre {(b[0]+b[2])/2:+.3f},{(b[1]+b[3])/2:+.3f}  [{how}]")
        else:
            print("  body      : none drawn on Fab")
        c = g.crtyd
        print("  courtyard : " + (f"{c[0]:.2f},{c[1]:.2f} .. {c[2]:.2f},{c[3]:.2f}  ({c[2]-c[0]:.2f} x {c[3]-c[1]:.2f} mm)"
                                   + ('' if g.cpoly else '  NOT CLOSED') if g.crtyd_real else 'NONE'))
        lays = Counter(u(V(x, 'layer')) for x in f.t if isinstance(x, list) and x and x[0] in GFX + ('fp_text',))
        print(f"  graphics  : {', '.join(f'{l} {n}' for l, n in sorted(lays.items()))}")
        proj = proj_of(f.src.split(' ')[0])
        for w, r, hit in models(f, proj) or [('(none)', '', True)]:
            print(f"  3D model  : {w}" + ('' if hit else f"   MISSING ({r})"))
    return 0


# ---------------------------------------------------------------- lint

def lint(f, proj):
    """[finding] for one footprint"""
    from kpcb_smooth import seg_pad_dist
    g, out = f.g, []

    def add(sev, rule, msg):
        out.append({'severity': sev, 'rule': rule, 'msg': f"{f.label}: {msg}", 'refs': [f.ref] if f.ref else []})

    if V(f.t, 'generator_version').endswith('.99'):
        add('INFO', 'FORMAT', f"saved by a nightly ({V(f.t, 'generator_version')}): stable KiCad cannot open it")
    if f.legacy:
        add('INFO', 'FORMAT', "legacy KiCad 5 (module ...) format: `kicad-cli fp upgrade` before editing")
    attr = {u(x) for x in (kid(f.t, 'attr') or [])[1:]}
    cu = copper(f)
    kinds = {p['kind'] for p in cu if not (p['kind'] == 'thru_hole' and in_pad(p, cu))}   # EP vias aren't THT
    if 'smd' in attr and kinds & {'thru_hole'}:
        add('WARN', 'ATTR', "attr smd, but it has plated through-holes (attr through_hole?)")
    if 'through_hole' in attr and kinds and not kinds & {'thru_hole'}:
        add('WARN', 'ATTR', "attr through_hole, but every pad is SMD")
    if not attr & {'smd', 'through_hole'} and cu:
        add('INFO', 'ATTR', "neither smd nor through_hole: the pos file may treat it as unspecified")
    for k in sorted(attr & SIDE_FLAGS):
        if not f.ref:
            add('INFO', 'ATTR', f"library sets {k}: every placed copy inherits it")

    # courtyard (KLC F5.3)
    clr, why = klc_clearance(f)
    if not g.crtyd_real and cu:
        add('ERROR', 'CRTYD', f"no courtyard (KLC wants {clr:g} mm round body+pads, {why}); `edit crtyd klc`")
    elif cu:
        if not g.cpoly:
            add('WARN', 'CRTYD', "courtyard is not one closed outline (DRC can't test it)")
        b, _ = body(f)
        e = extent(f) or b
        env = (min(b[0], e[0]), min(b[1], e[1]), max(b[2], e[2]), max(b[3], e[3]))
        c = g.crtyd
        m = min(env[0] - c[0], env[1] - c[1], c[2] - env[2], c[3] - env[3])
        if min(e[0] - c[0], e[1] - c[1], c[2] - e[2], c[3] - e[3]) < -1e-4:
            add('WARN', 'CRTYD', f"copper reaches {-min(e[0] - c[0], e[1] - c[1], c[2] - e[2], c[3] - e[3]):.2f} mm "
                                 "outside the courtyard: placement DRC cannot keep a neighbour off those pads")
        elif m < clr - 0.005:
            add('WARN', 'CRTYD', f"courtyard clears body+pads by {m:.3f} mm; KLC F5.3 says {clr:g} ({why}) - "
                                 "a deliberate tight one is fine, it is what placement DRC holds neighbours to")
        crt = [x for x in f.t if isinstance(x, list) and x and x[0] in GFX and u(V(x, 'layer')).endswith('.CrtYd')]
        offg = [n for x in crt for n in _coords(x) if abs(F(n) * 100 - round(F(n) * 100)) > 1e-4]
        if offg:
            add('INFO', 'CRTYD', f"{len(offg)} courtyard coordinate(s) off the 0.01 mm grid (KLC F5.3), e.g. {u(offg[0])}")
        wid = sorted({_width(x) for x in crt} - {0.05})
        if wid:
            add('INFO', 'WIDTH', f"courtyard line width {'/'.join(f'{w:g}' for w in wid)} (KLC: 0.05)")

    # fab (KLC F5.2)
    fab = [x for x in f.t if isinstance(x, list) and x and x[0] in GFX and u(V(x, 'layer')).endswith('.Fab')]
    if cu and not g.fab:
        add('WARN', 'FAB', "no body outline on F.Fab (markers alone are not the housing); `edit fab WxH`")
    wid = sorted({_width(x) for x in fab if x[0] != 'fp_circle'} - {0.0})
    bad = [w for w in wid if not 0.1 - 1e-6 <= w <= 0.15 + 1e-6]
    if bad:
        add('INFO', 'WIDTH', f"Fab line width {'/'.join(f'{w:g}' for w in bad)} (KLC: 0.10-0.15)")
    texts = [(u(x[1]), u(x[2]) if len(x) > 2 else '', u(V(x, 'layer'))) for x in f.t
             if isinstance(x, list) and x and x[0] in ('property', 'fp_text')]
    if cu and not any(t in ('${REFERENCE}', '%R') and l.endswith('.Fab') for _k, t, l in texts):
        add('INFO', 'FAB', "no ${REFERENCE} text on F.Fab (KLC F5.2: the assembly drawing's designator)")

    # silk (KLC F5.1)
    silk = [(l, a_, b_, w) for l, a_, b_, w in g.silklines]
    wid = sorted({w for *_x, w in silk if not 0.1 - 1e-6 <= w <= 0.15 + 1e-6})
    if wid:
        add('INFO', 'WIDTH', f"silk line width {'/'.join(f'{w:g}' for w in wid)} (KLC: 0.10-0.15, 0.12 nominal)")
    worst = {}
    for l, a_, b_, w in silk:
        for p in cu:
            if l[:2] not in {x[:2] for x in p['layers']} and '*.Cu' not in p['layers']:
                continue
            d = seg_pad_dist(a_, b_, p) - w / 2
            need = max(w, p['mask'] if p['mask'] else getattr(f, 'mask_clear', 0.0))
            if d < need and d < worst.get(p['num'], (9,))[0]:
                worst[p['num']] = (d, need)
    over = sorted((n for n, (d, _n) in worst.items() if d < 0), key=natkey)
    near = sorted((n for n, (d, _n) in worst.items() if d >= 0), key=natkey)
    if over:
        add('ERROR', 'SILK', f"silk over {len(over)} pad(s): {' '.join(over[:10])} (the fab clips it off the copper)")
    if near:
        d, need = min(worst[n] for n in near)
        add('WARN', 'SILK', f"silk {d:.3f} mm from {len(near)} pad(s) {' '.join(near[:10])}: KLC F5.1 wants >= {need:g} "
                            "(its line width or the mask expansion; 0.2 recommended)")
    if 'smd' in attr and g.fab:
        fb = g.fab
        inside = [1 for l, a_, b_, w in silk if all(fb[0] + .05 < x < fb[2] - .05 and fb[1] + .05 < y < fb[3] - .05
                                                    for x, y in (a_, b_))]
        if inside:
            add('WARN', 'SILK', f"{len(inside)} silk line(s) under the body: hidden once assembled (KLC F5.1)")

    # pads
    nums = Counter(p['num'] for p in cu if p['num'])
    dup = sorted((n for n, k in nums.items() if k > 1), key=natkey)
    if dup and not kid(f.t, 'duplicate_pad_numbers_are_jumpers'):
        add('INFO', 'PADNUM', f"pad number(s) used more than once (one net each): {' '.join(dup[:8])}")
    ep = thermal_pad(f, cu)
    winds = [p for p in g.pads if not p['num'] and any(l.endswith('.Paste') for l in p['layers'])]
    for p in cu:
        side = 'B.' if all(l.startswith('B.') for l in p['layers'] if l.endswith('.Cu')) else 'F.'
        if p['kind'] == 'smd' and not any(l in (side + 'Mask', '*.Mask') for l in p['layers']):
            add('WARN', 'PADMASK', f"SMD pad {p['num'] or '(no number)'} has no {side}Mask opening: copper under mask")
        if p['kind'] == 'smd' and p['num'] and not any(l in (side + 'Paste', '*.Paste') for l in p['layers']):
            if p is ep and not winds:
                add('WARN', 'PADPASTE', f"exposed pad {p['num']} gets no paste and there are no paste windows: "
                                        "no solder joint under the part")
            elif p is not ep:
                add('INFO', 'PADPASTE', f"SMD pad {p['num']} gets no paste (right for a test point or fiducial)")
    webs, vias, overs = [], {}, []
    for i, p in enumerate(cu):
        for o in cu[i + 1:]:
            if p['num'] == o['num']:
                continue
            gp = pad_gap(p, o)
            h, e = (p, o) if p['kind'] == 'thru_hole' else (o, p)
            if gp < 0 and h['kind'] == 'thru_hole' and in_pad(h, [e]):
                vias.setdefault(e['num'], []).append(h['num'])
            elif gp < 0:
                nets = getattr(f, 'nets', {})
                if nets and nets.get(p['num']) and nets.get(p['num']) == nets.get(o['num']):
                    continue                                 # one net (a FET's drain pads into its tab)
                overs.append((p['num'], o['num'], -gp))
            elif p['kind'] == o['kind'] == 'smd':
                webs.append((gp - _mask(f, p) - _mask(f, o), p['num'], o['num']))
    if overs:
        nets = getattr(f, 'nets', {})
        txt = ' '.join(f"{a_}+{b_}" for a_, b_, _d in overs[:8])
        if nets:
            add('ERROR', 'PADOVER', f"pads overlap on different nets: {txt} (a short)")
        else:
            add('WARN', 'PADOVER', f"differently numbered pads overlap: {txt}; fine only if the symbol puts them "
                                   "on one net (a FET's drain pads into its tab), else a short")
    for n, hs in sorted(vias.items()):
        add('ERROR', 'PADNUM', f"thermal via pad(s) {' '.join(sorted(hs, key=natkey))} sit in pad {n} under other "
                               f"numbers: KiCad nets pads by number, so they are not on {n}'s net - number them {n}")
    thin = [w for w in webs if w[0] < 0.1 - 1e-6]
    if thin:
        w, a_, b_ = min(thin)
        add('INFO', 'MASKWEB', f"mask web {w:.3f} mm ({a_}-{b_}), {len(thin)} pad pair(s) under ~0.1 mm: a fab "
                               "opens those as one window, no solder dam between them (fine for most QFN/0.4 mm pitch)")
    if ep and not winds and any(l.endswith('.Paste') for l in ep['layers']) and \
            F(V(next((x for x in kids(f.t, 'pad') if u(x[1]) == ep['num']), []), 'solder_paste_margin_ratio')) > -0.15:
        add('INFO', 'PASTE', f"exposed pad {ep['num']} ({ep['sx']:.2f}x{ep['sy']:.2f} mm) takes a full paste aperture: "
                             "EPs usually get ~50-80% (windowed) so the part does not float; check the datasheet's "
                             "stencil note")

    # origin (the pos file places the part by its origin)
    if 'smd' in attr and cu:
        b, how = body(f)
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        if math.hypot(cx, cy) > 0.1:
            add('WARN', 'ORIGIN', f"origin {math.hypot(cx, cy):.2f} mm from the {how} centre ({cx:+.3f},{cy:+.3f}): "
                                  "the CPL places by origin, so the fab must offset it; `edit origin body`")

    # 3D models
    ms = models(f, proj)
    if not ms and cu:
        add('INFO', 'MODEL', "no 3D model")
    for w, r, hit in ms:
        if '${' in r:
            add('WARN', 'MODEL', f"3D model path uses an undefined variable: {w}")
        elif not hit:
            add('WARN', 'MODEL', f"3D model file not found: {w} -> {r}")
    return out


def _coords(x):
    return [n for c in x[1:] if isinstance(c, list) for n in
            (c[1:3] if c and c[0] in ('start', 'end', 'mid', 'center', 'xy') else _coords(c))]


def c_lint(fps, a):
    F_ = []
    for f in fps:
        proj = proj_of(f.src.split(' ')[0])
        F_ += lint(f, proj)
    n = Counter(x['severity'] for x in F_)
    print_findings(F_, f"{len(fps)} footprint(s): {n['ERROR']} error, {n['WARN']} warn, {n['INFO']} info")
    return 2 if n['ERROR'] else 0


# ---------------------------------------------------------------- view

def c_view(fps, a):
    f = fps[0]
    with tempfile.TemporaryDirectory(prefix='kfp_view_') as td:
        lib = os.path.join(td, 'v.pretty')
        os.mkdir(lib)
        name = re.sub(r'[^\w.+-]', '_', f.name)
        with open(os.path.join(lib, name + '.kicad_mod'), 'w') as fh:
            fh.write(dump(f.t) + '\n' if f.board else open(f.src).read())
        side = 'F.'
        lays = ','.join(side + l for l in ('Cu', 'Mask', 'SilkS', 'Fab', 'CrtYd')) + ',' + 'B.Cu'
        cli = 'kicad-cli-nightly' if shutil.which('kicad-cli-nightly') else kicad_cli(f.src.split(' ')[0])
        cmd = [cli, 'fp', 'export', 'svg', lib, '--fp', name, '-o', td, '--layers', a.layers or lays]
        r = subprocess.run(cmd + ['--sp', '--spn'], capture_output=True, text=True)
        if r.returncode:                                 # an older kicad-cli: no pad sketching
            r = subprocess.run(cmd, capture_output=True, text=True)
        svg = os.path.join(td, name + '.svg')
        if not os.path.isfile(svg):
            print(f"kicad-cli fp export svg failed: {(r.stderr or r.stdout).strip()[-300:]}")
            return 3
        out = a.out or os.path.join(tempfile.gettempdir(), f"kfp_{name}.png")
        m = re.search(r'viewBox="[-\d.]+ [-\d.]+ ([\d.]+) ([\d.]+)"', open(svg).read(2000))
        w = float(m.group(1)) if m else 10
        r = subprocess.run(['rsvg-convert', '-b', 'white', '-w', str(int(min(2000, max(600, w * a.px)))), '-o', out, svg],
                           capture_output=True, text=True)
        if r.returncode:
            shutil.copy(svg, out[:-4] + '.svg')
            print(f"rsvg-convert failed ({r.stderr.strip()}); the SVG is {out[:-4]}.svg")
            return 3
    print(f"{out}  ({f.label}; layers {a.layers or lays}; pads sketched with numbers)")
    return 0


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('file')
    ap.add_argument('cmd', nargs='?', default='show', choices=['show', 'lint', 'view', 'edit', 'diff', 'libs'])
    ap.add_argument('args', nargs='*', help='REFs (board), or edit ops')
    ap.add_argument('-o', '--out', default='')
    ap.add_argument('--in-place', action='store_true', help='edit: allow OUT == the input file')
    ap.add_argument('--layers', default='', help='view: kicad-cli layer list')
    ap.add_argument('--px', type=float, default=150, help='view: pixels per mm (600-2000 px wide)')
    ap.add_argument('--max', type=int, default=40)
    ap.add_argument('--proj', default='', help='the project whose fp-lib-table resolves Lib:Name (default: the cwd)')
    ap.add_argument('--all', action='store_true', help='diff: also print footprints that differ only where DRC looks away')
    ap.add_argument('-v', '--verbose', action='store_true', help='libs: list stock-library footprints too')
    a = ap.parse_args(argv)
    board = a.file.endswith('.kicad_pcb')
    if a.cmd in ('libs', 'diff'):
        from kfp_diff import c_libs, c_diff
    if a.cmd == 'edit':
        from kfp_edit import c_edit
    if a.cmd == 'libs':
        return c_libs(a) if board else (print("libs takes a .kicad_pcb") or 1)
    if a.cmd == 'diff':
        if not board:
            print("diff takes BOARD.kicad_pcb [REF...] (two libraries: `kicad-cli fp diff` in nightly)")
            return 1
        return c_diff(load(a.file, a.args), a)
    if a.cmd == 'edit':
        return c_edit(load(a.file, (), a.proj or None), a)
    if board and not a.args:
        print(f"{a.cmd} on a board needs REF(s): kfp.py {a.file} {a.cmd} U2")
        return 1
    fps = load(a.file, a.args if board else (), a.proj or None)
    return {'show': c_show, 'lint': c_lint, 'view': c_view}[a.cmd](fps, a)


if __name__ == '__main__':
    sys.exit(main())
