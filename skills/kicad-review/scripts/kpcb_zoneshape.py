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
compares the net's copper pieces: the same pads must stay joined. OUT itself is never a
kicad-cli save (a format bump); the refilled copies are deleted."""
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


def propose(P, eps=0.1):
    """(outline, fillet radius or None): unrounded, simplified, octilinear"""
    Q, r, _note = fillet_outline(P)
    Q = simplify(Q, eps)
    Q = clean(octilinear(Q, tol=eps / 2))
    return (Q, r) if len(Q) >= 3 and simple(Q) else (P, None)


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
    Q, r = propose(P, eps)
    m0, m1 = metrics(P), metrics(Q)
    print(f"zoneshape {z.uuid[:8]} {z.name or ''} ({z[0]} {'/'.join(z[1])}, priority {z.priority}), eps {eps:g} mm")
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
    return _verify(b, a.out, z[0])


def _verify(b, out, net):
    """refill scratch copies of the input and OUT; the net's pieces must hold the same pads"""
    cli = kicad_cli(out)
    if not shutil.which(cli):
        print(f"  {cli} not found: refill and run `kpcb.py OUT net {net}` by hand"); return 0
    from kpcb_copper import Copper
    stem = os.path.splitext(b.path)[0]
    sig = []
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
            sig.append(sorted(sorted(p['pads']) for p in Copper(Board(dst), net).pieces() if p['pads']))
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
          f"`zoneshape UUID` proposes one")
    print(f"  {'uuid':<8}  {'net':<18} {'layer':<6} {'pts':>4} {'off45':>5} {'micro':>5} {'arcs':>4}  proposal")
    for drop, _o, z, m, n in dirty[:a.max]:
        print(f"  {z.uuid[:8]:<8}  {trunc(z[0], 18):<18} {'/'.join(z[1])[:6]:<6} {m[0]:>4} {m[1]:>5} {m[2]:>5} {m[3]:>4}  "
              + (f"{m[0]} -> {n} pts" if drop else 'off-45 kept (no 0/45/90 line within eps)')
              + (f"  [{trunc(z.name, 20)}]" if z.name else ''))
    if len(dirty) > a.max:
        print(f"  ... +{len(dirty) - a.max} more (--max)")
    return 0
