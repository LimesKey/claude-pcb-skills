"""kpcb.py `tracks`, `widen` and `loops`: the quality of routed copper, and two clean-ups.

`tracks [--kind K] [--view OUT.png]` is a census of what a reviewer sees: corners of 46-90
deg and acute ones at nodes of two same-net tracks, off-45 segments (octi: > 0.3 deg or a far end
> 10 um off the line), width steps mid-run, segments under 0.05 mm, dead-end traces that stop
at a pad edge instead of its centre (`smooth --pads`), signal ends inside a small pad off its
anchor (by hand), ends joined only by their caps (`smooth --joints`), two runs joined only
through a pad's copper (`smooth --overlaps`), two
same-net runs side by side into one pad (`smooth --twins`), plane-net (GND) tracks lying wholly inside their own saved fill (`ripup
--inpour` deletes them). Each is dropped when it is hidden under the UNION of other same-net
copper (pads, vias, wider tracks, fills), a corner also when one leg lies wholly in the other's cap. Listed rows say why `smooth` left them: on a pad
or via (an anchor), a width step (`smooth --corners` takes it), a T, a frozen leg (arc,
locked), boxed in (no clear cut at the real clearance), or `fix` (a pass would take it).

`widen [NET...] [--width W] -o OUT` grows under-width tracks to the widest legal step up to
their target: a power netclass's track width (PWR_*), the net's class width for GND, W
(0.2) for signals. Clearance as `smooth`: route's typed Grid, Exact where it refuses. Power
classes >= 1 mm go per segment (resistance first) and skip legs under 0.5 mm (sense); the
rest take one width per run so a run does not alternate. Capped at an SMD pad's narrow side;
never a new same-net contact (Kelvin legs keep one); skipped: tracks inside a same-net
fill, switch nodes (EMI area), inner tracks within 2 mm of RF traces (their plane), RF/USB/
diff nets. Sequential: each accepted width is in the model before the next is priced.
--uniform: any other net's segment narrower than its neighbours (each end a plain two-track
node or a via, never a pad: not a fine-pitch neck) takes the narrowest neighbour's width
where that clears - a 0.1 mm sliver inside a 0.3 run the census hides.

`loops [NET...] [-o OUT]` finds redundant track chains on signal nets: greedily, the
longest chain whose removal - with ripup's prune of what that leaves dangling and of vias
joining < 2 layers - leaves the net's pad partition unchanged, both as KiCad joins copper
and on STRICT joins (an end cap wholly inside the pad or via, a real T): a pad entry whose
neighbour's cap merely grazes the pad is not redundant, and a pad already hanging by a
graze is not a licence to remove its whole path. Power, GND and poured nets
are skipped (parallel copper is lower R). -o deletes them and their teardrops; verify with
`kdrc.py OUT drc --refill-save --baseline BEFORE.json` (0 new unconnected)."""
import math, re
from collections import defaultdict, Counter
from kcommon import unesc_disp, rail_voltage
from kpcb_board import PolyIndex, bbox, hit, poly_area, pt_seg_dist, seg_seg_dist
from kpcb_route import Grid, _netclass, piece_parts
from kpcb_move import via_layers, is_arc
from kpcb_edit import PcbText, tear_edits, num, prune, _rip_out
from kpcb_copper import pad_dist
from kpcb_smooth import (Index, Exact, chains, covered, leg_in_cap, cap_rounds, cut_corner, skipped, in_pad, on_layer, octi, ang, turn,
                         q, RES, GRAZE, pad_ends, pad_joins, twins, no_project, cap_joints, close_joint)


# ---------------------------------------------------------------- tracks (census)

def in_pour(b, nets=None, box=None, every=False):
    """[track idx] lying wholly inside a saved fill of their own net on their layer - centreline,
    both edges and the end caps, every 0.1 mm: copper the pour already is. Plane nets only
    (route's _planes: GND, or a net pouring > 20% of the board) unless `every` (any poured net:
    a power path relying on its fill alone is opt-in, per net). No neck test is needed: fill
    holding the whole track is at least the track's width across it everywhere, and a same-net
    track does not shape the refill. Fragments under 4 mm2 don't count (a pad's thermal patch,
    or an island the track itself keeps alive). Read from the fill on disk: refill first, or a
    track the pour has since been cut away from reads as covered."""
    from kpcb_route import _planes, _pidx
    planes, by = _planes(b), defaultdict(list)
    for fl in b.fills:
        if (every or (fl['net'], fl['layer']) in planes) and (not nets or fl['net'] in nets) and fl['area'] >= 4:
            by[(fl['net'], fl['layer'])].append(fl)
    out = []
    for i, t in enumerate(b.tracks):
        fls = by.get((t['net'], t['layer']))
        if not fls or t['locked'] or t['len'] < 1e-4 or is_arc(t) or \
                box and not any(box[0] <= x <= box[2] and box[1] <= y <= box[3] for x, y in (t['a'], t['b'])):
            continue
        hw, L = t['w'] / 2, t['len']
        ux, uy = (t['b'][0] - t['a'][0]) / L, (t['b'][1] - t['a'][1]) / L
        n = max(1, math.ceil(L / 0.1))
        pts = [(t['a'][0] + ux * L * k / n - uy * o, t['a'][1] + uy * L * k / n + ux * o)
               for k in range(n + 1) for o in (-hw, 0.0, hw)]
        pts += [(t['a'][0] - ux * hw, t['a'][1] - uy * hw), (t['b'][0] + ux * hw, t['b'][1] + uy * hw)]
        fls = [fl for fl in fls if fl['bbox'][0] <= min(x for x, _ in pts) and fl['bbox'][2] >= max(x for x, _ in pts)
               and fl['bbox'][1] <= min(y for _, y in pts) and fl['bbox'][3] >= max(y for _, y in pts)]
        if fls and all(any(p in _pidx(b, fl) for fl in fls) for p in pts):
            out.append(i)
    return out


# ---------------------------------------------------------------- do-nothing copper

NOTHING = (('dead', 'dead branches', 'ripup --deadend'), ('passvia', 'pass-through vias', 'ripup --deadend'),
           ('micro', 'segments < 0.05 mm', 'smooth --micro'), ('inpour', 'plane tracks in fill', 'ripup --inpour'),
           ('inpourpwr', 'other tracks in fill', 'ripup NET --inpour (opt-in)'))


def donothing(b, nets=None):
    """the do-nothing copper census: {kind: {key: (net, desc, [uuid])}} - 'dead' a branch serving
    no pad (kpcb_copper.dead_copper), 'passvia' one that is vias only (joined on < 2 layers),
    'micro' a segment under 0.05 mm, 'inpour' a plane track inside its fill, 'inpourpwr' another
    net's. Keys are uuids (a branch: all of its own), so two boards' censuses compare by key.
    nets: only these (a writer's touched nets)"""
    from kpcb_copper import dead_all, dead_desc, MICRO
    from kpcb_route import _planes
    out = {k: {} for k, _l, _c in NOTHING}
    for net, ds in dead_all(b, sorted(nets) if nets is not None else None).items():
        for d in ds:
            u = [t['uuid'] for t, *_r in d['tracks']] + [v['uuid'] for v in d['vias']] + \
                sorted({fl['zone'] for fl in d['fills'] if fl.get('zone')})
            kind = 'passvia' if d['vias'] and not d['tracks'] and not d['fills'] else 'dead'
            out[kind][frozenset(u)] = (net, dead_desc(d), u)
    for t in b.tracks:
        if t['len'] < MICRO and t['net'] and not is_arc(t) and (nets is None or t['net'] in nets):
            out['micro'][t['uuid']] = (t['net'], f"{t['layer']} {t['len'] * 1000:.0f} um @{t['a'][0]:.2f},{t['a'][1]:.2f}",
                                       [t['uuid']])
    planes = {n for n, _l in _planes(b)}
    for i in in_pour(b, nets, every=True):
        t = b.tracks[i]
        out['inpour' if t['net'] in planes else 'inpourpwr'][t['uuid']] = (
            t['net'], f"{t['layer']} {t['len']:.2f} mm w{t['w']:g} @{t['mid'][0]:.2f},{t['mid'][1]:.2f}", [t['uuid']])
    return out


def nothing_line(c):
    """one totals line for `review`"""
    return ', '.join(f"{len(c[k])} {lab}" for k, lab, _c in NOTHING)


def nothing_delta(old, new, nets=None):
    """[(kind, label, fix, [(net, desc, uuids)] added, n removed)] between two boards, on `nets`:
    added = none of its uuids was do-nothing copper of any kind before (a dead branch that only
    lost a micro segment is not new)"""
    a, z = donothing(old, nets), donothing(new, nets)
    was = {u for k in a for v in a[k].values() for u in v[2]}     # anything already do-nothing before
    now = {u for k in z for v in z[k].values() for u in v[2]}
    return [(k, lab, fix, [v for v in z[k].values() if not was & set(v[2])],
             sum(1 for v in a[k].values() if not now & set(v[2]))) for k, lab, fix in NOTHING]


def touched_nets(old, new):
    """nets whose tracks or vias differ (by uuid and geometry) between two boards"""
    key = lambda o: (o['uuid'], o['net'], o.get('layer'), o.get('a'), o.get('b'), o.get('w'), o.get('x'), o.get('y'))  # noqa: E731
    A, Z = {key(o) for o in old.tracks + old.vias}, {key(o) for o in new.tracks + new.vias}
    return {k[1] for k in A ^ Z if k[1]}


PRUNE = {'smooth', 'widen', 'loops', 'reroute', 'ripup', 'unhook'}   # writers whose new dead copper is a side effect


def gate(b, out, cmd):
    """after an -o writer: the do-nothing census on the nets it touched, before vs after. New
    dead branches and pass-through vias are pruned from OUT when the writer is a clean-up pass
    (PRUNE: there they are a side effect), else named with the call that takes them (a hand
    `edit seg` lays a route one piece at a time); new micro segments and in-pour tracks are named"""
    from kpcb_board import Board
    nb = Board(out)
    nets = touched_nets(b, nb)
    if not nets:
        return
    rows = [r for r in nothing_delta(b, nb, nets) if r[3]]
    if not rows:
        return
    print(f"do-nothing copper this edit added, on the {len(nets)} net(s) it touched:")
    kill = set()
    for k, lab, fix, added, _gone in rows:
        auto = k in ('dead', 'passvia') and cmd in PRUNE
        print(f"  +{len(added)} {lab}" + (' (pruned from OUT)' if auto else f" - `{fix}`"))
        for net, desc, u in added[:6]:
            print(f"    {unesc_disp(net):<24} {desc}  {' '.join(x[:8] for x in u[:8])}")
        if auto:
            kill |= {x for _n, _d, u in added for x in u}
    if kill:
        from kpcb_copper import dead_copper
        whole = {o['uuid'] for n in nets for d in dead_copper(nb, n) for o in
                 [t for t, _L, kp in d['tracks'] if kp is None] + d['vias']} & kill
        t = PcbText(out)
        trk = [x for x in nb.tracks if x['uuid'] in whole]
        for u in whole:
            if u in t.span:
                t.sub(u, '')
        tear_edits(t, trk)
        t.save(out, inplace=True)                    # OUT is this run's own output, not the input board
        print(f"  pruned {len(whole)} track(s)/via(s) from {out}")


SMALL_PAD = 1.5                                      # a pad this long or less wants its trace ends on the anchor


def anchor_ends(b, ix, skip):
    """[(offset, track idx, end, 'REF.PIN')], largest first: a signal trace's dead end (no other
    track end there, not on a via) inside a pad <= SMALL_PAD across (custom primitives counted),
    >= 10 um off its anchor and deeper in than a `pad` row's graze. KiCad joins it as laid; a
    designer lands every end on the anchor (Q11-G 45 um off U8.24, an SDA spur 0.45 mm off D29.3,
    reference board). A bend vertex inside the pad (two tracks meet) is the route going on, not an end."""
    from kpcb_route import _planes
    planes = {n for n, _l in _planes(b)}
    lab = {id(p): f"{f.ref}.{p['num']}" for f in b.fps.values() for p in f.pads}

    def size(p):
        us = [-p['sx'] / 2, p['sx'] / 2] + [u for poly in p['prims'] for u, _v in poly]
        vs = [-p['sy'] / 2, p['sy'] / 2] + [v for poly in p['prims'] for _u, v in poly]
        return max(max(us) - min(us), max(vs) - min(vs))
    out = []
    for i, t in enumerate(b.tracks):
        net = t['net']
        if not net or net in skip or net in planes or is_arc(t) or t['len'] < 1e-4 or \
                'PWR' in (b.netclass(net) or '').upper() or rail_voltage(net.split('/')[-1]) is not None:
            continue
        for E in (t['a'], t['b']):
            if len(ix.ends[(net, t['layer'], q(E))]) != 1 or ix.on_via(net, t['layer'], E):
                continue
            p = next((p for p in ix.pads[net] if on_layer(p, t['layer']) and pad_dist(p, E, True) <= -GRAZE
                      and size(p) <= SMALL_PAD), None)
            if p is not None and math.dist(E, (p['x'], p['y'])) >= 0.01:
                out.append((math.dist(E, (p['x'], p['y'])), i, E, lab[id(p)]))
    return sorted(out, key=lambda r: -r[0])


def census_rows(b, skip, box=None, kinds=None):
    """(Counter, rows): rows (kind, net, layer, xy, detail, why, (node, i1, i2) | None);
    box: only nodes, segments and rows inside X0,Y0,X1,Y1; kinds: only the passes those need run
    (`--kind cleanup` skips the corner, jog and pad passes: 12 -> 5 s on the reference board), so
    the other kinds' counts are partial"""
    ix = Index(b)
    c, rows = Counter(), []
    want = lambda *ks: kinds is None or not kinds.isdisjoint(ks)   # noqa: E731
    far = lambda t, n: t['b'] if q(t['a']) == n else t['a']    # noqa: E731
    inb = lambda p: not box or (box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3])   # noqa: E731
    for (net, ly, n), lst in ix.ends.items() if want('acute', '90', 'neck') else ():
        if net in skip or len(lst) != 2 or not inb(n):
            continue
        t1, t2 = b.tracks[lst[0]], b.tracks[lst[1]]
        if t1['len'] < 1e-4 or t2['len'] < 1e-4:
            continue
        w = max(t1['w'], t2['w'])
        onp, onv = ix.on_pad(net, ly, n, w / 2), ix.on_via(net, ly, n, w / 2)
        th = turn(ang(far(t1, n), n), ang(n, far(t2, n)))
        k = None if th < 46 else '90' if th < 91 else 'acute'
        if k and (covered(b, ix, net, ly, n, w, set(lst)) or leg_in_cap(t1, t2) or leg_in_cap(t2, t1)
                  or cap_rounds(t1, t2, th)):
            c['hidden ' + k] += 1
            k = None
        tee = any(i not in lst and pt_seg_dist(n, b.tracks[i]['a'], b.tracks[i]['b']) <= b.tracks[i]['w'] / 2
                  for i in ix.trk[(net, ly)])
        why = 'pad' if onp else 'via' if onv else 'T' if tee else \
            'frozen' if any(is_arc(t) or t['locked'] for t in (t1, t2)) else \
            'width step' if abs(t1['w'] - t2['w']) > 1e-3 else ''
        if k:
            c[k] += 1
            rows.append((k, net, ly, n, f"{th:.0f} deg", why, (n, lst[0], lst[1])))
        if abs(t1['w'] - t2['w']) > 1e-3 and not onp and not onv:
            c['neck'] += 1
            rows.append(('neck', net, ly, n, f"{t1['w']:g} -> {t2['w']:g} mm", 'T' if tee else '', None))
    for i, t in enumerate(b.tracks):
        if not t['net'] or t['net'] in skip or t['len'] < 1e-4 or not inb(t['mid']):
            continue
        if is_arc(t):
            c['arc'] += 1
            continue
        c['segs'] += 1
        c['mm'] += t['len']
        if want('off45') and not octi(t['a'], t['b']):
            if covered(b, ix, t['net'], t['layer'], t['mid'], t['w'], {i}):
                c['hidden off45'] += 1
            else:
                c['off45'] += 1
                pe = any(ix.on_pad(t['net'], t['layer'], e) for e in (t['a'], t['b']))
                ve = any(ix.on_via(t['net'], t['layer'], e, t['w'] / 2) for e in (t['a'], t['b']))
                r = ang(t['a'], t['b']) % 180
                dv = min(r % 45, 45 - r % 45)              # under 0.3 deg: off by its drift (octi)
                rows.append(('off45', t['net'], t['layer'], t['mid'], f"{t['len']:.2f} mm at {r:.0f} deg" if dv >= 0.3 else
                             f"{t['len']:.2f} mm, end {t['len'] * math.sin(math.radians(dv)) * 1000:.0f} um off "
                             f"{45 * round(r / 45) % 180} deg", 'pad end (smooth --square)' if pe else 'via end' if ve else '', None))
        if want('stub') and t['len'] < 0.05:
            if covered(b, ix, t['net'], t['layer'], t['mid'], t['w'], {i}):
                c['hidden stub'] += 1
            else:
                c['stub'] += 1
                rows.append(('stub', t['net'], t['layer'], t['mid'], f"{t['len'] * 1000:.0f} um", 'smooth --micro', None))
    for i, E, lab, p in pad_ends(b, ix, skip, inside=True) if want('pad') else ():
        if not inb(E):
            continue
        if pad_dist(p, E, True) <= -GRAZE:
            c['inside pad'] += 1                    # well inside, off centre: fine as laid
            continue
        c['pad'] += 1
        rows.append(('pad', b.tracks[i]['net'], b.tracks[i]['layer'], E,
                     f"{math.dist(E, (p['x'], p['y'])):.2f} mm off {lab}", 'fix: smooth --pads', None))
    for off, i, E, lab in anchor_ends(b, ix, skip) if want('anchor') else ():
        if inb(E):
            c['anchor'] += 1
            rows.append(('anchor', b.tracks[i]['net'], b.tracks[i]['layer'], E, f"{off * 1000:.0f} um off {lab}",
                         'by hand (KiCad joins it as laid)', None))
    for gap, i, E, j, E2 in sorted(cap_joints(b, ix, skip) if want('joint') else (), key=lambda r: -r[0]):
        t = b.tracks[i]
        if not inb(E):
            continue
        if covered(b, ix, t['net'], t['layer'], E, t['w'], {i, j}):
            c['hidden joint'] += 1
            continue
        c['joint'] += 1
        rows.append(('joint', t['net'], t['layer'], E, f"{gap * 1000:.0f} um {'end to end' if E2 else 'off the T axis'}",
                     '', (gap, i, E, j, E2)))
    from kpcb_jogs import find
    chs = chains(b, skip, ix) if want('jog', 'overlap', 'twin') else []   # jogs, overlaps, twins walk the same chains
    for jog in find(b, skip, every=True, chs=chs) if want('jog') else ():
        if not inb(jog[4][jog[5]]):
            continue
        c['jog'] += 1
        rows.append(('jog', jog[0], jog[1], jog[4][jog[5]], f"{jog[6]:.2f} mm sideways", '', jog[:6]))
    for net, ly, lab, p, A, B, brg in pad_joins(b, skip, ix, chs) if want('overlap') else ():
        if inb((p['x'], p['y'])):
            c['overlap'] += 1
            rows.append(('overlap', net, ly, (p['x'], p['y']), f"two runs only through {lab}"
                         + (f" (+{len(brg)} bridge)" if brg else ''), 'smooth --overlaps', None))
    for net, ly, lab, far, near, par, mid in twins(b, skip, ix, chs) if want('twin') else ():
        if inb(mid):
            c['twin'] += 1
            rows.append(('twin', net, ly, mid, f"{par:.1f} mm beside its twin into {lab}", 'smooth --twins', None))
    from kpcb_route import _planes
    planes = {n for n, _l in _planes(b)}
    inp = set()                                      # deadend reads it: a branch wholly in fill is an inpour row
    for i in in_pour(b, box=box, every=True) if want('inpour', 'inpourpwr', 'deadend') else ():
        t = b.tracks[i]
        if t['net'] in skip:
            continue
        k = 'inpour' if t['net'] in planes else 'inpourpwr'
        if k == 'inpour':
            inp.add(id(t))
        c[k] += 1
        rows.append((k, t['net'], t['layer'], t['mid'], f"{t['len']:.2f} mm w{t['w']:g}", 'ripup --inpour' if k == 'inpour'
                     else f"ripup {unesc_disp(t['net'].split('/')[-1])} --inpour (opt-in: may it rely on its fill?)", None))
    from kpcb_copper import dead_all, dead_desc
    dead = set()                                     # what KiCad's dangling pass deletes: wholly dead tracks, vias
    for net, ds in dead_all(b).items() if want('deadend', 'cleanup') else ():
        rf = 'RF' in (b.netclass(net) or '').upper()
        for d in ds if net not in skip else ():
            dead |= {id(t) for t, _mm, keep in d['tracks'] if keep is None} | {id(v) for v in d['vias']}
            if d['tracks'] and all(id(t) in inp for t, *_r in d['tracks']):   # wholly in fill: its inpour row says it
                continue
            at = d['at'] or (d['tracks'][0][0]['mid'] if d['tracks'] else (d['vias'][0]['x'], d['vias'][0]['y']) if d['vias']
                             else d['fills'][0]['pts'][0])
            if inb(at):
                c['deadend'] += 1
                rows.append(('deadend', net, (d['layers'] or ['-'])[0], at, dead_desc(d).split(' off ')[0],
                             'INFO: an RF stub (matching?)' if rf else 'off ' + d['off'].split(' @')[0] + '; ripup --deadend', d))
    for k, z, desc, fix in zone_rows(b) if want('zonepts', 'zonedup') else ():
        bb = bbox(z.outline)
        at = ((bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2)
        if inb(at):
            c[k] += 1
            rows.append((k, z[0], ','.join(z[1]), at, desc, fix, None))
    from kpcb_dense import detours
    for _x, net, L, M, V, n, ly in detours(b, skip) if want('detour') else ():
        c['detour'] += 1
        at = next(((p['x'], p['y']) for f in b.placed() for p in f.pads if p['net'] == net), (0.0, 0.0))
        if not inb(at):
            continue
        rows.append(('detour', net, ly, at, f"{L:.1f} vs MST {M:.1f} mm, {V} via", 'reroute ' + unesc_disp(net.split('/')[-1]), None))
    for r in cleanup_rows(b, ix, skip, dead) if want('cleanup') else ():
        if inb(r[3]):
            c['cleanup'] += 1
            rows.append(r)
    return c, rows


NM = 1e6                                             # KiCad's internal unit, per mm


def _nm(p):
    return round(p[0] * NM), round(p[1] * NM)


def _collinear(t1, t2):
    """SEG::ApproxCollinear at its 1 nm default: both ends of the shorter segment within 1 nm
    of the longer one's line, in KiCad's integer nm (rescale rounds: det^2 / l < 1.5)"""
    a, c = (t1, t2) if t1['len'] >= t2['len'] else (t2, t1)
    (ax, ay), (bx, by) = _nm(a['a']), _nm(a['b'])
    p, r = ay - by, bx - ax
    k, L = -p * ax - r * ay, p * p + r * r
    return L > 0 and all(2 * (p * x + r * y + k) ** 2 < 3 * L for x, y in (_nm(c['a']), _nm(c['b'])))


def kicad_takes(b, d):
    """'' when KiCad's Cleanup dangling pass ("Delete tracks unconnected at one end", "vias
    connected on only one layer") takes exactly dead branch d, else what it takes instead:
    it stops where every end joins something (a pour, a cycle), deletes a track it would need
    to cut back whole, and takes what that leaves - an attach stub lying in what it hung off
    (ripup's prune, run over d as it lies: the reference board's +BATT and -BATT rows matched
    the 10.99 GUI item for item, 2026-11-13)"""
    from kpcb_edit import prune
    row = [('t', t) for t, _mm, keep in d['tracks'] if keep is None] + [('v', v) for v in d['vias']]
    cuts = [t for t, _mm, keep in d['tracks'] if keep is not None]
    k = prune(b, set(), test=row + [('t', t) for t in cuts])
    took, cut = sum(id(o) in k for _k, o in row), [t for t in cuts if id(t) in k]
    mine = {id(o) for _k, o in row} | {id(t) for t in cuts}
    extra = [o for o in b.tracks + b.vias if id(o) in k and id(o) not in mine]
    if took == len(row) and not cut and not extra:
        return ''
    parts = [('all of it' if took == len(row) else
              "none of it (every end of it joins something)" if not took else
              f"{took} of its {len(row)}" + (' (its pour holds the rest)' if d['fills'] else ''))] if row else []
    parts += [f"{' '.join(t['uuid'][:8] for t in cut)} whole (it cannot cut a track back)"] if cut else []
    parts += [f"{len(extra)} more it then leaves dangling: {' '.join(o['uuid'][:8] for o in extra[:8])}"] if extra else []
    return ("KiCad's Cleanup takes " + ', '.join(parts[:-1]) + (' and ' if len(parts) > 1 else '') + parts[-1]
            + ('; ripup --deadend takes it all' if took < len(row) else ''))


def cleanup_rows(b, ix, skip, dead=frozenset()):
    """what KiCad's Tools -> Cleanup Tracks & Vias would change, predicted from
    pcbnew/tracks_cleaner.cpp (10.99 g8304096633, checked in the GUI 2026-11-13: it cannot run
    headless, `api-server` answers RunAction with "not available in headless mode"; stable's SWIG
    pcbnew has no cleaner). Each row names its dialog option; all are on by default except
    "Delete tracks fully inside pads" (the dialog remembers its last ticks).
    Merge co-linear tracks: two plain same-width segments, neither locked, the shorter's ends
    within 1 nm of the longer's line, merge when every one of the four ends that something
    else in the net holds is an end of the merged segment (KiCad's min/max box of the four, exact
    in nm), and <= 2 such ends: so the joint holds nothing. testMergeCollinearSegments asks the
    whole net island on every layer: another track's or arc's END exactly there, a via centred
    there, a same-net pad on ANY layer within w/2 (PAD::HitTest checks its whole padstack), a
    same-net zone or teardrop OUTLINE within max(w/2, 0.1 mm), a corner within twice that
    (ZONE::HitTest: the outline, never the fill). Teardrops hug the pad and via entries, so a
    joint near one does not merge: on the reference board they held all 22 joints that merge
    once every zone is gone. A track crossing the joint mid-span or ending near it does not hold
    it. A segment with ANY different-width trace touching it (either end, a T into its side)
    never starts a merge, so a pair where one side necks merges or not by KiCad's pair order
    (object addresses): "may"; so does a pair whose two possible merged boxes differ (a
    sub-um leg). It merges again after the dangling pass, so a joint held only by dead copper
    (`dead`: ids of the deadend rows' tracks and vias) counts. Zero-length segments go first.
    Redundant vias: two at one point with the same layers (one goes), a via over a through-hole
    pad (a via met on one layer only is a deadend row: dead_copper drops its spoke). Tracks fully
    inside pads: both end caps in one same-net pad (an end pushed to the pad centre on a new
    segment comes back off: land it on the anchor in line). Duplicate segment: same ends, width,
    layer (one goes unless both are locked). Not modelled: a pour whose fill is a separate island
    from the joint (counted as holding), overlapping collinear pairs that touch but share no end,
    dangling cycles KiCad keeps (dead_all counts them)."""
    out, at_k = [], defaultdict(list)
    lab = {id(p): f"{f.ref}.{p['num']}" for f in b.fps.values() for p in f.pads}
    gone = set(dead)
    for v in b.vias:
        if v['net'] and v['net'] not in skip:          # redundant vias go before the dangling pass
            at_k[(round(v['x'], 4), round(v['y'], 4), tuple(sorted(v['layers'])))].append(v)
    for g in at_k.values():                          # each unlocked via meeting another goes: the last one
        free = [v for v in g if not v['locked']]     # survives, unless a locked twin outlives them all
        for i, v in enumerate(free):
            at = (v['x'], v['y'])
            p = next((p for p in ix.pads[v['net']] if p['drill'] and pad_dist(p, at, True) <= v['size'] / 2), None)
            if len(g) > 1 and (i < len(free) - 1 or len(free) < len(g)):
                out.append(('cleanup', v['net'], '-', at, 'duplicate via', 'KiCad deletes one (redundant vias)', None))
            elif p is not None:
                out.append(('cleanup', v['net'], '-', at, f"via on through-hole {lab[id(p)]}", 'KiCad deletes it (redundant vias)', None))
            else:
                continue
            gone.add(id(v))

    def plain(t):
        return not is_arc(t) and id(t) not in gone

    def necks(i):
        t, W = b.tracks[i], round(b.tracks[i]['w'] * NM)
        return any(j != i and plain(o := b.tracks[j]) and round(o['w'] * NM) != W
                   and seg_seg_dist(t['a'], t['b'], o['a'], o['b']) <= (t['w'] + o['w']) / 2 for j in ix.trk[(t['net'], t['layer'])])

    at_nm, ends_nm = defaultdict(list), defaultdict(list)     # exact nm ends: per net, per (net, layer)
    for i, t in enumerate(b.tracks):
        if not t['net'] or t['net'] in skip:
            continue
        if _nm(t['a']) == _nm(t['b']):
            if not is_arc(t) and not t['locked']:
                out.append(('cleanup', t['net'], t['layer'], t['a'], 'zero-length segment', 'KiCad deletes it', None))
            gone.add(id(t))
            continue
        for e in (t['a'], t['b']):
            at_nm[(t['net'], _nm(e))].append(i)
            ends_nm[(t['net'], t['layer'], _nm(e))].append(i)
    filled = {zu for _n, _f, zu in b._fill_nodes}
    outl = defaultdict(list)                       # the net's pour and teardrop outlines, boxed
    for o, net in [(z.outline, z[0]) for z in b.zones if not z.keepout and z.uuid in filled] + \
            [(td[3], td[0]) for td in b.teardrops]:
        if net and len(o) > 2:
            outl[net].append((bbox(o), o))

    def on_outline(net, e, w):                     # ZONE::HitTest(pos, (w + 1) / 2)
        a = max(w / 2, 0.1)
        return any(x0 - 2 * a <= e[0] <= x1 + 2 * a and y0 - 2 * a <= e[1] <= y1 + 2 * a
                   and (any(math.dist(e, v) <= 2 * a for v in o) or any(pt_seg_dist(e, o[k - 1], o[k]) <= a for k in range(len(o))))
                   for (x0, y0, x1, y1), o in outl[net])

    def held(net, e, w, pair):                     # IsPointOnEnds (exact) or HitTest, any layer
        k = _nm(e)
        return any(i not in pair and id(b.tracks[i]) not in gone for i in at_nm[(net, k)]) or \
            any(id(v) not in gone and _nm((v['x'], v['y'])) == k for v in ix.vias[net]) or \
            any(in_pad(p, e, w / 2) for p in ix.pads[net]) or on_outline(net, e, w)

    def box_ok(s1, ends, hold):                    # the merged segment KiCad builds from s1's slope
        xs, ys = [e[0] for e in ends], [e[1] for e in ends]
        (ax, ay), (bx, by) = s1
        ab = ((min(xs), min(ys)), (max(xs), max(ys))) if (ax > bx) == (ay > by) else ((min(xs), max(ys)), (max(xs), min(ys)))
        return all(e in ab for e in hold)

    for (net, ly, n), lst in ends_nm.items():
        live = [i for i in lst if id(b.tracks[i]) not in gone]
        if len(live) != 2:
            continue
        t1, t2 = b.tracks[live[0]], b.tracks[live[1]]
        if not (plain(t1) and plain(t2)) or t1['locked'] or t2['locked'] or round(t1['w'] * NM) != round(t2['w'] * NM) \
                or not _collinear(t1, t2):
            continue
        ends = [_nm(e) for e in (t1['a'], t1['b'], t2['a'], t2['b'])]
        hold = [k for k, e in zip(ends, (t1['a'], t1['b'], t2['a'], t2['b'])) if held(net, e, t1['w'], live)]
        if len(hold) > 2:
            continue
        ok = [box_ok((_nm(t['a']), _nm(t['b'])), ends, hold) for t in (t1, t2)]
        if not any(ok):
            continue
        n1, n2 = necks(live[0]), necks(live[1])
        if n1 and n2:
            continue
        freed = len(lst) > 2 or any(_nm((v['x'], v['y'])) == n for v in ix.vias[net] if id(v) in gone)
        may = n1 or n2 or not all(ok)
        out.append(('cleanup', net, ly, (n[0] / NM, n[1] / NM), 'collinear joint' + (' after the dangling pass' if freed else '')
                    + (', one side necks' if n1 or n2 else '') + (', sub-um leg' if not all(ok) else ''),
                    'KiCad may merge them (its pair order decides)' if may else 'KiCad merges the two segments', None))
    dup = {}
    for t in b.tracks:
        if not t['net'] or t['net'] in skip or is_arc(t) or t['len'] < 1e-4:
            continue
        k = (t['layer'], round(t['w'], 4), *sorted((q(t['a']), q(t['b']))))
        if k in dup and not (t['locked'] and dup[k]['locked']):
            out.append(('cleanup', t['net'], t['layer'], t['mid'], f"duplicate {t['len']:.2f} mm segment", 'KiCad deletes one', None))
        dup[k] = t
        p = None if t['locked'] else next((p for p in ix.pads[t['net']] if on_layer(p, t['layer'])
                                           and pad_dist(p, t['a'], True) <= -t['w'] / 2 + 1e-4
                                           and pad_dist(p, t['b'], True) <= -t['w'] / 2 + 1e-4), None)
        if p is not None:
            out.append(('cleanup', t['net'], t['layer'], t['mid'], f"{t['len']:.2f} mm wholly inside {lab[id(p)]}",
                        'deleted only with "tracks fully inside pads" ticked (off by default): end on the pad anchor', None))
    return out


def zone_rows(b):
    """[(kind, zone, detail, fix)]: 'zonepts' an outline hard to edit in KiCad (> 24 corners or
    4+ edges under 0.3 mm: what the pre-2026-10-28 `fatten`/`route --pour` traced, never what a designer
    draws: theirs are <= 22 corners, <= 3 short edges), 'zonedup' half or more of a zone inside
    another zone of its net on a shared layer (two outlines for one copper: delete one - a script
band only when it is the one inside: SW1's In2 band from U8 outside the designer's zone was the current
path, and CHG_VBUS 71% inside BAT_VBUS still lost 2.7 mm2 of fill, 2026-10-28). A plane
    net's zone inside its pour is a patch with rules of its own (RF_*_CPWG), never a dup"""
    from kpcb_route import _planes
    planes = {n for n, _l in _planes(b)}
    zs = [z for z in b.zones if z.outline and z[0] and not z.keepout]
    lays = {z.uuid: set(b.copper) if '*.Cu' in z[1] else set(z[1]) for z in zs}
    nm = lambda z: f"'{z.name or z.uuid[:8]}'"     # noqa: E731
    out = []
    for z in zs:
        P = z.outline
        short = sum(math.dist(P[i - 1], P[i]) < 0.3 for i in range(len(P)))
        if len(P) > 24 or short >= 4:
            out.append(('zonepts', z, f"{nm(z)} {len(P)} corners, {short} edge(s) < 0.3 mm",
                        'redraw: few corners on 0/45/90 (`zoneshape UUID --redraw` proposes one; or delete and `fatten NET --amps A`)'))
    idx, bbs = {z.uuid: PolyIndex(z.outline) for z in zs}, {z.uuid: bbox(z.outline) for z in zs}
    def frac(z, o):                                  # share of z's area inside o, on a 0.25 mm sample grid
        bz = bbs[z.uuid]
        pts = [p for i in range(int((bz[2] - bz[0]) / 0.25)) for j in range(int((bz[3] - bz[1]) / 0.25))
               for p in [(bz[0] + 0.125 + 0.25 * i, bz[1] + 0.125 + 0.25 * j)] if p in idx[z.uuid]]
        return sum(p in idx[o.uuid] for p in pts) / len(pts) if pts else 0.0
    for i, z in enumerate(zs):
        for o in zs[i + 1:]:
            if o[0] != z[0] or z[0] in planes or not lays[o.uuid] & lays[z.uuid] or not hit(bbs[z.uuid], bbs[o.uuid]):
                continue
            f, a, c = max((frac(z, o), z, o), (frac(o, z), o, z), key=lambda t: t[0])
            if f >= 0.5:
                band = [x for x in (a, c) if (x.name or '').startswith(('route ', 'fatten '))]
                mine = len(band) == 1 and band[0] is a       # zones compare by value: never ==
                past = (1 - f) * poly_area(a.outline) if mine else poly_area(c.outline) - f * poly_area(a.outline)
                fix = f'delete one, or `zonemerge {a.uuid[:8]} {c.uuid[:8]} -o OUT`' if len(band) != 1 else \
                    f"delete the script band {nm(a)}" + (f", then refill: {past:.1f} mm2 of it lies outside {nm(c)} "
                                                         "- check the net's fill area" if past >= 0.5 else '') \
                    if mine else f"band {nm(c)} reaches {past:.1f} mm2 past {nm(a)} (likely the current " \
                                        f"path): `zonemerge {a.uuid[:8]} {c.uuid[:8]} -o OUT` makes them one outline"
                out.append(('zonedup', a, f"{nm(a)} {f:.0%} inside {nm(c)}", fix))
    return out


KINDS = ('acute', '90', 'off45', 'neck', 'stub', 'pad', 'anchor', 'joint', 'overlap', 'twin', 'jog', 'detour', 'inpour',
         'inpourpwr', 'deadend', 'zonepts', 'zonedup', 'cleanup')


def kind_arg(s):
    """argparse type for --kind: a misspelt kind ran no pass and listed nothing"""
    bad = [k for k in s.split(',') if k and k not in KINDS]
    if bad:
        import argparse
        raise argparse.ArgumentTypeError(f"{','.join(bad)!r}: no such kind; one of {','.join(KINDS)}")
    return s


def c_tracks(b, a):
    skip = set() if a.all else skipped(b)
    box = tuple(float(v) for v in a.box.split(',')) if a.box else None
    kinds = [k for k in KINDS if not a.kind or k in a.kind.split(',')]
    c, rows = census_rows(b, skip, box, set(kinds) if a.kind else None)
    print(f"tracks{' in ' + a.box if box else ''}: {c['segs']} segments, {c['mm']:.1f} mm, {c['arc']} arc(s)"
          + (f"; {len(skip)} RF/USB/diff-pair net(s) skipped (--all includes them)" if skip else ''))
    label = {'acute': 'corners, acute', '90': 'corners 46-90 deg', 'off45': 'off-45 segments',
             'neck': 'width steps mid-run', 'stub': 'segments < 0.05 mm', 'pad': 'ends at a pad edge',
             'anchor': 'ends off a small pad anchor', 'joint': 'joined only by end caps', 'overlap': 'joined only through pad', 'twin': 'twin runs into one pad', 'jog': 'lane jogs 0.05-1 mm', 'detour': 'detours (> 1.5x MST)', 'inpour': 'plane tracks inside fill', 'inpourpwr': 'other tracks inside fill',
             'deadend': 'dead branches (no pad)', 'zonepts': 'zones hard to edit', 'zonedup': 'zones over own-net zone',
             'cleanup': 'KiCad cleanup would change'}
    for k in kinds:                                  # --kind: only the passes it needs ran
        print(f"  {label[k]:<22} {c[k]:>4} visible" + (f"  ({c['hidden ' + k]} hidden under same-net copper)"
                                                      if 'hidden ' + k in c else '')
              + (f"  ({c['inside pad']} more end inside their pad off centre: fine as KiCad joins; `anchor` lists"
                 f" signal ends on pads <= {SMALL_PAD:g} mm)" if k == 'pad' and c['inside pad'] else ''))
    per = Counter((r[2], r[0]) for r in rows if r[0] in ('acute', '90', 'off45')
                  and {'acute', '90', 'off45'} <= set(kinds))
    lays = sorted({ly for ly, _k in per}, key=lambda ly: b.copper.index(ly) if ly in b.copper else 99)
    if lays:
        print("  per layer: " + ' | '.join(f"{ly} {per[(ly, 'acute')]} acute {per[(ly, '90')]} x90 "
                                           f"{per[(ly, 'off45')]} off45" for ly in lays))
    shown, ix, taken, cks = [], None, None, {}
    for k in kinds:
        order = {'': 0, 'width step': 1, 'T': 2, 'frozen': 3}
        rs = sorted((r for r in rows if r[0] == k), key=lambda r: order.get(r[5], 4))   # what a pass can take first
        if not rs:
            continue
        print(f"\n{label[k]} ({len(rs)}):")
        for r in rs[:a.max]:
            why = r[5]
            if k == 'jog':                           # priced only when shown: a Clear per chain
                from kpcb_jogs import verdict
                why = verdict(b, *r[6], skip=skip, cks=cks)
            elif k == 'joint':                       # likewise: a Clear per end it moves
                ix = ix or Index(b)
                mv, why = close_joint(b, ix, *r[6])
                why = 'fix: smooth --joints' if mv else why
            elif k == 'pad':                         # the pass itself, once, on a copy: it edits its board's
                if taken is None:                    # tracks (only those; a reload was 0.9 s)
                    import copy
                    from kpcb_smooth import pass_pads
                    nb = copy.copy(b)
                    nb.tracks = [dict(t) for t in b.tracks]
                    taken = {(n, ly, q(E)) for n, ly, E, _c, _l in pass_pads(nb, skip, lambda *_a: True)}
                if (r[1], r[2], q(r[3])) not in taken:
                    why = 'smooth --pads finds no clear way onto the centre: by hand'
            elif not why and r[6]:                   # a free corner: can the corner pass cut it?
                why = 'fix: smooth --corners' if cut_corner(b, r[1], r[2], *r[6]) else 'boxed in at the real clearance'
            elif not why and k == 'off45':
                why = 'smooth (or boxed in)'
            print(f"  {unesc_disp(r[1].split('/')[-1]):<24} {r[2]:<7} {r[3][0]:8.3f},{r[3][1]:<8.3f} {r[4]:<20} {why}")
            if k == 'deadend':
                from kpcb_copper import dead_uuids
                print(f"      {' '.join(dead_uuids(r[6]))}")
                kc = kicad_takes(b, r[6])
                if kc:
                    print(f"      {kc}")
            shown.append(r)
        if len(rs) > a.max:
            print(f"  ... +{len(rs) - a.max} more - raise --max")
    if a.view and shown:
        from kpcb_view import sites_png
        out = sites_png(b, [(r[2], r[3], f"{r[0]} {unesc_disp(r[1].split('/')[-1])}") for r in shown], a.view,
                        a.radius if a.radius != 5.0 else 0.8, a.px if a.px != 20 else 120)
        print(f"\n{out}  ({len(shown)} panel(s), tracks/pads/vias only, the listed rows in order)")
    return 0


# ---------------------------------------------------------------- widen

def c_widen(b, a):
    if no_project(b, 'widen'):
        return 1
    imp = skipped(b)                                 # once: inside the comprehension it ran per track
    skip = imp | b.sw_nets()
    want = set(a.args) or None
    ix = Index(b)
    rf = [t for t in b.tracks if t['net'] in imp and t['layer'] in b.outer and
          'RF' in (b.netclass(t['net']) or '').upper()]
    fills = defaultdict(list)
    for fl in b.fills:
        fills[(fl['net'], fl['layer'])].append(PolyIndex(fl['pts']))
    bylay = defaultdict(list)
    for i, t in enumerate(b.tracks):
        bylay[(t['net'], t['layer'])].append(i)
    sig = a.width or 0.2

    def cls_of(net):
        nc = b.netclass(net) or 'Default'
        return nc, _netclass(b, net)

    def per_segment(t):
        nc, cl = cls_of(t['net'])
        return 'PWR' in nc.upper() and (cl.get('track_width') or 0) >= 1.0

    def target(t):
        nc, cl = cls_of(t['net'])
        if 'PWR' in nc.upper():
            if per_segment(t) and t['w'] < 0.5:
                return None                          # a sense / Kelvin leg
            return cl.get('track_width')
        return (cl.get('track_width') or 0.3) if t['net'] == 'GND' else sig

    def samples(t, step):
        n = max(1, math.ceil(t['len'] / step))
        return [(t['a'][0] + (t['b'][0] - t['a'][0]) * k / n, t['a'][1] + (t['b'][1] - t['a'][1]) * k / n) for k in range(n + 1)]

    def cap(t):
        """the narrow side of any SMD pad an end sits in"""
        return min([min(p['sx'], p['sy']) for p in ix.pads[t['net']] if on_layer(p, t['layer']) and not p['drill']
                    and (in_pad(p, t['a']) or in_pad(p, t['b']))], default=99.0)

    def in_fill(t):
        pis = fills.get((t['net'], t['layer']), ())
        return bool(pis) and all(any(pi.touches(x, 0) for pi in pis) for x in samples(t, 0.1))

    def contacts(i, t, w):
        """same-net items (not at t's ends) the capsule of width w touches"""
        out = set()
        if t['net'] == 'GND':
            return out
        ends = (t['a'], t['b'])
        for p in ix.pads[t['net']]:
            if on_layer(p, t['layer']) and not any(in_pad(p, e, 0.01) for e in ends) and \
                    any(in_pad(p, x, w / 2) for x in samples(t, 0.05)):
                out.add(('pad', id(p)))
        for v in ix.vias[t['net']]:
            c = (v['x'], v['y'])
            if t['layer'] in via_layers(v, b.copper) and all(math.dist(c, e) > v['size'] / 2 + 0.01 for e in ends) \
                    and pt_seg_dist(c, t['a'], t['b']) < (w + v['size']) / 2:
                out.add(('via', id(v)))
        for j in bylay[(t['net'], t['layer'])]:
            u = b.tracks[j]
            if j == i or any(pt_seg_dist(e, u['a'], u['b']) <= u['w'] / 2 + 0.01 for e in ends) or \
                    any(pt_seg_dist(e, t['a'], t['b']) <= t['w'] / 2 + 0.01 for e in (u['a'], u['b'])):
                continue                             # joined at an end or a T: one copper already
            if seg_seg_dist(t['a'], t['b'], u['a'], u['b']) < (w + u['w']) / 2:
                out.add(('trk', j))
        for k, pi in enumerate(fills.get((t['net'], t['layer']), ())):
            if any(pi.touches(x, w / 2) for x in samples(t, 0.05)):
                out.add(('fill', k))
        return out

    def clear(t, w):
        box = (min(t['a'][0], t['b'][0]) - 0.6, min(t['a'][1], t['b'][1]) - 0.6,
               max(t['a'][0], t['b'][0]) + 0.6, max(t['a'][1], t['b'][1]) + 0.6)
        g = Grid(b, t['net'], box, RES, w, 0.6, 0.3, [t['layer']], extra_clr=RES * 0.8)
        blk = g.blk[t['layer']]
        for x in samples(t, RES / 2):
            i, j = round((x[0] - g.x0) / g.res), round((x[1] - g.y0) / g.res)
            if not (0 <= i < g.W and 0 <= j < g.H) or blk[j * g.W + i]:
                return Exact(b, t['net'], t['layer'], w, (box[0] - 1, box[1] - 1, box[2] + 1, box[3] + 1)).seg(t['a'], t['b'])
        return True

    def scope(t):
        """a track widen may touch at all: named (or all) nets, not skipped/locked/arc, not an
        inner track under an RF trace's plane"""
        return not (not t['net'] or t['net'] in skip or (want and t['net'] not in want and t['net'].split('/')[-1]
                                                         not in want) or t['len'] < 1e-3 or t['locked'] or is_arc(t)
                    or t['layer'] not in b.outer and any(seg_seg_dist(t['a'], t['b'], r['a'], r['b']) < 2.0 for r in rf))

    def plan(t):
        """widths to try, widest first, or None"""
        if not scope(t):
            return None
        tg = target(t)
        if not tg or t['w'] >= tg - 1e-3:
            return None
        tg = min(tg, cap(t))
        if tg < t['w'] + 0.049 or in_fill(t):
            return None
        step, out, w = (0.1 if tg >= 0.6 else 0.05), [], tg
        while w >= t['w'] + 0.049:
            out.append(round(w, 3))
            w -= step
        return out

    def ok(i, t, w):
        return not (contacts(i, t, w) - contacts(i, t, t['w'])) and clear(t, w)

    done, tally = [], Counter()
    def accept(i, t, w):
        done.append((i, t['w'], w))
        tally[b.netclass(t['net']) or 'Default'] += t['len'] * (w - t['w'])
        t['w'] = w

    for i, t in enumerate(b.tracks):                 # power classes >= 1 mm: per segment
        if t['net'] and per_segment(t):
            for w in plan(t) or ():
                if ok(i, t, w):
                    accept(i, t, w)
                    break
    def runs_of(power):
        """tracks joined at nodes of exactly two same-net tracks off pads/vias, per-segment
        power classes (power) or the rest"""
        par = {}
        def find(x):
            while par.setdefault(x, x) != x:
                x = par[x]
            return x
        for (net, ly, n), lst in ix.ends.items():
            if len(lst) == 2 and all(per_segment(b.tracks[k]) == power for k in lst) and \
                    not ix.on_via(net, ly, n) and not ix.on_pad(net, ly, n):
                par[find(lst[0])] = find(lst[1])
        runs = defaultdict(list)
        for i, t in enumerate(b.tracks):
            if t['net'] and per_segment(t) == power:
                runs[find(i)].append(i)
        return runs.values()

    steps = None
    if a.uniform_power:                              # a power run at its widest where that is clear
        for run in runs_of(True):
            mx = max(b.tracks[i]['w'] for i in run)
            for i in run:
                t = b.tracks[i]
                if t['w'] >= mx - 1e-3 or t['w'] < 0.5 or not scope(t) or in_fill(t):
                    continue                         # at max, a sense leg, out of scope, or inside its own fill
                w = min(mx, cap(t))
                if w > t['w'] + 0.049 and ok(i, t, w):
                    accept(i, t, w)
        steps = sum(1 for (net, ly, n), lst in ix.ends.items() if len(lst) == 2
                    and all(per_segment(b.tracks[k]) for k in lst) and not ix.on_via(net, ly, n)
                    and not ix.on_pad(net, ly, n) and abs(b.tracks[lst[0]]['w'] - b.tracks[lst[1]]['w']) > 1e-3)
    # the rest, one width per run
    pad_end = lambda t: t['len'] < 0.6 and (ix.on_pad(t['net'], t['layer'], t['a']) or ix.on_pad(t['net'], t['layer'], t['b']))  # noqa: E731
    for run in runs_of(False):
        ps = {i: plan(b.tracks[i]) for i in run}
        if not any(ps.values()):
            continue
        core = [i for i in run if not pad_end(b.tracks[i])] or run
        tops = [ps[i][0] for i in core if ps[i]]
        if not tops:
            continue
        lo = min(b.tracks[i]['w'] for i in core)
        for w in sorted({w for i in core if ps[i] for w in ps[i] if w > lo + 0.049}, reverse=True):
            if w > min(tops) + 1e-3:
                continue
            need = [i for i in core if b.tracks[i]['w'] < w - 1e-3 and not (in_fill(b.tracks[i]) and not ps[i])]
            if any(not ps[i] or w not in ps[i] for i in need):
                continue
            if all(ok(i, b.tracks[i], w) for i in need):
                for i in need:
                    accept(i, b.tracks[i], w)
                for i in run:                        # pad entries taper only if they must
                    if i not in core:
                        for w2 in [x for x in (ps[i] or ()) if x <= w + 1e-3]:
                            if ok(i, b.tracks[i], w2):
                                accept(i, b.tracks[i], w2)
                                break
                break
    if a.uniform:                                    # a segment narrower than both neighbours: their width
        for i, t in enumerate(b.tracks):
            if not t['net'] or per_segment(t) or not scope(t) or in_fill(t):
                continue
            nb, vs = [], []
            for e in (t['a'], t['b']):
                lst = [k for k in ix.ends[(t['net'], t['layer'], q(e))] if k != i]
                v = next((v for v in ix.vias[t['net']] if math.dist(e, (v['x'], v['y'])) <= v['size'] / 2), None)
                if ix.on_pad(t['net'], t['layer'], e) or len(lst) > 1 or (not lst and not v):
                    nb = []                          # a pad (a fine-pitch neck), a junction or a dead end
                    break
                nb += [b.tracks[k]['w'] for k in lst]
                vs += [v['size']] if v else []
            w = min(nb, default=0.0)
            if nb and w > t['w'] + 1e-3 and w <= min(vs, default=w) and ok(i, t, w):
                accept(i, t, w)
    print(f"widen: {len(done)} track(s); copper added (mm2) by class: "
          + (', '.join(f'{k} {v:.1f}' for k, v in sorted(tally.items())) or 'none')
          + (f"; {steps} width step(s) left mid-run in power classes (boxed in)" if steps is not None else ''))
    for i, w0, w1 in sorted(done, key=lambda d: -b.tracks[d[0]]['len'] * (d[2] - d[1]))[:a.max]:
        t = b.tracks[i]
        print(f"  {unesc_disp(t['net'].split('/')[-1]):<26} {t['layer']:<7} {w0:g} -> {w1:g}  {t['len']:.2f} mm  "
              f"at {t['a'][0]:.2f},{t['a'][1]:.2f}")
    if len(done) > a.max:
        print(f"  ... +{len(done) - a.max} more")
    if not done or not a.out:
        if done:
            print("(dry run: -o OUT writes it)")
        return 0
    t = PcbText(b.path)
    for i, _w0, w1 in done:
        s, n = re.subn(r'\(width [^)]*\)', f'(width {num(w1)})', t.text(b.tracks[i]['uuid']), count=1)
        assert n == 1
        t.sub(b.tracks[i]['uuid'], s)
    tear = len(tear_edits(t, [b.tracks[i] for i, _a, _b in done]))
    t.save(a.out)
    print(f"wrote {a.out}: {len(done)} width edit(s), {tear} teardrop(s) dropped (the refill re-creates those "
          f"whose track stays <= 0.9x the pad/via)")
    return 0


# ---------------------------------------------------------------- loops

def c_loops(b, a):
    if no_project(b, 'loops'):
        return 1
    poured = {fl['net'] for fl in b.fills}
    skip = skipped(b)
    nets = [n for n in (set(a.args) or {t['net'] for t in b.tracks if t['net']})
            if n not in poured and n not in skip and n != 'GND' and 'PWR' not in (b.netclass(n) or '').upper()
            and rail_voltage(n.split('/')[-1]) is None]
    allT, allV = b.tracks, b.vias
    def part(net):          # KiCad's joins AND the strict ones: neither may change
        ts = [t for t in b.tracks if t['net'] == net]
        vs = [v for v in b.vias if v['net'] == net]
        entered = frozenset(f"{f.ref}.{p['num']}" for f in b.fps.values() for p in f.pads if p['net'] == net and (
            any(on_layer(p, t['layer']) and (in_pad(p, t['a']) or in_pad(p, t['b'])) for t in ts)
            or any(in_pad(p, (v['x'], v['y'])) for v in vs)))
        # a pad whose only centreline entry goes is left on a graze, which the strict partition
        # misses when the pad was already strictly apart (LED_DO U20.3's centre stub, 2026-10-19)
        return tuple({frozenset(f"{f.ref}.{p['num']}" for f, p in pc['pads']) for pc in piece_parts(b, net, st)}
                     for st in (False, True)) + (entered,)
    found, kill = [], set()
    for net in sorted(nets):
        base = part(net)
        while True:
            b.tracks = [t for t in allT if id(t) not in kill]
            b.vias = [v for v in allV if id(v) not in kill]
            got = None
            pads = [p for f in b.fps.values() if f.placed for p in f.pads if p['net'] == net]
            vias = [(v['x'], v['y'], v['size'] / 2) for v in b.vias if v['net'] == net]
            chs = [c for c in chains(b, set(), only={net})     # an entry stub inside one pad or via is no loop
                   if not any(all(in_pad(p, x) for x in c[4]) for p in pads)
                   and not any(all(math.dist(x, (vx, vy)) <= r for x in c[4]) for vx, vy, r in vias)]
            for ch in sorted(chs, key=lambda c: -sum(b.tracks[i]['len'] for i in c[3])):
                k2 = prune(b, {id(b.tracks[i]) for i in ch[3]})
                b.tracks = [t for t in allT if id(t) not in kill | k2]
                b.vias = [v for v in allV if id(v) not in kill | k2]
                same = part(net) == base
                b.tracks = [t for t in allT if id(t) not in kill]
                b.vias = [v for v in allV if id(v) not in kill]
                if same:
                    got = (ch, k2)
                    break
            if not got:
                break
            ch, k2 = got
            kill |= k2
            gone = [t for t in allT if id(t) in k2]
            found.append((net, sum(t['len'] for t in gone), sorted({t['layer'] for t in gone}), len(gone),
                          sum(1 for v in allV if id(v) in k2), ch[4][0]))
    b.tracks, b.vias = allT, allV
    if not found:
        print(f"loops: no redundant chain on {len(nets)} signal net(s) (power, GND, poured, RF/USB nets skipped)")
        return 0
    print(f"loops: {len(found)} redundant chain(s) on {len({f[0] for f in found})} net(s), "
          f"{sum(f[1] for f in found):.1f} mm; removing each keeps its net's pads joined (prune included)")
    for net, L, lys, nt, nv, at in sorted(found, key=lambda f: -f[1])[:a.max]:
        print(f"  {unesc_disp(net.split('/')[-1]):<26} {L:6.2f} mm  {'/'.join(lys):<14} {nt} seg" + (f" {nv} via" if nv else '')
              + f"  from {at[0]:.2f},{at[1]:.2f}")
    if len(found) > a.max:
        print(f"  ... +{len(found) - a.max} more")
    if not a.out:
        print("(dry run: -o OUT deletes them; then kdrc.py OUT drc --refill-save --baseline BEFORE.json)")
        return 0
    return _rip_out(b, a, kill, 'loops')
