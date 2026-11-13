"""kpcb.py `diff OLD.kicad_pcb`: what an edit changed, OLD -> this board - the fingerprint
every board edit needs. Items are matched by uuid (the writers keep them, KiCad keeps
them): footprints (moved, rotated, flipped, added, removed), their visible silk text
(refdes moved, resized, hidden), board silk items, vias, zones (teardrops counted apart),
and tracks - removed, added, modified (width only, or geometry), net or layer changes on
kept ones, length per layer, and the series resistance of each net's changed tracks
(stackup copper thickness per layer: a SUM over those tracks, not the path R - `ampacity
--from --to --fills` is that). --box X0,Y0,X1,Y1 limits vias and tracks to that region;
-v lists each net's removed (-), added (+) and re-widened (~) segments with coordinates.
`diff SCRATCH --patch [--base COPY] -o OUT` writes the other way: this board with SCRATCH's
tracks, vias and zones (c_patch)."""
import math, re
from collections import defaultdict, Counter
from kcommon import natkey, trunc, unesc_disp
from kpcb_board import Board, RHO_CU, thick_of


def _r(b, t):
    return RHO_CU * t['len'] / max(t['w'] * thick_of(b, t['layer']), 1e-9)


TXT = ('text', 'layer', 'x', 'y', 'ang', 'h', 'thick', 'hidden', 'mirror', 'knockout')


def _tkey(t):
    return tuple(round(t[k] % 360 if k == 'ang' else t[k], 3) if isinstance(t[k], float) else t.get(k) for k in TXT)


def _silk_fields(f):
    return [t for t in f.fields if t['layer'].endswith('.SilkS')]


def _what(new, old):
    """'Reference ang 180->0 knockout off' for texts matched by uuid (else by kind, in order)"""
    out, ob = [], {t['uuid'] or (t['kind'], i): t for i, t in enumerate(old)}
    for i, t in enumerate(new):
        o = ob.pop(t['uuid'] or (t['kind'], i), None)
        if o is None:
            out.append(f"{t['kind']} added"); continue
        ch = [k for k, x, y in zip(TXT, _tkey(t), _tkey(o)) if x != y]
        ch = ['moved' if k in ('x', 'y') else f"{k} {'on' if t[k] else 'off'}" if isinstance(t[k], bool)
              else f"{k} {o[k]:g}->{t[k]:g}" if isinstance(t[k], float) else k for k in ch]
        if ch:
            out.append(f"{t['kind']} " + ' '.join(dict.fromkeys(ch)))
    return ', '.join(out + [f"{o['kind']} removed" for o in ob.values()])


def _inbox(box, pts, r=0.0):
    return not box or any(box[0] - r <= x <= box[2] + r and box[1] - r <= y <= box[3] + r for x, y in pts)


def _rekeyed(added, removed, new, old, key):
    """drop added/removed pairs that are the same item under a new uuid (a KiCad save can
    re-uuid untouched copper); returns how many"""
    pool = defaultdict(list)
    for u in removed:
        pool[key(old[u])].append(u)
    n = 0
    for u in sorted(added):
        k = key(new[u])
        if pool.get(k):
            removed.discard(pool[k].pop())
            added.discard(u)
            n += 1
    return n


def _teardrops(new, old, near=1.5):
    """(added, removed, moved) teardrops. Keyed by (net, layer, centroid to 0.01 mm), since
    KiCad gives a regenerated teardrop a new uuid; an unmatched removed/added pair on the same
    net and layer within `near` mm is one teardrop that moved with its via or track end."""
    k = lambda t: (t[0], t[1], round(t[2][0], 2), round(t[2][1], 2))  # noqa: E731
    def excess(xs, ys):                       # the xs a multiset subtraction leaves over
        left, out = Counter(map(k, xs)) - Counter(map(k, ys)), []
        for t in xs:
            if left[k(t)] > 0:
                left[k(t)] -= 1
                out.append(t)
        return out
    add, rem = excess(new, old), excess(old, new)
    moved = []
    for r in list(rem):
        cand = [t for t in add if t[:2] == r[:2] and math.dist(t[2], r[2]) <= near]
        if cand:
            t = min(cand, key=lambda t: math.dist(t[2], r[2]))
            add.remove(t); rem.remove(r); moved.append((r, t))
    return add, rem, moved


def _pair(new, old):
    """{new ref: old ref}: by footprint uuid first (deleting one REF**~dupN logo renumbers
    the rest, so a reference match would pair unrelated logos), then by reference"""
    ou = {}
    for r, g in old.items():
        if g.uuid:
            ou.setdefault(g.uuid, r)
    pairs = {r: ou[f.uuid] for r, f in new.items() if f.uuid and f.uuid in ou}
    taken = set(pairs.values())
    for r in new:
        if r not in pairs and r in old and r not in taken:
            pairs[r] = r
    return pairs

def _zkids(txt):
    """a zone's text as (header, [(child name, text)], closer): KiCad's formatter opens each
    direct child on a line of its own at two tabs"""
    cut = txt.rindex('\n\t)')
    ks = re.split(r'\n(?=\t\t\()', txt[:cut])
    return ks[0], [(re.match(r'\t\t\((\w+)', k)[1], k) for k in ks[1:]], txt[cut:]


def _zsplice(btxt, stxt):
    """this board's zone text with SCRATCH's layers, fill settings (the fillet) and outline,
    its saved fill dropped (refill); stxt None: btxt unfilled"""
    grp = lambda n: 'layers' if n == 'layer' else n    # noqa: E731
    h, bk, end = _zkids(btxt)
    sk = _zkids(stxt)[1] if stxt else []
    take = {'layers', 'fill', 'polygon'} if stxt else set()
    out, done = [h], set()
    for n, k in bk:
        g = grp(n)
        if n in ('filled_polygon', 'fill_segments'):
            continue
        if g in take:
            if g not in done:
                out += [k2 for n2, k2 in sk if grp(n2) == g]
                done.add(g)
            continue
        out.append(k)
    return '\n'.join(out) + end


def c_patch(b, s, a):
    """`diff SCRATCH --patch -o OUT [--base COPY]`: this board with SCRATCH's tracks, vias and
    zones, written into this board's own text (SCRATCH was saved by kicad-cli: never hand that
    file back; replaying the command log diverges - fresh uuids, refilled vs stale fills). By
    uuid: a track or via SCRATCH dropped goes (its teardrops with it), one it changed or added is
    copied verbatim; a changed zone gets SCRATCH's layers, fill settings (fillet) and outline
    spliced into this board's text, fill dropped; an added zone comes unfilled. --base COPY (the
    copy SCRATCH was made from): only what SCRATCH changed from COPY is carried, and an item
    this board changed since then (and SCRATCH too) is a clash, left as this board has it.
    Footprints, silk and the rest are never carried. OUT is re-read and checked item by item."""
    from kpcb_edit import PcbText, tear_edits
    if not a.out:
        print("diff SCRATCH --patch -o OUT [--base COPY]   (SCRATCH's tracks, vias and zones onto this board)"); return 1
    o = Board(a.base) if a.base else b
    q4 = lambda p: (round(p[0], 4), round(p[1], 4))    # noqa: E731

    def items(bd):
        t = PcbText(bd.path)
        k = {x['uuid']: ('trk', x['net'], x['layer'], round(x['w'], 4), q4(x['a']), q4(x['b']), q4(x['mid'])) for x in bd.tracks}
        k.update({v['uuid']: ('via', v['net'], q4((v['x'], v['y'])), v['size'], v['drill'], tuple(v['layers']), v['free'])
                  for v in bd.vias})
        for z in bd.zones:
            if z.uuid not in t.span:                 # a footprint's own rule area: never carried
                continue
            zt = t.text(z.uuid)
            sm, r = re.search(r'\(smoothing (\w+)\)', zt), re.search(r'\(radius ([-\d.]+)\)', zt)
            k[z.uuid] = ('zone', z[0], tuple(z[1]), tuple(q4(p) for p in z.outline), z.priority, sm and sm[1],
                         r and round(float(r[1]), 4))
        return t, k
    (bt, B), (st, S) = items(b), items(s)
    O = items(o)[1] if a.base else B
    todo = {u for u in set(S) | set(O) if S.get(u) != O.get(u)}           # what SCRATCH changed
    clash = {u for u in todo if B.get(u) != O.get(u) and B.get(u) != S.get(u)}
    n, gone = Counter(), []
    trk = {x['uuid']: x for x in b.tracks}
    for u in sorted(todo - clash):
        kind = (S.get(u) or O.get(u))[0]
        if B.get(u) == S.get(u):
            continue                                 # this board has it already
        if u in S and u in B:
            bt.sub(u, _zsplice(bt.text(u), st.text(u)) if kind == 'zone' else st.text(u))
            n[kind + ' changed'] += 1
        elif u in S:
            bt.add((_zsplice(st.text(u), None) if kind == 'zone' else st.text(u)) + '\n')
            n[kind + ' added'] += 1
        elif u in B:
            bt.sub(u, '')
            n[kind + ' removed'] += 1
        if u in trk:
            gone.append(trk[u])
    tear = len(tear_edits(bt, gone))
    bt.save(a.out)
    print(f"patch {s.path} onto {b.path} -> {a.out}: " + (', '.join(f"{v} {k}" for k, v in sorted(n.items())) or 'nothing to carry')
          + f"; {tear} teardrop(s) of changed copper dropped" + ("; changed zones unfilled: refill" if n['zone changed'] + n['zone added'] else ''))
    if clash:
        print(f"  {len(clash)} clash(es): changed on this board since {a.base} and by SCRATCH - left as this board has "
              "them: " + ' '.join(sorted(u[:8] for u in clash)[:12]))
    elif todo and not a.base:
        print("  (no --base: an item this board changed after SCRATCH was copied is SCRATCH's now - --base COPY keeps it)")
    R = items(Board(a.out))[1]
    want = {u: B.get(u) if u in clash or u not in todo else S.get(u) for u in set(B) | set(S)}
    bad = sorted(u for u in set(want) | set(R) if R.get(u) != want.get(u))
    print(f"  check ok: {a.out}'s tracks, vias and zones are this board's with SCRATCH's {len(todo - clash)} change(s)"
          if not bad else f"  MISMATCH on {len(bad)} item(s): {' '.join(u[:8] for u in bad[:12])} - do not use {a.out}")
    return 2 if bad else 0


def c_diff(b, a):
    if not a.args:
        print("diff OLD.kicad_pcb [--box X0,Y0,X1,Y1] [-v]   (what changed from OLD to this board)"); return 1
    box = tuple(float(v) for v in a.box.split(',')) if a.box else None
    try:
        o = Board(a.args[0])
    except FileNotFoundError:
        print(f"diff: no such board: {a.args[0]}"); return 3
    except ValueError as e:
        print(f"diff: {e}"); return 3
    if a.patch:
        return c_patch(b, o, a)
    print(f"diff {a.args[0]} -> {b.path}" + (f"  (vias and tracks in {a.box} only)" if box else ''))
    lines, same = [], []
    # footprints
    mv, rot, flip, txt, placed, ren = [], [], [], [], set(), []
    pairs = _pair(b.fps, o.fps)
    for ref in sorted(pairs, key=natkey):
        f, g = b.fps[ref], o.fps[pairs[ref]]
        if ref.split('~dup')[0] != pairs[ref].split('~dup')[0]:
            ren.append(f"{pairs[ref]}->{ref}")
        if f.layer != g.layer:
            flip.append(ref)
        if math.dist((f.x, f.y), (g.x, g.y)) > 1e-4:
            mv.append(f"{ref} {f.x - g.x:+.3f},{f.y - g.y:+.3f}")
        if abs((f.rot - g.rot + 180) % 360 - 180) > 1e-6:
            rot.append(f"{ref} {g.rot:g}->{f.rot:g}")
        if f.layer != g.layer or math.dist((f.x, f.y), (g.x, g.y)) > 1e-4 or f.rot != g.rot:
            placed.add(ref)
        if sorted(map(_tkey, _silk_fields(f))) != sorted(map(_tkey, _silk_fields(g))):
            txt.append(ref)
    add = sorted(set(b.fps) - set(pairs), key=natkey)
    rem = sorted(set(o.fps) - set(pairs.values()), key=natkey)
    fp_n = len(pairs) - len(placed)
    if mv or rot or flip or add or rem or ren:
        lines.append(f"footprints: {len(mv)} moved, {len(rot)} rotated, {len(flip)} flipped, {len(add)} added, "
                     f"{len(rem)} removed" + (f", {len(ren)} renamed" if ren else ''))
        for tag, xs in (('moved', mv), ('rotated', rot), ('flipped', flip), ('added', add), ('removed', rem),
                        ('renamed', ren)):
            if xs:
                lines.append(f"  {tag:<8} " + ', '.join(xs[:a.max]) + (f" +{len(xs) - a.max}" if len(xs) > a.max else ''))
    else:
        same.append(f"footprints ({fp_n})")
    # silk: footprint text and board graphics on the silkscreen
    still = [r for r in txt if r not in placed]
    sb, so = Counter((ly, tuple(round(v, 3) for v in bb)) for ly, bb in b.silk), \
        Counter((ly, tuple(round(v, 3) for v in bb)) for ly, bb in o.silk)
    tb, to = {t['uuid']: t for t in b.silktexts}, {t['uuid']: t for t in o.silktexts}
    bt = [u for u in set(tb) & set(to) if _tkey(tb[u]) != _tkey(to[u])]
    cel = lambda d: {u for u, t in d.items() if t['kind'] == 'table'}     # noqa: E731
    ca, cr = len(cel(tb) - cel(to)), len(cel(to) - cel(tb))
    if txt or sb != so or bt or ca or cr:
        lines.append(f"silk: visible text changed on {len(txt)} footprint(s) ({len(still)} of them did not move)"
                     + (f"; board silk items {sum(so.values())} -> {sum(sb.values())}, "
                        f"{sum((sb - so).values())} new/changed" if sb != so else '')
                     + (f"; {len(bt)} board text(s) restyled in place" if bt else '')
                     + (f"; table cells {ca} added, {cr} removed" if ca or cr else ''))
        for r in still[:a.max]:
            lines.append(f"  {r}: " + _what(_silk_fields(b.fps[r]), _silk_fields(o.fps[pairs[r]])))
        if len(still) > a.max:
            lines.append(f"  +{len(still) - a.max} more text-only: " + ' '.join(still[a.max:a.max * 3]))
        for u in sorted(bt, key=lambda u: tb[u]['text'])[:a.max]:
            lines.append(f"  {'table cell' if tb[u]['kind'] == 'table' else 'board text'} '{trunc(tb[u]['text'].replace(chr(10), ' '), 24)}': " + _what([tb[u]], [to[u]]).removeprefix('board '))
    else:
        same.append("silk")
    # vias
    vb = {v['uuid']: v for v in b.vias if _inbox(box, [(v['x'], v['y'])], v['size'] / 2)}
    vo = {v['uuid']: v for v in o.vias if _inbox(box, [(v['x'], v['y'])], v['size'] / 2)}
    key = lambda v: (round(v['x'], 4), round(v['y'], 4), v['size'], v['drill'], v['net'], tuple(v['layers']), v['free'])  # noqa: E731
    vch = [u for u in set(vb) & set(vo) if key(vb[u]) != key(vo[u])]
    va, vr = set(vb) - set(vo), set(vo) - set(vb)
    vre = _rekeyed(va, vr, vb, vo, key)
    if vch or va or vr or vre:
        lines.append(f"vias: {len(vch)} changed, {len(va)} added, {len(vr)} removed ({len(vo)} -> {len(vb)})"
                     + (f"; {vre} only got a new uuid" if vre else ''))
        for u in sorted(vch)[:a.max]:
            v, w = vb[u], vo[u]
            lines.append(f"  {unesc_disp(v['net'])} {w['x']:.3f},{w['y']:.3f} -> {v['x']:.3f},{v['y']:.3f}"
                         + (f" net {unesc_disp(w['net'])} -> {unesc_disp(v['net'])}" if v['net'] != w['net'] else ''))
        for tag, us, src in (('added', va, vb), ('removed', vr, vo)):
            for u in sorted(us, key=lambda u: (src[u]['net'], src[u]['x'], src[u]['y']))[:a.max]:
                v = src[u]
                lines.append(f"  {tag:<7} {unesc_disp(v['net']) or '(no net)'} {v['size']:g}/{v['drill']:g} "
                             f"{v['x']:.3f},{v['y']:.3f}" + ('  free' if v.get('free') else ''))
            if len(us) > a.max:
                lines.append(f"  {tag:<7} ... +{len(us) - a.max} more")
    else:
        same.append(f"vias ({len(vb)})")
    # zones (not teardrops)
    zb, zo = {z.uuid: z for z in b.zones}, {z.uuid: z for z in o.zones}
    zk = lambda z: (z[0], tuple(z[1]), tuple(z.outline), z.priority, z.keepout)  # noqa: E731
    zch = [u for u in set(zb) & set(zo) if zk(zb[u]) != zk(zo[u])]
    za, zr = set(zb) - set(zo), set(zo) - set(zb)
    if zch or za or zr:
        lines.append(f"zones: {len(zch)} changed, {len(za)} added, {len(zr)} removed (not counting teardrops)")
        for u in sorted(zch)[:a.max]:
            lines.append(f"  changed {unesc_disp(zb[u][0]) or 'rule area'} {'/'.join(zb[u][1])} '{zb[u].name}'")
        for u in sorted(za)[:a.max]:
            lines.append(f"  added   {unesc_disp(zb[u][0]) or 'rule area'} {'/'.join(zb[u][1])} '{zb[u].name}'")
    else:
        same.append(f"zones ({len(zb)})")
    tda, tdr, tdm = _teardrops([t for t in b.teardrops if _inbox(box, [t[2]])],
                               [t for t in o.teardrops if _inbox(box, [t[2]])])
    if tda or tdr or tdm:
        lines.append(f"teardrops: {len(o.teardrops)} -> {len(b.teardrops)}: {len(tdm)} moved, "
                     f"{len(tda)} added, {len(tdr)} removed (KiCad regenerates them; a moved one follows its via/track)")
        for tag, it in [('moved', m) for m in tdm] + [('added', t) for t in tda] + [('removed', t) for t in tdr]:
            if tag == 'moved':
                (n, ly, p), (_, _, q) = it
                lines.append(f"  moved   {unesc_disp(n)} {ly} {p[0]:.2f},{p[1]:.2f} -> {q[0]:.2f},{q[1]:.2f}")
            else:
                n, ly, p = it
                lines.append(f"  {tag:<7} {unesc_disp(n)} {ly} {p[0]:.2f},{p[1]:.2f}")
            if len(lines) > 400:
                break
    else:
        same.append(f"teardrops ({len(b.teardrops)})")
    # tracks
    tb = {t['uuid']: t for t in b.tracks if _inbox(box, [t['a'], t['b'], t['mid']], t['w'] / 2)}
    to = {t['uuid']: t for t in o.tracks if _inbox(box, [t['a'], t['b'], t['mid']], t['w'] / 2)}
    geo = lambda t: (tuple(round(v, 4) for v in t['a']), tuple(round(v, 4) for v in t['b']))  # noqa: E731
    wonly, moved, renet, relay = [], [], [], []
    for u in set(tb) & set(to):
        t, w = tb[u], to[u]
        if t['net'] != w['net']:
            renet.append(u)
        if t['layer'] != w['layer']:
            relay.append(u)
        if geo(t) != geo(w):
            moved.append(u)
        elif abs(t['w'] - w['w']) > 1e-6:
            wonly.append(u)
    ta, tr = set(tb) - set(to), set(to) - set(tb)
    tre = _rekeyed(ta, tr, tb, to, lambda t: (t['net'], t['layer'], round(t['w'], 4), frozenset(geo(t))))
    if wonly or moved or renet or relay or ta or tr or tre:
        lines.append(f"tracks: {len(tr)} removed, {len(ta)} added, {len(moved)} re-laid (same uuid, new ends), "
                     f"{len(wonly)} width-only; {len(to)} -> {len(tb)}" + (f"; {tre} only got a new uuid" if tre else ''))
        if renet or relay:
            lines.append(f"  !! {len(renet)} kept track(s) changed net, {len(relay)} changed layer")
        L = defaultdict(float)
        for t in tb.values():
            L[t['layer']] += t['len']
        for t in to.values():
            L[t['layer']] -= t['len']
        lines.append("  length: " + ', '.join(f"{ly} {L[ly]:+.2f} mm" for ly in b.copper if abs(L.get(ly, 0)) > 5e-3)
                     + f"  (total {sum(L.values()):+.2f} mm)")
        nets = defaultdict(lambda: [0.0, 0.0, 0])                    # net -> [R old, R new, tracks]
        for u in tr | set(moved) | set(wonly):
            nets[to[u]['net']][0] += _r(o, to[u])
            nets[to[u]['net']][2] += 1
        for u in ta | set(moved) | set(wonly):
            nets[tb[u]['net']][1] += _r(b, tb[u])
        ws = Counter(round(tb[u]['w'] - to[u]['w'], 3) for u in wonly)
        if ws:
            lines.append("  widths: " + ', '.join(f"{d:+g} mm x{n}" for d, n in ws.most_common(6)))
        top = sorted(nets.items(), key=lambda kv: -abs(kv[1][1] - kv[1][0]))
        ext = defaultdict(list)                      # net -> the changed tracks' ends, both versions
        for u in tr | set(moved) | set(wonly):
            ext[to[u]['net']] += [to[u]['a'], to[u]['b']]
        for u in ta | set(moved) | set(wonly):
            ext[tb[u]['net']] += [tb[u]['a'], tb[u]['b']]
        lines.append(f"  series R of the changed tracks, per net ({len(nets)} net(s), biggest change first; a SUM "
                     f"over them, not the path R: `ampacity --from --to --fills` is that):")
        for net, (r0, r1, n) in top[:a.max]:
            e = ext[net]
            lines.append(f"    {unesc_disp(net) or '(no net)':<30} {r0 * 1e3:8.2f} -> {r1 * 1e3:8.2f} mohm ({r1 * 1e3 - r0 * 1e3:+.2f})"
                         f"  in {min(x for x, _ in e):.2f},{min(y for _, y in e):.2f} .. {max(x for x, _ in e):.2f},"
                         f"{max(y for _, y in e):.2f}")
            if a.verbose:
                for tag, us, src in (('-', tr | set(moved), to), ('+', ta | set(moved), tb), ('~', set(wonly), tb)):
                    for u in sorted((u for u in us if src[u]['net'] == net), key=lambda u: (src[u]['layer'], src[u]['a'])):
                        t = src[u]
                        lines.append(f"        {tag} {t['layer']:<7} w{(str(to[u]['w']) + '->') if tag == '~' else ''}{t['w']:g}  "
                                     f"{t['a'][0]:.4f},{t['a'][1]:.4f} -> {t['b'][0]:.4f},{t['b'][1]:.4f}  {u[:8]}")
        if len(top) > a.max:
            lines.append(f"    ... +{len(top) - a.max} more net(s)")
    else:
        same.append(f"tracks ({len(tb)})")
    print('\n'.join(lines) if lines else "no change")
    if same:
        print(f"identical: {', '.join(same)}")
    from kpcb_tracks import nothing_delta, touched_nets
    nets = touched_nets(o, b)
    if box:                                          # only nets with copper in the box
        inb = lambda p: box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]   # noqa: E731
        nets = {x['net'] for x in o.tracks + b.tracks if x['net'] in nets and (inb(x['a']) or inb(x['b']))} | \
            {v['net'] for v in o.vias + b.vias if v['net'] in nets and inb((v['x'], v['y']))}
    rows = nothing_delta(o, b, nets) if nets else []
    if any(r[3] or r[4] for r in rows):
        print(f"do-nothing copper on the {len(nets)} changed net(s): "
              + ', '.join(f"{lab} +{len(add)}/-{gone}" for _k, lab, _f, add, gone in rows if add or gone))
        for _k, lab, fix, add, _g in rows:
            for net, desc, u in add[:a.max]:
                print(f"  + {lab[:-1] if lab.endswith('s') else lab}: {unesc_disp(net):<22} {desc}  {' '.join(x[:8] for x in u[:8])}"
                      f"  (`{fix}`)")
    elif nets:
        print(f"do-nothing copper on the {len(nets)} changed net(s): none added or removed")
    return 0
