"""kpcb.py `zoneshape`: zone outlines as a designer draws them by hand - few vertices on
0/45/90 edges, corners rounded only by the zone's own (smoothing fillet) - not the dense
outlines an area optimiser or a raster trace leaves.

`zoneshape`: every zone ranked by how far its outline is from that: vertices, off-45 edges,
micro-edges (< 0.3 mm), faceted arc runs, and how many vertices the proposal below drops.

`zoneshape ZONE [--eps E] [-o OUT]` (ZONE: a uuid prefix or the zone's name): the proposal
for one zone. Faceted arcs become sharp corners + KiCad's 0.2 fillet (kpcb_fillet), corners
within E (0.1 mm) of a straight edge go (Douglas-Peucker), edges within E/2 of 0/45/90 go on
that line (kpcb_fillet.octilinear). Net, priority and every other zone setting stay. The dry
run checks the outline: stays simple, same-net pads inside it before are inside after, no
vertex leaves the board, how far it moved. -o OUT writes it with the zone's fill dropped
(refill in KiCad), then refills scratch copies of the input and OUT with kicad-cli and
compares the net's copper pieces (the same pads must stay joined) and its copper round the
zone (mm2, before -> after). OUT itself is never a kicad-cli save (a format bump); the
refilled copies are deleted.

`--redraw` first redraws the outline along the boundaries its fill keeps to anyway (`redraw`):
other-net copper and its clearance, the edge band and off the board, no-pour rule areas,
fills that out-rank it or are its own net's. Corners whose removal changes only that area
(to within E) go, edges on 0/45/90 where that holds too; -o then fails (exit 2) if the
refilled copper round the zone moves > 1% / 0.5 mm2. Not courtyards: they shape no fill."""
import math, os, re, shutil, subprocess, tempfile
from kpcb_board import Board, inside, poly_area
from kpcb_fillet import chains, clean, fillet_outline, octilinear, simple, smooth_fill, _ring_dist
from kpcb_route import simplify
from kpcb_edit import PcbText, num
from kcommon import kicad_cli, trunc

MICRO = 0.3           # tracks --kind zonepts: a designer's zones are <= 22 corners, <= 3 edges under this


def metrics(P):
    """(vertices, off-45 edges, micro-edges, faceted arc runs)"""
    off = micro = 0
    for a, c in zip(P, P[1:] + P[:1]):
        L = math.dist(a, c)
        if L < 1e-6:
            continue
        th = math.degrees(math.atan2(c[1] - a[1], c[0] - a[0]))
        off += abs((th + 22.5) % 45 - 22.5) > 0.5
        micro += L < MICRO
    return len(P), off, micro, len(chains(P))


def propose(P, eps=0.1, fit=None):
    """(outline, fillet radius or None): unrounded, `fit` (redraw), simplified, octilinear"""
    Q, r, _note = fillet_outline(P)
    Q = fit(Q) if fit else Q
    Q = simplify(Q, eps)
    Q = clean(octilinear(Q, tol=eps / 2))
    return (Q, r) if len(Q) >= 3 and simple(Q) else (P, None)


def _lys(b, z):
    return list(b.copper) if '*.Cu' in z[1] else [ly for ly in z[1] if ly in b.copper]


def dontcare(b, z, res=0.05):
    """(Grid, raster): 1 where zone z's fill can be on none of its layers or adds no copper -
    within clearance of other-net copper (a Grid for a 0-width centreline: a fill point), the
    edge band and off the board, a no-pour rule area, another zone's saved fill of z's net
    (copper already there) or of another net out-ranking z (ZONE::HigherPriority). A foreign
    pour z out-ranks stays 0 (z would take it: cut=True keeps Grid from painting any); so do a
    same-net pad and teardrops (not in b.fills: free, the safe side)."""
    from kpcb_route import Grid, _kos
    from kpcb_board import _pidx, bbox
    bb, lys = bbox(z.outline), _lys(b, z)
    g = Grid(b, z[0], (bb[0] - 1, bb[1] - 1, bb[2] + 1, bb[3] + 1), res, 0.0, 0.6, 0.3, lys, cut=True, vias=False)
    pri = {o.uuid: (o.priority, o.uuid or '') for o in b.zones}     # ZONE::HigherPriority: ties go by uuid
    for fl in b.fills:
        if fl['layer'] in g.blk and fl.get('zone') != z.uuid and \
                (fl['net'] == z[0] or pri.get(fl.get('zone'), (-1, '')) > (z.priority, z.uuid or '')):
            g.fill_rows(_pidx(b, fl), g.blk[fl['layer']])
    for kl, idx, _nv, nopour, _nt in _kos(b):
        for ly in kl & set(lys) if nopour else ():
            g.fill_rows(idx, g.blk[ly])
    ras = g.blk[lys[0]]
    for ly in lys[1:]:
        ras = bytearray(x & y for x, y in zip(ras, g.blk[ly]))
    return g, ras


def _knees(a, c):
    """the two 0/45/90 two-edge paths a -> c: the diagonal first, or last"""
    dx, dy = c[0] - a[0], c[1] - a[1]
    d = min(abs(dx), abs(dy))
    sx, sy = math.copysign(d, dx), math.copysign(d, dy)
    return [(a[0] + sx, a[1] + sy), (c[0] - sx, c[1] - sy)]


def redraw(b, z, P, eps=0.1, res=0.05):
    """P redrawn along the boundaries the fill keeps to anyway: each run of corners whose
    region between the old run and one new edge (or two on 0/45/90, tried first) is
    `dontcare` save within eps of the old run (a raster-traced outline sits ON the free
    boundary) goes, greedily longest first. A same-net pad centre never changes side; a new
    edge never crosses the rest of the ring. So the fill is unchanged to within eps: the
    copper round obstacles and the board edge now shapes it, as when a designer draws it."""
    from kpcb_board import PolyIndex, pt_seg_dist
    from kpcb_smooth import octi
    g, ras = dontcare(b, z, res)
    lys = set(_lys(b, z))
    pads = [(p['x'], p['y']) for f in b.fps.values() for p in f.pads if p['net'] == z[0]
            and (p['drill'] or '*.Cu' in p['layers'] or lys & set(p['layers']))]
    W, n = g.W, len(P)

    def ok(chain, path, rest=()):                       # rest: the ring's other edges as they now stand
        if any(_cross(u, v, *e) for u, v in zip(path, path[1:]) for e in rest):
            return False
        idx = PolyIndex(chain + path[::-1][1:-1])
        if any(p in idx for p in pads):
            return False
        fb = idx.bbox
        for j in range(max(0, math.ceil((fb[1] - g.y0) / res)), min(g.H - 1, math.floor((fb[3] - g.y0) / res)) + 1):
            y = g.y0 + j * res
            for a0, a1 in g.spans(idx, y):
                i0, i1 = max(0, math.ceil((a0 - g.x0) / res)), min(W - 1, math.floor((a1 - g.x0) / res))
                i = ras.find(0, j * W + i0, j * W + i1 + 1) if i0 <= i1 else -1
                while i != -1:                          # a free point: only within eps of the old run
                    pt = (g.x0 + (i - j * W) * res, y)
                    if all(pt_seg_dist(pt, u, v) > eps for u, v in zip(chain, chain[1:])):
                        return False
                    i = ras.find(0, i + 1, j * W + i1 + 1)
        return True

    s = next((i for i in range(n) if not ok([P[i - 1], P[i], P[(i + 1) % n]], [P[i - 1], P[(i + 1) % n]])), 0)
    R = P[s:] + P[:s + 1]
    Q, i = [R[0]], 0
    while i < n:
        best, path = i + 1, [R[i], R[i + 1]]
        for k in range(i + 2, n + 1):
            if k - best > 8:                            # ponytail: 8-corner lookahead, not an optimal cover
                break
            rest = list(zip(Q, Q[1:])) + list(zip(R[k:], R[k + 1:]))
            for cand in [[R[i], kn, R[k]] for kn in _knees(R[i], R[k])] + [[R[i], R[k]]]:
                if ok(R[i:k + 1], cand, rest):
                    best, path = k, cand
                    break
        if len(path) == 2 and not octi(*path):          # an edge kept: on 0/45/90 if that holds
            rest = list(zip(Q, Q[1:])) + list(zip(R[best:], R[best + 1:]))
            path = next(([R[i], kn, R[best]] for kn in _knees(R[i], R[best])
                         if ok(R[i:best + 1], [R[i], kn, R[best]], rest)), path)
        Q += path[1:]
        i = best
    Q = clean(Q[:-1])
    return Q if len(Q) >= 3 and simple(Q) else P


def _cross(p, q, r, s):
    """pq and rs cross at a point inside both (touching ends do not)"""
    o = lambda a, b, c: (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])   # noqa: E731
    return o(r, s, p) * o(r, s, q) < -1e-12 and o(p, q, r) * o(p, q, s) < -1e-12


def _zones(b):
    return [z for z in b.zones if not z.keepout and len(z.outline) >= 3]


def _pick(b, key):
    m = [z for z in _zones(b) if z.uuid and z.uuid.startswith(key) or z.name == key]
    return m


def _pads_in(b, z, P):
    """same-net pads on the zone's layers whose centre is inside the outline"""
    return {f"{f.ref}.{p['num']}" for f in b.fps.values() for p in f.pads
            if p['net'] == z[0] and any(ly in z[1] or ly == '*.Cu' for ly in p['layers'])
            and inside((p['x'], p['y']), [P])}


def c_zoneshape(b, a):
    if not a.args:
        return _lint(b, a)
    zs = _pick(b, a.args[0])
    if len(zs) != 1:
        print(f"zoneshape: {a.args[0]!r} matches {len(zs)} zone(s)" + (': ' + ' '.join(
            f"{z.uuid[:8]}={z.name or z[0]}" for z in zs[:8]) if zs else '; `zoneshape` lists them')); return 1
    z = zs[0]
    eps = a.eps or 0.1
    P = z.outline
    Q, r = propose(P, eps, fit=(lambda Q: redraw(b, z, Q, eps)) if a.redraw else None)
    m0, m1 = metrics(P), metrics(Q)
    print(f"zoneshape {z.uuid[:8]} {z.name or ''} ({z[0]} {'/'.join(z[1])}, priority {z.priority}), eps {eps:g} mm"
          + (", redrawn along the copper and edges its fill keeps clear of (to within eps)" if a.redraw else ''))
    print(f"  vertices {m0[0]} -> {m1[0]}, off-45 edges {m0[1]} -> {m1[1]}, micro-edges {m0[2]} -> {m1[2]}, "
          f"faceted arcs {m0[3]} -> {m1[3]}" + (f"; corners now sharp + (smoothing fillet) {r:g}" if r else ''))
    dev = max(max(_ring_dist(q, P) for q in Q), max(_ring_dist(p, Q) for p in P))
    if len(Q) == len(P) and dev < 1e-3 and not r:
        print("  already clean: nothing to propose"); return 0
    print(f"  area {poly_area(P):.2f} -> {poly_area(Q):.2f} mm2, outline moved <= {dev:.3f} mm")
    lost = sorted(_pads_in(b, z, P) - _pads_in(b, z, Q))
    out = [q for q in Q if b.rings and not inside(q, b.rings)]
    was = [p for p in P if b.rings and not inside(p, b.rings)]
    bad = 0
    if lost:
        bad = 1; print(f"  LOST: {len(lost)} same-net pad(s) no longer inside: {' '.join(lost[:12])}")
    if len(out) > len(was):
        bad = 1; print(f"  OFF BOARD: {len(out) - len(was)} more vertex(es) outside the outline, e.g. "
                       f"{out[0][0]:.3f},{out[0][1]:.3f}")
    if not bad:
        print("  geometry ok: simple, every same-net pad it held still inside, on the board")
    if not a.out:
        print("(dry run: -o OUT writes it, refills scratch copies and checks the net's pieces; then `diff`)")
        return 2 if bad else 0
    if bad:
        print("  nothing written: fix the outline by hand or lower --eps"); return 2
    t = PcbText(b.path)
    s = t.text(z.uuid)
    pol = re.search(r'(\n\t\t\(polygon\n\t\t\t\(pts\n)(.*?)(\n\t\t\t\)\n\t\t\))', s, re.S)
    if not pol or '(arc' in pol[2]:
        print("  nothing written: the zone outline holds arcs or no polygon"); return 1
    s = s[:pol.start(2)] + ''.join(f"\t\t\t\t(xy {num(x)} {num(y)})\n" for x, y in Q).rstrip('\n') + s[pol.end(2):]
    if r:
        s = smooth_fill(s, r) or s
    s = re.sub(r'\n\t\t\(filled_polygon\n.*?\n\t\t\)', '', s, flags=re.S)
    t.sub(z.uuid, s)
    t.save(a.out)
    print(f"wrote {a.out} (this zone's fill dropped: refill in KiCad)")
    return _verify(b, a.out, z, a.redraw)


def _copper_mm2(b, net, lys, box, res=0.1):
    """mm2 of `net`'s saved fills (their union) on lys within box, sampled every res"""
    from kpcb_board import _pidx
    n = 0
    for ly in lys:
        fls = [_pidx(b, fl) for fl in b.fills if fl['net'] == net and fl['layer'] == ly
               and fl['bbox'][0] <= box[2] and fl['bbox'][2] >= box[0] and fl['bbox'][1] <= box[3] and fl['bbox'][3] >= box[1]]
        for j in range(int((box[3] - box[1]) / res) + 1):
            for i in range(int((box[2] - box[0]) / res) + 1):
                pt = (box[0] + i * res, box[1] + j * res)
                n += any(pt in f for f in fls)
    return n * res * res


def _verify(b, out, z, strict=False):
    """refill scratch copies of the input and OUT; the net's pieces must hold the same pads,
    and its copper round the zone (the union of its fills there) must stay within 1% / 0.5 mm2
    when `strict` (a redraw promises the same fill)"""
    from kpcb_board import bbox
    net, lys = z[0], _lys(b, z)
    bb = bbox(z.outline)
    box = (bb[0] - 1, bb[1] - 1, bb[2] + 1, bb[3] + 1)
    cli = kicad_cli(out)
    if not shutil.which(cli):
        print(f"  {cli} not found: refill and run `kpcb.py OUT net {net}` by hand"); return 0
    from kpcb_copper import Copper
    stem = os.path.splitext(b.path)[0]
    sig, mm2 = [], []
    with tempfile.TemporaryDirectory(prefix='kzs_') as d:
        for tag, src in (('in', b.path), ('out', out)):
            dst = os.path.join(d, tag + '.kicad_pcb')
            shutil.copy(src, dst)
            for ext in ('.kicad_pro', '.kicad_dru'):
                if os.path.exists(stem + ext):
                    shutil.copy(stem + ext, os.path.join(d, tag + ext))
            r = subprocess.run([cli, 'pcb', 'drc', '--refill-zones', '--save-board', '--format', 'json',
                                '-o', os.path.join(d, tag + '.json'), dst], capture_output=True, text=True)
            if r.returncode not in (0, 5) or not os.path.exists(dst):
                print(f"  refill failed ({cli}): {trunc((r.stderr or r.stdout).strip(), 160)}"); return 3
            bd = Board(dst)
            sig.append(sorted(sorted(p['pads']) for p in Copper(bd, net).pieces() if p['pads']))
            mm2.append(_copper_mm2(bd, net, lys, box))
    grew = mm2[1] - mm2[0]
    print(f"  refilled: {net} copper round the zone {mm2[0]:.2f} -> {mm2[1]:.2f} mm2 ({grew:+.2f})")
    if strict and abs(grew) > max(0.5, 0.01 * mm2[0]):
        print("  FILL CHANGED: the redraw crossed copper its clearance model missed; drop --redraw or check it in KiCad")
        return 2
    if sig[0] == sig[1]:
        print(f"  refilled: {net} keeps the same {len(sig[1])} piece(s) and pads")
        return 0
    main0 = set(max(sig[0], key=len, default=[]))
    main1 = set(max(sig[1], key=len, default=[]))
    print(f"  REFILL CHANGED {net}: {len(sig[0])} -> {len(sig[1])} piece(s); off the main piece now: "
          f"{' '.join(sorted(main0 - main1)[:12]) or '-'}; newly joined: {' '.join(sorted(main1 - main0)[:12]) or '-'}")
    return 2


def _lint(b, a):
    rows = []
    for z in _zones(b):
        m = metrics(z.outline)
        Q, _r = propose(z.outline, a.eps or 0.1)
        rows.append((m[0] - len(Q), m[1], z, m, len(Q)))
    rows.sort(key=lambda r: (-r[0], -r[1], r[2][0]))
    dirty = [r for r in rows if r[0] > 0 or r[3][1] or r[3][3]]
    over = sum(r[3][0] > 24 or r[3][2] >= 4 for r in rows)
    print(f"zoneshape: {len(rows)} zone(s), {len(dirty)} not hand-drawn style (few vertices on 0/45/90, sharp corners "
          f"+ fillet), {over} over a designer's bar (> 24 vertices or 4+ micro-edges); worst first. "
          f"`zoneshape UUID [--redraw]` proposes one")
    print(f"  {'uuid':<8}  {'net':<18} {'layer':<6} {'pts':>4} {'off45':>5} {'micro':>5} {'arcs':>4}  proposal")
    for drop, _o, z, m, n in dirty[:a.max]:
        print(f"  {z.uuid[:8]:<8}  {trunc(z[0], 18):<18} {'/'.join(z[1])[:6]:<6} {m[0]:>4} {m[1]:>5} {m[2]:>5} {m[3]:>4}  "
              + (f"{m[0]} -> {n} pts" if drop else 'off-45 kept (no 0/45/90 line within eps)')
              + (f"  [{trunc(z.name, 20)}]" if z.name else ''))
    if len(dirty) > a.max:
        print(f"  ... +{len(dirty) - a.max} more (--max)")
    return 0
