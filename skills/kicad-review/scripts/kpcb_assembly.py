"""kpcb.py `assembly`: what fitting the parts by hand takes, from footprint geometry alone
(no package-name list: the two sessions that asked filtered by name and missed parts)."""
import math
from collections import Counter, defaultdict
from kcommon import natkey, refrange, trunc
from kpcb_board import _pidx, bbox, pad_box, solid

FINE = 0.5          # mm pitch: at or under it, bridging needs paste (or drag soldering and a microscope)
TINY = (1.05, 0.65)  # mm body: a two-terminal part this small with its land mostly under it (SOD-882,
                     # 0.75 under) has bottom-only terminals; an 0402 chip is 0.33-0.45 under
BIG, POUR = 4.0, 50.0   # mm2: a land this big joined to this much fill sinks an ordinary iron's heat
SIZES = ((0.8, '0201'), (1.25, '0402'), (1.8, '0603'), (2.3, '0805'), (3.5, '1206'))   # body's longer side, mm


def _cu(f):
    """the pads that take solder: copper, not a bare hole, a paste-only aperture or a thermal
    via (a plated hole numbered as an SMD pad of the part, the exposed pad's via array)"""
    ps = [p for p in f.pads if p['kind'] in ('smd', 'connect', 'thru_hole')
          and any(l.endswith('.Cu') for l in p['layers'])]
    smd = {p['num'] for p in ps if p['kind'] != 'thru_hole'}
    return [p for p in ps if p['kind'] != 'thru_hole' or p['num'] not in smd]


def _under(f, ps):
    """SMD pads no iron reaches: wholly inside the Fab body outline (not an edge-launch part's:
    its housing sits past the edge, the pins on top of their pads), more than half under a
    TINY two-terminal body (a leadless diode: its land runs past the body, its terminals do not),
    or (any footprint) surrounded by the other pads, as an exposed pad or an inner ball is"""
    n, fb = 0, f.fab if f.fab and not f.edgeref else None
    tiny = fb and len({p['num'] for p in ps}) == 2 and all(p['kind'] != 'thru_hole' for p in ps) \
        and max(fb[2] - fb[0], fb[3] - fb[1]) <= TINY[0] and min(fb[2] - fb[0], fb[3] - fb[1]) <= TINY[1]
    for p in ps:
        if p['kind'] == 'thru_hole':                    # soldered from the other side
            continue
        b = pad_box(p)
        if fb and min(b[0] - fb[0], b[1] - fb[1], fb[2] - b[2], fb[3] - b[3]) >= -0.02:
            n += 1
            continue
        if tiny:
            ins = max(0, min(b[2], fb[2]) - max(b[0], fb[0])) * max(0, min(b[3], fb[3]) - max(b[1], fb[1]))
            n += ins > 0.5 * (b[2] - b[0]) * (b[3] - b[1])
            continue
        o = [(q['x'], q['y']) for q in ps if q['num'] and q['num'] != p['num']]
        if len(o) > 1:
            x0, y0, x1, y1 = bbox(o)
            n += min(p['x'] - x0, x1 - p['x'], p['y'] - y0, y1 - p['y']) > 0.1
    return n


def _pitch(ps):
    """closest centre-to-centre distance between two separate lands of different pins
    (None for a two-terminal part: its spacing is its size)"""
    ps = [p for p in ps if p['num']]
    if len({p['num'] for p in ps}) < 3:
        return None
    bx = [pad_box(p) for p in ps]
    gap = lambda a, c: max(a[0] - c[2], c[0] - a[2], a[1] - c[3], c[1] - a[3])   # noqa: E731
    return min((math.dist((a['x'], a['y']), (c['x'], c['y'])) for i, a in enumerate(ps)
                for j, c in enumerate(ps[i + 1:], i + 1) if a['num'] != c['num'] and gap(bx[i], bx[j]) > 0),
               default=None)


def c_assembly(b, a):
    """Hand assembly: parts to fit per side, BOM lines, pads, body sizes, and the parts that
    need paste and reflow or hot air (a pad under the body, or pitch <= FINE), finest pitch first."""
    fit, dnp, nobom = [], [], []
    for f in b.fps.values():
        ps = _cu(f)
        if not ps:
            continue
        (dnp if f.dnp else nobom if 'exclude_from_bom' in f.attr else fit).append(f)
    if not fit:
        print("no part to fit: every footprint is DNP, excluded from the BOM or padless"); return 1
    back = sum(f.back for f in fit)
    pads = Counter('tht' if p['kind'] == 'thru_hole' else 'smd' for f in fit for p in _cu(f))
    print(f"assembly: {len(fit)} parts to fit, {len(fit) - back} front / {back} back, "
          f"{len({(f.lcsc or f.mpn or f.value, f.fp) for f in fit})} BOM lines; "
          f"{pads['smd']} SMD pads, {pads['tht']} through-hole")
    left = [f"DNP {len(dnp)}" + (f" ({trunc(refrange([f.ref for f in dnp]), 60)})" if dnp else ''),
            f"excluded from the BOM {len(nobom)}" + (f" ({trunc(refrange([f.ref for f in nobom]), 70)})" if nobom else '')]
    print("  not counted: " + '; '.join(left))
    size = Counter()
    for f in fit:
        L = max(f.fab[2] - f.fab[0], f.fab[3] - f.fab[1]) if f.fab else None
        size[next((n for m, n in SIZES if L <= m), 'larger') if L else 'no Fab outline'] += 1
    print("  body, longer side: " + ' | '.join(f"{n}-size {size[n]}" for _m, n in SIZES)
          + f" | larger {size['larger']}" + (f" | no Fab outline {size['no Fab outline']}" if size['no Fab outline'] else ''))
    tht = [f.ref for f in fit if any(p['kind'] == 'thru_hole' for p in _cu(f))]
    if tht:
        print(f"  through-hole ({len(tht)}): {trunc(refrange(tht), 90)}")
    groups = defaultdict(list)
    for f in fit:
        groups[(f.fp, f.back)].append(f)
    hard = []
    for (fp, bk), fl in groups.items():
        f = fl[0]
        ps = _cu(f)
        und, pit = _under(f, ps), _pitch(ps)
        fine = pit is not None and pit <= FINE + 0.005
        if not (und or fine):
            continue
        mn = min(min(bx[2] - bx[0], bx[3] - bx[1]) if p['prims'] else min(p['sx'], p['sy'])
                 for p, bx in ((p, pad_box(p)) for p in ps))
        hard.append((pit or 9, not und, mn, fp, bk, fl, und, len(ps)))
    if not hard:
        print(f"\nno pad under a body and no pitch <= {FINE:g} mm: an iron reaches every joint")
    else:
        hard.sort(key=lambda t: t[:3] + (natkey(t[5][0].ref),))
        n = sum(len(t[5]) for t in hard)
        print(f"\nneeds paste and reflow or hot air ({n} parts): a pad under the body (an iron cannot reach "
              f"it) or pitch <= {FINE:g} mm; finest pitch first")
        print(f"  {'refs':<24} side {'pitch':>5} {'min pad':>7} {'under':>6} {'body':>9}  footprint")
        for pit, _u, mn, fp, bk, fl, und, npads in hard:
            f = fl[0]
            body = f"{f.fab[2] - f.fab[0]:.1f}x{f.fab[3] - f.fab[1]:.1f}" if f.fab else '-'
            print(f"  {trunc(refrange([x.ref for x in fl]), 24):<24} {'B' if bk else 'F':<4} "
                  f"{f'{pit:.2f}' if pit < 9 else '-':>5} {mn:7.2f} {f'{und}/{npads}':>6} {body:>9}  {trunc(fp.split(':')[-1], 44)}")
        print(f"  the other {len(fit) - n}: no pad under the body, pitch > {FINE:g} mm. under = SMD pads inside the Fab "
              f"outline, ringed by other pads (an exposed pad), or more than half under a two-terminal body <= "
              f"{TINY[0]:g}x{TINY[1]:g} mm (bottom-only terminals); body '-' = no Fab outline, only the ring test")
    _sunk(b, [f for f in fit if f.ref not in {x.ref for t in hard for x in t[5]}])
    return 0


def _sunk(b, fit):
    """lands >= BIG mm2 joined to >= POUR mm2 of their net's saved fill (every layer they reach):
    the pour pulls the heat away, so an ordinary iron never wets them (parts already listed for
    reflow are left out: that list already says how they go on)"""
    fills = defaultdict(list)
    for fl in b.fills:
        fills[(fl['net'], fl['layer'])].append(fl)
    zones = defaultdict(list)
    for z in b.zones:
        for ly in z.layers:
            zones[(z.net, ly)].append(z)
    rows = []
    for f in fit:
        lands = defaultdict(list)                       # a number's pads together: an edge SMA's 2 is four
        for p in _cu(f):
            lands[p['num']].append(p)
        for num, ps in lands.items():
            got, land = {}, max(ps, key=lambda p: (lambda x: (x[2] - x[0]) * (x[3] - x[1]))(pad_box(p)))
            for p in ps:
                x0, y0, x1, y1 = pad_box(p)
                if (x1 - x0) * (y1 - y0) < BIG or not p['net']:
                    continue
                th = p['drill'] > 0 or any(l.startswith('*') for l in p['layers'])
                pts = [(x, y) for x in (x0, (x0 + x1) / 2, x1) for y in (y0, (y0 + y1) / 2, y1)]
                for ly in (b.copper if th else [l for l in p['layers'] if l in b.copper]):
                    z = max(zones[(p['net'], ly)], key=lambda z: z.priority, default=None)
                    if z is None or not solid(p, z):            # thermal spokes are the designed fix
                        continue
                    for fl in fills[(p['net'], ly)]:
                        if id(fl) not in got and any(_pidx(b, fl).touches(q, 0.05) for q in pts):
                            got[id(fl)] = fl['area']
            a = sum(got.values())
            if a >= POUR:
                rows.append((-a, natkey(f.ref), f"{f.ref}.{num}", f.back, pad_box(land), land['net'], a, len(got)))
    if not rows:
        return
    rows.sort(key=lambda r: r[:2])
    print(f"\nheat-sinked lands ({len(rows)}): >= {BIG:g} mm2 joined solid (no thermal spokes) to >= {POUR:g} mm2 "
          f"of pour; a high-power iron with a wide tip, or preheat the board; largest pour first")
    print(f"  {'pad':<10} side {'land':>9} {'pour mm2':>8} {'fills':>5}  net")
    for _a, _k, pad, bk, (x0, y0, x1, y1), net, a, nf in rows[:12]:
        print(f"  {pad:<10} {'B' if bk else 'F':<4} {f'{x1 - x0:.1f}x{y1 - y0:.1f}':>9} {a:8.0f} {nf:5d}  {trunc(net, 40)}")
    if len(rows) > 12:
        print(f"  ... {len(rows) - 12} more")
