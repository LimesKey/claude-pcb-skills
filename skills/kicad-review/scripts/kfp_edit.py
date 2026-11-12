"""kfp.py `edit`: scripted edits on a library footprint (.kicad_mod), every op reported and
the lint delta printed; the board copy follows through Update Footprint in KiCad."""
import fnmatch, math, os, uuid
from collections import Counter
from kcommon import kid, kids, natkey
from kfp import (GFX, F, V, body, copper, dump, extent, klc_clearance, lint, num, proj_of, q, u)


EDIT_OPS = {'crtyd': 1, 'fab': 1, 'origin': 1, 'pad': 2, 'widths': 0, 'model': 1, 'rename': 1, 'descr': 1}
EDIT_USE = """edit OP... -o OUT   (ops run in order on a library footprint; OUT may be the input with --in-place)
  crtyd CLR|klc          the courtyard as one 0.05 mm rect round body+pads, CLR mm out (klc: F5.3's
                         class value), snapped outward to the 0.01 mm grid; old courtyard items go
  fab WxH|pads           the Fab body as a W x H outline centred on the origin with KLC's pin-1 bevel
                         (1 mm or 25%, the smaller) at the corner nearest pad 1/A1 (`pads`: the copper
                         extent); old Fab lines/rects/polys go, marker circles stay; adds ${REFERENCE}
  origin body|pads|X,Y   move the origin to the body centre / copper centre / X,Y (everything shifts)
  pad SEL K=V[,V][;K=V]  SEL a pad number or glob ('*', 'A?'); keys: size=W,H at=X,Y shape=S
                         rratio=R drill=D mask=M paste=M pasteratio=R layers=L,L.. num=N
  widths                 KLC line widths: silk 0.12, Fab 0.10, courtyard 0.05
  model PATH|none        the 3D model path (${KIPRJMOD}/lib/... keeps the repo self-contained)
  rename NAME            the footprint name and its Value
  descr TEXT             the description"""


def _gfx(t, layer_sfx, tags=GFX):
    return [x for x in t if isinstance(x, list) and x and x[0] in tags and u(V(x, 'layer')).endswith(layer_sfx)]


def _rect(layer, x0, y0, x1, y1, w):
    return ['fp_rect', ['start', num(x0), num(y0)], ['end', num(x1), num(y1)],
            ['stroke', ['width', num(w)], ['type', 'solid']], ['fill', 'no'], ['layer', q(layer)],
            ['uuid', q(str(uuid.uuid4()))]]


def _insert(t, item):
    """before the first pad (KiCad's order: graphics, then pads)"""
    i = next((i for i, x in enumerate(t) if isinstance(x, list) and x and x[0] in ('pad', 'zone', 'group', 'embedded_fonts',
                                                                                    'model')), len(t))
    t.insert(i, item)


def _shift(n, dx, dy):
    for c in n[1:]:
        if isinstance(c, list) and c:
            if c[0] in ('at', 'start', 'end', 'mid', 'center', 'xy') and len(c) >= 3:
                c[1], c[2] = num(F(c[1]) + dx), num(F(c[2]) + dy)
            elif c[0] not in ('primitives', 'model', 'effects'):     # pad primitives are pad-local
                _shift(c, dx, dy)


def _setkid(n, tag, vals):
    k = kid(n, tag)
    new = [tag] + list(vals)
    if k:
        n[n.index(k)] = new
    else:
        n.insert(next((i for i, x in enumerate(n) if isinstance(x, list) and x[0] in ('net', 'pinfunction', 'uuid')),
                      len(n)), new)


def op_pad(f, sel, spec):
    pads = [p for p in kids(f.t, 'pad') if fnmatch.fnmatchcase(u(p[1]), sel)]
    if not pads:
        raise SystemExit(f"edit: pad {sel!r} matches nothing; nothing written")
    for p in pads:
        for kv in spec.split(';'):
            k, _, v = kv.partition('=')
            vs = [x for x in v.split(',') if x]
            if k == 'size':
                _setkid(p, 'size', [num(float(x)) for x in vs])
            elif k == 'at':
                at = kid(p, 'at')
                _setkid(p, 'at', [num(float(x)) for x in vs] + (at[3:4] if at else []))
            elif k == 'shape':
                p[3] = vs[0]
                if vs[0] == 'roundrect' and not kid(p, 'roundrect_rratio'):
                    _setkid(p, 'roundrect_rratio', ['0.25'])
            elif k == 'rratio':
                _setkid(p, 'roundrect_rratio', [num(float(vs[0]))])
            elif k == 'drill':
                _setkid(p, 'drill', [num(float(x)) for x in vs])
            elif k == 'mask':
                _setkid(p, 'solder_mask_margin', [num(float(vs[0]))])
            elif k == 'paste':
                _setkid(p, 'solder_paste_margin', [num(float(vs[0]))])
            elif k == 'pasteratio':
                _setkid(p, 'solder_paste_margin_ratio', [num(float(vs[0]))])
            elif k == 'layers':
                _setkid(p, 'layers', [q(x) for x in vs])
            elif k == 'num' and len(pads) == 1:
                p[1] = q(vs[0])
            else:
                raise SystemExit(f"edit: pad key {k!r} unknown (or num= on several pads); nothing written")
    return f"pad {sel}: {spec} on {len(pads)} pad(s)"


def op_crtyd(f, v):
    clr, why = (klc_clearance(f) if v == 'klc' else (float(v), 'given'))
    b, _ = body(f)
    e = extent(f) or b
    env = (min(b[0], e[0]) - clr, min(b[1], e[1]) - clr, max(b[2], e[2]) + clr, max(b[3], e[3]) + clr)
    env = (math.floor(env[0] * 100 + 1e-6) / 100, math.floor(env[1] * 100 + 1e-6) / 100,
           math.ceil(env[2] * 100 - 1e-6) / 100, math.ceil(env[3] * 100 - 1e-6) / 100)
    old = _gfx(f.t, '.CrtYd')
    for x in old:
        f.t.remove(x)
    side = 'B' if all(u(V(x, 'layer')).startswith('B.') for x in old) and old else 'F'
    _insert(f.t, _rect(f'{side}.CrtYd', *env, 0.05))
    return (f"crtyd: {len(old)} item(s) -> rect {env[0]:g},{env[1]:g} .. {env[2]:g},{env[3]:g} "
            f"({env[2]-env[0]:.2f} x {env[3]-env[1]:.2f} mm, {clr:g} mm {why})")


def op_fab(f, v):
    if v == 'pads':
        e = extent(f)
        W, H = e[2] - e[0], e[3] - e[1]
    else:
        W, H = (float(x) for x in v.lower().split('x'))
    old = [x for x in _gfx(f.t, '.Fab') if x[0] != 'fp_circle']
    for x in old:
        f.t.remove(x)
    p1 = min(copper(f), key=lambda p: natkey(p['num'] or '~'), default=None)
    sx, sy = (-1 if not p1 or p1['x'] <= 0 else 1), (-1 if not p1 or p1['y'] <= 0 else 1)
    bv = min(1.0, 0.25 * min(W, H))
    hx, hy = W / 2, H / 2
    pts = [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]
    k = pts.index((sx * hx, sy * hy))                    # the pin-1 corner, cut by the bevel
    c = pts[k]
    pts[k:k + 1] = [(c[0], c[1] - sy * bv), (c[0] - sx * bv, c[1])] if k in (0, 2) else \
        [(c[0] - sx * bv, c[1]), (c[0], c[1] - sy * bv)]
    _insert(f.t, ['fp_poly', ['pts'] + [['xy', num(x), num(y)] for x, y in pts],
                  ['stroke', ['width', '0.1'], ['type', 'solid']], ['fill', 'no'], ['layer', q('F.Fab')],
                  ['uuid', q(str(uuid.uuid4()))]])
    note = ''
    if not any(isinstance(x, list) and x and x[0] == 'fp_text' and u(x[2]) in ('${REFERENCE}', '%R') for x in f.t):
        h = max(0.1, min(1.0, round(min(W, H) / 3.2, 2)))
        _insert(f.t, ['fp_text', 'user', q('${REFERENCE}'), ['at', '0', '0', '0'], ['layer', q('F.Fab')],
                      ['uuid', q(str(uuid.uuid4()))],
                      ['effects', ['font', ['size', num(h), num(h)], ['thickness', num(round(h * 0.15, 3))]]]])
        note = f", ${{REFERENCE}} {h:g} mm added"
    return f"fab: {len(old)} item(s) -> {W:g} x {H:g} mm outline, {bv:.2f} mm pin-1 bevel{note}"


def op_origin(f, v):
    if v == 'body':
        b, how = body(f)
    elif v == 'pads':
        b, how = extent(f), 'copper'
    else:
        x, y = (float(s) for s in v.split(','))
        b, how = (x, y, x, y), 'given point'
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    _shift(f.t, -cx, -cy)
    return f"origin: moved to the {how} centre (everything shifted {-cx:+.3f},{-cy:+.3f})"


def op_widths(f):
    n = 0
    for sfx, w in (('.SilkS', 0.12), ('.Fab', 0.1), ('.CrtYd', 0.05)):
        for x in _gfx(f.t, sfx):
            if x[0] == 'fp_circle' and sfx != '.CrtYd':
                continue
            st = kid(x, 'stroke')
            if st and abs(F(V(st, 'width')) - w) > 1e-6:
                _setkid(st, 'width', [num(w)])
                n += 1
    return f"widths: {n} line(s) set to KLC widths"


def c_edit(fps, a):
    if len(fps) != 1 or fps[0].board:
        print("edit works on one library footprint (.kicad_mod or Lib:Name); a board copy is changed by fixing "
              "the library and Update Footprint in KiCad")
        return 1
    f = fps[0]
    if f.legacy:
        print(f"{f.src} is legacy (module ...) format: `kicad-cli fp upgrade {os.path.dirname(f.src)} -o NEW.pretty` first")
        return 1
    ops, i, args = [], 0, list(a.args)
    while i < len(args):
        n = EDIT_OPS.get(args[i])
        if n is None or i + n >= len(args) + (n == 0):
            print(f"edit: bad or short op {args[i]!r}\n{EDIT_USE}")
            return 1
        ops.append((args[i], args[i + 1:i + 1 + n]))
        i += 1 + n
    if not ops or not a.out:
        print(EDIT_USE + ("\n\n-o OUT is required" if ops else ''))
        return 1
    if os.path.abspath(a.out) == os.path.abspath(f.src) and not a.in_place:
        print("refusing to overwrite the input: -o a copy, or pass --in-place")
        return 1
    proj = proj_of(f.src)
    before = lint(f, proj)
    for k, v in ops:
        f._g = None
        msg = (op_pad(f, *v) if k == 'pad' else op_crtyd(f, v[0]) if k == 'crtyd' else op_fab(f, v[0]) if k == 'fab'
               else op_origin(f, v[0]) if k == 'origin' else op_widths(f) if k == 'widths' else None)
        if k == 'model':
            for m in kids(f.t, 'model'):
                f.t.remove(m)
            if v[0] != 'none':
                f.t.append(['model', q(v[0]), ['offset', ['xyz', '0', '0', '0']], ['scale', ['xyz', '1', '1', '1']],
                            ['rotate', ['xyz', '0', '0', '0']]])
            msg = f"model: {v[0]}"
        elif k == 'rename':
            f.t[1] = q(v[0])
            for p in kids(f.t, 'property'):
                if u(p[1]) == 'Value':
                    p[2] = q(v[0])
            msg = f"rename: {v[0]} (save it as {v[0]}.kicad_mod)"
        elif k == 'descr':
            _setkid(f.t, 'descr', [q(v[0])])
            msg = "descr set"
        print(f"  {msg}")
    f._g = None
    after = lint(f, proj)
    with open(a.out, 'w', encoding='utf-8') as fh:
        fh.write(dump(f.t) + '\n')
    key = lambda x: (x['severity'], x['rule'], x['msg'])      # noqa: E731
    kb, ka = Counter(map(key, before)), Counter(map(key, after))
    print(f"wrote {a.out}: lint {len(before)} -> {len(after)} finding(s)")
    for x in sorted(kb - ka):
        print(f"  - [{x[0]}] {x[1]}  {x[2]}")
    for x in sorted(ka - kb):
        print(f"  + [{x[0]}] {x[1]}  {x[2]}")
    print("  then: `kfp.py OUT view` to look; KiCad reformats the file on its next save")
    return 0


