"""kfp.py `diff` and `libs`: a board's footprints against their library copies, and where
every footprint and 3D model comes from. The comparison follows KiCad's own
(FOOTPRINT::FootprintNeedsUpdate, pcbnew/drc/drc_test_provider_library_parity.cpp), so its
first tier is exactly what DRC's lib_footprint_mismatch counts."""
import glob, os, re, subprocess
from collections import Counter
from kcommon import expand_vars, fp_lib_dirs, kicad_env, kid, natkey, refrange
from kfp import (GFX, SIDE_FLAGS, F, V, _width, board_spans, lib_copy, proj_of, u)


ND = [3]                         # decimals canon() compares at: 3 = 1 um, 6 = the file's own 1 nm


def _norm(n):
    """a node as a hashable tuple: atoms unquoted, numbers to 1 um, uuids dropped"""
    if isinstance(n, str):
        s = u(n)
        try:
            return round(float(s), ND[0]) + 0.0
        except ValueError:
            return {'%R': '${REFERENCE}', '%V': '${VALUE}'}.get(s, s)
    return tuple(_norm(c) for c in n if not (isinstance(c, list) and c and c[0] in ('uuid', 'tstamp')))


def _pt(c, tag):
    k = kid(c, tag)
    return (round(F(k[1]), ND[0]) + 0.0, round(F(k[2]), ND[0]) + 0.0) if k and len(k) > 2 else None


def _fill(c, dflt='no'):
    f = V(c, 'fill') or V(c, 'fill_type') or dflt
    return 'yes' if f in ('yes', 'solid') else 'no'


def _shape_key(c):
    """FOOTPRINT::FootprintNeedsUpdate's shape test (drc_test_provider_library_parity.cpp): the
    geometry (a rect normalised, a polygon from any start vertex), fill and layer; the stroke
    only on copper"""
    k = c[0][3:]
    if k == 'rect':
        (x0, y0), (x1, y1) = _pt(c, 'start'), _pt(c, 'end')
        geo = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    elif k == 'poly':
        pts = [(round(F(x[1]), ND[0]) + 0.0, round(F(x[2]), ND[0]) + 0.0) for x in (kid(c, 'pts') or [])[1:]
               if isinstance(x, list) and x[0] == 'xy']
        pts = [p for i, p in enumerate(pts) if p != pts[i - 1]] if len(pts) > 1 else pts   # KiCad drops repeats
        xs, ys = sorted({x for x, _y in pts}), sorted({y for _x, y in pts})
        if len(pts) == 4 and len(xs) == len(ys) == 2 and len(set(pts)) == 4:   # a rect stored as a poly
            k, geo = 'rect', (xs[0], ys[0], xs[1], ys[1])
        else:
            i = pts.index(min(pts)) if pts else 0
            geo = tuple(pts[i:] + pts[:i])
    elif k == 'arc':                                        # a flip reverses it: the same arc
        a_, m_, e_ = _pt(c, 'start'), _pt(c, 'mid'), _pt(c, 'end')
        geo = (min(a_, e_), m_, max(a_, e_))
    else:
        geo = tuple(_pt(c, t) for t in ('start', 'mid', 'end', 'center') if kid(c, t))
    lay = u(V(c, 'layer'))
    w = round(_width(c), 3) if lay.endswith('.Cu') else None
    return ('fp_' + k, lay, geo, _fill(c), w)


SYM180 = ('circle', 'rect', 'oval', 'roundrect')
PAD_KICAD = ('size', 'drill', 'roundrect_rratio', 'chamfer_ratio', 'chamfer', 'property', 'rect_delta',
             'remove_unused_layers', 'keep_end_layers', 'die_length')
PAD_OVERRIDE = ('solder_mask_margin', 'solder_paste_margin', 'solder_paste_margin_ratio', 'clearance', 'zone_connect',
                'thermal_width', 'thermal_bridge_width', 'thermal_gap', 'thermal_bridge_angle', 'zone_layer_connections')


def _pad_key(c):
    """(kicad, extra): the fields KiCad's DRC compares, and the per-pad overrides it ignores"""
    at = kid(c, 'at') or ['at', '0', '0']
    sh = u(c[3]) if len(c) > 3 else ''
    ang = (F(at[3]) if len(at) > 3 else 0.0) % 360
    drl = kid(c, 'drill') or []
    off = kid(drl, 'offset')
    if sh == 'circle' and not off:
        ang = 0.0                                           # any angle is the same circle
    elif sh in SYM180 and not off and not kid(c, 'rect_delta'):
        ang %= 180                                          # a half turn is the same pad
    kv = {x[0]: _norm(x[1:]) for x in c[4:] if isinstance(x, list) and x and x[0] in PAD_KICAD}
    if sh not in ('roundrect', 'chamfered_rect'):
        kv.pop('roundrect_rratio', None)
    if kid(c, 'primitives'):
        kv['primitives'] = tuple(sorted(str((_shape_key(x)[2], _fill(x, 'yes'), round(_width(x), 3)))  # KiCad 5's
                                        for x in kid(c, 'primitives')[1:] if isinstance(x, list)))   # were filled
    lay = tuple(sorted(u(x) for x in (kid(c, 'layers') or [])[1:]))
    base = {'type': u(c[2]), 'shape': sh, 'at': (round(F(at[1]), ND[0]) + 0.0, round(F(at[2]), ND[0]) + 0.0),
            'angle': round(ang, 2), 'layers': lay}
    base.update(kv)
    extra = {x[0]: _norm(x[1:]) for x in c[4:] if isinstance(x, list) and x and x[0] in PAD_OVERRIDE}
    return base, extra


def canon(t, nd=3):
    """{category: Counter}: 'kicad' = what DRC's lib_footprint_mismatch compares, the rest = what
    else differs (a board-side override, a 3D model, line widths, texts: Update Footprint resets
    those too, but DRC says nothing)"""
    ND[0] = nd
    out = {k: Counter() for k in ('pads', 'shapes', 'zones', 'type', 'xpads', 'strokes', 'texts', 'models', 'settings')}
    attr = set()
    for c in t[2:]:
        if not isinstance(c, list) or not c:
            continue
        k = c[0]
        if k == 'pad':
            base, extra = _pad_key(c)
            n = u(c[1])
            out['pads'][(n, tuple(sorted(base.items())))] += 1
            if extra:
                out['xpads'][(n, tuple(sorted(extra.items())))] += 1
        elif k in GFX:
            out['shapes'][_shape_key(c)] += 1
            if not u(V(c, 'layer')).endswith('.Cu'):
                st = kid(c, 'stroke')
                out['strokes'][(_shape_key(c), round(_width(c), 3), V(st, 'type') if st else '')] += 1
        elif k == 'fp_text' and len(c) > 2 and u(c[1]) == 'user':
            out['texts'][(_norm(c[2]), u(V(c, 'layer')))] += 1
        elif k == 'zone':
            lay = {u(x) for x in (kid(c, 'layers') or kid(c, 'layer') or [])[1:]}
            if {'F.Cu', 'B.Cu'} <= lay and any(l.startswith('In') for l in lay) or '*.Cu' in lay:
                lay = {l for l in lay if not l.endswith('.Cu')} | {'*.Cu'}    # every copper layer, however many
            out['zones'][(tuple(sorted(lay)),
                          V(c, 'name'), V(c, 'priority') or '0', kid(c, 'keepout') is not None,
                          _norm(kid(kid(c, 'polygon') or [], 'pts') or []))] += 1
        elif k == 'model':
            out['models'][_norm(c)] += 1
        elif k == 'attr':
            attr = {u(x) for x in c[1:]}
        elif k == 'allow_soldermask_bridges' or (k == 'attr' and 'allow_soldermask_bridges' in c):
            attr.add('allow_soldermask_bridges')
        elif k in ('solder_mask_margin', 'solder_paste_margin', 'solder_paste_ratio', 'solder_paste_margin_ratio',
                   'clearance', 'zone_connect'):
            out['settings'][_norm(c)] += 1
        elif k == 'net_tie_pad_groups':
            out['type'][_norm(c)] += 1
    out['type'][('attr', tuple(sorted(attr & {'smd', 'through_hole', 'allow_soldermask_bridges'})))] += 1
    out['settings'][('flags', tuple(sorted(attr & (SIDE_FLAGS | {'board_only', 'exclude_from_sim'}))))] += 1
    return out


def _pads_lines(A, B, cat, tag):
    lines = []
    go = {}
    for n, kv in (A[cat] - B[cat]).elements():
        go.setdefault(n, []).append(dict(kv))
    nw = {}
    for n, kv in (B[cat] - A[cat]).elements():
        nw.setdefault(n, []).append(dict(kv))
    for n in sorted(set(go) | set(nw), key=natkey):
        a_, b_ = go.get(n, []), nw.get(n, [])
        if cat == 'xpads':                                  # no override at all is the empty one
            a_, b_ = a_ or [{}], b_ or [{}]
        if len(a_) == len(b_) == 1:
            fa, fb = a_[0], b_[0]
            ch = [f"{k} {_short(fa.get(k, '-'), 30)} -> {_short(fb.get(k, '-'), 30)}"
                  for k in dict.fromkeys(list(fa) + list(fb)) if fa.get(k) != fb.get(k)]
            lines.append(f"  {tag}pad {n or '(no number)'}: " + '; '.join(ch))
        else:
            lines.append(f"  {tag}pad {n or '(no number)'}: {len(a_)} in the library, {len(b_)} on the board")
    return lines


def fp_diff(bf, lf):
    """(kicad, extra) line lists for board copy bf vs library lf: kicad = why DRC says
    lib_footprint_mismatch ([] = it does not), extra = what else differs"""
    A, B = canon(lf.t), canon(bf.t)
    k, x = [], []
    if not any(A[c] != B[c] for c in ('type', 'pads', 'shapes', 'zones')):
        A6, B6 = canon(lf.t, 6), canon(bf.t, 6)
        if any(A6[c] != B6[c] for c in ('type', 'pads', 'shapes', 'zones')):
            x.append("  coordinates differ by < 1 um only (a rotation round trip's rounding): KiCad's DRC can still "
                     "flag it, as it sorts items by exact position before pairing them; nothing physical differs")
        ND[0] = 3
    if A['type'] != B['type']:
        k.append(f"  type: library {_short(list(A['type']))} vs board {_short(list(B['type']))}")
    k += _pads_lines(A, B, 'pads', '')
    for cat, what in (('shapes', 'graphic shapes'), ('zones', 'rule areas')):
        g0, g1 = A[cat] - B[cat], B[cat] - A[cat]
        if g0 or g1:
            per = Counter()
            for key, c in g0.items():
                per[(key[1] if cat == 'shapes' else '/'.join(key[0]), 'lib')] += c
            for key, c in g1.items():
                per[(key[1] if cat == 'shapes' else '/'.join(key[0]), 'brd')] += c
            k.append(f"  {what}: " + ', '.join(f"{l} {per[(l, 'lib')]} library-only / {per[(l, 'brd')]} board-only"
                                               for l in sorted({l for l, _s in per})))
            if cat == 'zones':
                bb = lambda key: [v for xy in key[4][1:] for v in xy[1:]]   # noqa: E731
                for tag, g_ in (('library', g0), ('board  ', g1)):
                    for key in list(g_)[:2]:
                        v = bb(key)
                        print_ = f"{min(v[0::2]):g},{min(v[1::2]):g} .. {max(v[0::2]):g},{max(v[1::2]):g}" if v else '?'
                        k.append(f"    {tag}: {'keepout' if key[3] else 'zone'} {print_} "
                                 f"({max(v[0::2]) - min(v[0::2]):g} x {max(v[1::2]) - min(v[1::2]):g} mm)" if v else '')
            if cat == 'shapes':
                for key in list(g0)[:2]:
                    k.append(f"    library: {key[0]} {key[1]} {_short(key[2], 70)}")
                for key in list(g1)[:2]:
                    k.append(f"    board:   {key[0]} {key[1]} {_short(key[2], 70)}")
    x += _pads_lines(A, B, 'xpads', 'override on ')
    for cat, what in (('strokes', 'line width/style'), ('texts', 'user texts'), ('models', '3D models'),
                      ('settings', 'footprint settings')):
        g0, g1 = A[cat] - B[cat], B[cat] - A[cat]
        if not (g0 or g1):
            continue
        if cat == 'strokes':
            wa = Counter((key[0][1], key[1]) for key in g0.elements())
            wb = Counter((key[0][1], key[1]) for key in g1.elements())
            x.append(f"  {what}: library " + ', '.join(f"{n} {l} {w:g}" for (l, w), n in sorted(wa.items()))
                     + " vs board " + ', '.join(f"{n} {l} {w:g}" for (l, w), n in sorted(wb.items())))
        else:
            x.append(f"  {what}: library {'; '.join(_short(v, 80) for v in g0) or '-'}")
            x.append(f"  {' ' * len(what)}  board   {'; '.join(_short(v, 80) for v in g1) or '-'}")
    return k, x


def _short(x, n=90):
    s = re.sub(r"[(),']", ' ', str(x))
    s = re.sub(r'\s+', ' ', s).strip()
    return s if len(s) <= n else s[:n - 1] + '~'


def c_diff(fps, a):
    proj = proj_of(a.file)
    same, nolib, kd, xd, nm = [], [], [], [], []
    shown = 0
    for f in fps:
        lf, why = lib_copy(f.board[0], proj)
        if lf is None:
            nolib.append(f"{f.ref} ({why})")
            continue
        k, x = fp_diff(f, lf)
        (kd if k else nm if x and x[0].startswith('  coordinates differ by < 1 um') else xd if x else same).append(f.ref)
        if (k or (x and (a.all or len(fps) <= 8))) and shown < a.max:
            shown += 1
            print(f"{f.ref}  {f.board[0]}  " + ("DIFFERS (DRC lib_footprint_mismatch)" if k else
                                               "matches for DRC; differs only in what DRC ignores")
                  + f"\n  library: {lf.src}")
            body_ = k + (["  also (DRC ignores; Update Footprint resets it):"] + ['  ' + y for y in x] if x else [])
            print('\n'.join(body_[:14]) + (f"\n  ... +{len(body_) - 14} more" if len(body_) > 14 else ''))
    print(f"\n{len(kd)} differ as DRC counts it" + (f" ({' '.join(kd[:30])}{' ...' if len(kd) > 30 else ''})" if kd else '')
          + (f"; {len(nm)} by sub-um rounding only, which DRC may still flag ({' '.join(nm[:20])})" if nm else '')
          + f"; {len(xd)} differ only in what DRC ignores (overrides, 3D model, widths, texts)"
          + ('' if a.all or len(fps) <= 8 or not xd else ' - `--all` shows them')
          + f"; {len(same)} identical"
          + (f"; {len(nolib)} without a library copy: {'; '.join(nolib[:6])}" + (' ...' if len(nolib) > 6 else '')
             if nolib else ''))
    print("Not compared: nets, field text and positions. A board-side override (a solid pad, a 3D model swapped "
          "on the board) is lost to Update Footprint from Library unless the library gets it too.")
    return 0


# ---------------------------------------------------------------- libs (where footprints come from)

def c_libs(a):
    proj = proj_of(a.file)
    spans, _ = board_spans(a.file)
    dirs = fp_lib_dirs(proj)
    env = kicad_env(proj)
    stock = [os.path.realpath(d) for d in env['_stock'].values() if d]
    real = os.path.realpath(proj)
    tracked = set()
    r = subprocess.run(['git', '-C', proj, 'ls-files', '-z'], capture_output=True, text=True)
    if not r.returncode:
        tracked = {os.path.realpath(os.path.join(proj, p)) for p in r.stdout.split('\0') if p}

    def where(p):
        rp = os.path.realpath(p)
        if any(rp.startswith(s + os.sep) for s in stock):
            return 'stock'
        if rp.startswith(real + os.sep):
            return 'repo' if not tracked or rp in tracked else 'repo, UNTRACKED'
        return 'outside the repo'

    use, mods = {}, {}
    for ref, txt in spans.items():
        m = re.match(r'\t?\(footprint "((?:[^"\\]|\\.)*)"', txt)
        fpid = m.group(1) if m else '?'
        use.setdefault(fpid, []).append(ref)
        for w in re.findall(r'\(model "((?:[^"\\]|\\.)*)"', txt):
            mods.setdefault(w, []).append(ref)
    rows = {}
    for fpid, refs in use.items():
        lib, _, name = fpid.partition(':')
        d = dirs.get(lib)
        p = os.path.join(d, name + '.kicad_mod') if d else ''
        kind = ('NO LIBRARY' if not d else 'NOT IN LIBRARY' if not os.path.isfile(p) else where(p))
        rows.setdefault((kind, lib), []).append((name, refs))
    order = {'repo': 0, 'repo, UNTRACKED': 1, 'outside the repo': 2, 'NOT IN LIBRARY': 3, 'NO LIBRARY': 4, 'stock': 5}
    print(f"{len(spans)} footprints, {len(use)} distinct, from {len({l for _k, l in rows})} libraries")
    for (kind, lib), items in sorted(rows.items(), key=lambda x: (order.get(x[0][0], 9), x[0][1])):
        refs = [r for _n, rs in items for r in rs]
        print(f"  {kind:<17} {lib:<26} {len(items):3} footprint(s) {len(refs):4} part(s)  "
              f"{dirs.get(lib, '') if kind != 'stock' else ''}")
        if kind != 'stock' or a.verbose:
            for name, rs in sorted(items, key=lambda x: natkey(x[0]))[:a.max]:
                print(f"      {name:<52} {refrange(sorted(rs, key=natkey)) if len(rs) > 1 else rs[0]}")
    # project libraries: footprints no board part uses
    for lib, d in dirs.items():
        if not os.path.realpath(d).startswith(real + os.sep):
            continue
        used = {fp.partition(':')[2] for fp in use if fp.partition(':')[0] == lib}
        spare = sorted(os.path.basename(p)[:-10] for p in glob.glob(os.path.join(d, '*.kicad_mod'))
                       if os.path.basename(p)[:-10] not in used)
        if spare:
            print(f"  unused in {lib}: {' '.join(spare)}")
    # 3D models by where they resolve
    mk = Counter()
    bad, out_ = [], []
    for w, refs in mods.items():
        rp = expand_vars(w, env)
        if not os.path.isabs(rp) and '${' not in rp:
            rp = os.path.join(proj, rp)
        if '${' in rp or not (os.path.isfile(rp) or any(os.path.isfile(os.path.splitext(rp)[0] + e)
                                                       for e in ('.step', '.stp', '.wrl'))):
            bad.append((w, refs))
            continue
        k = where(rp)
        mk[k] += len(refs)
        if k not in ('stock', 'repo'):
            out_.append((k, w, refs))
    rr = lambda refs: refrange(sorted(refs, key=natkey)) if len(refs) > 1 else refs[0]   # noqa: E731
    print(f"3D models: {sum(mk.values())} part(s) resolve ({', '.join(f'{n} {k}' for k, n in mk.most_common())})"
          + f"; {sum(len(r) for _w, r in bad)} part(s) name a file that does not exist")
    for tag, w, refs in (sorted(('missing', w, r) for w, r in bad) + sorted(out_))[:2 * a.max]:
        print(f"  {tag:<17} {w}  ({rr(refs)})")
    print("A board carries its own footprint copies, so fab output never needs a library. 'outside the repo' "
          "is what a clone cannot refresh (Update Footprint), lint, or render in 3D: copy those footprints/models "
          "into the project library (lib/) to make the repo self-contained.")
    return 0


