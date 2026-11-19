"""kpcb.py `assembly`: what fitting the parts by hand takes, from footprint geometry alone
(no package-name list: the two sessions that asked filtered by name and missed parts)."""
import math
from collections import Counter, defaultdict
from kcommon import natkey, refrange, trunc
from kpcb_board import bbox, pad_box

FINE = 0.5          # mm pitch: at or under it, bridging needs paste (or drag soldering and a microscope)
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
    its housing sits past the edge, the pins on top of their pads), or (any footprint)
    surrounded by the other pads, as an exposed pad or an inner ball is"""
    n = 0
    for p in ps:
        if p['kind'] == 'thru_hole':                    # soldered from the other side
            continue
        b = pad_box(p)
        if f.fab and not f.edgeref and min(b[0] - f.fab[0], b[1] - f.fab[1], f.fab[2] - b[2], f.fab[3] - b[3]) >= -0.02:
            n += 1
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
        return 0
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
          f"outline or ringed by other pads (an exposed pad); body '-' = no Fab outline, only that second test")
    return 0
