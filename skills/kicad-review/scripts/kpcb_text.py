"""kpcb's text-surgery layer: the board file as text, edited by span (PcbText), and the
number / string formatting KiCad writes. Every writer goes through it; it imports no
command module (kpcb_fillet only inside PcbText.zone)."""
import math, os, re, uuid


def num(v):
    """a coordinate as KiCad writes it: <= 6 decimals, no trailing zeros"""
    s = f"{v:.6f}".rstrip('0').rstrip('.')
    return '0' if s in ('', '-0') else s


def qs(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def norm_ang(a):
    a = math.fmod(a, 360.0)
    a = a - 360 if a > 180 else a + 360 if a <= -180 else a
    return 0.0 if abs(a) < 1e-9 else a


class PcbText:
    """The board as text, edited by span. A top-level item opens on a `\\n\\t(` line and
    closes on the next `\\n\\t)` line (KiCad's formatter; nothing deeper sits at one
    tab), so footprints, tracks, vias and zones are found by uuid without re-serialising
    anything that was not edited. New tracks/vias go in before the first zone."""

    def __init__(self, path):
        self.path = path
        with open(path, encoding='utf-8') as fh:
            self.txt = fh.read()
        self.span, self.edits = {}, []
        for m in re.finditer(r'\n\t\((footprint|segment|arc|via|gr_text|zone)\b', self.txt):
            s = m.start() + 1
            e = self.txt.index('\n\t)', s) + 3
            u = re.search(r'\(uuid "([^"]+)"\)', self.txt[s:e])     # first uuid = the item's own
            if u:
                self.span[u.group(1)] = (s, e)
        z = self.txt.find('\n\t(zone')
        self.tail = (z if z >= 0 else self.txt.rindex('\n)')) + 1
        self._tears = None

    @property
    def tears(self):
        """teardrop zones [(start, end, net, layer, outline points)], found on first use"""
        if self._tears is None:
            self._tears = []
            for m in re.finditer(r'\n\t\(zone\n', self.txt):
                s = m.start() + 1
                e = self.txt.index('\n\t)', s) + 3
                blk = self.txt[s:e]
                if '(teardrop' not in blk:
                    continue
                net = re.search(r'\(net "((?:[^"\\]|\\.)*)"\)', blk)
                ly = re.search(r'\(layer "([^"]+)"\)', blk)
                pol = re.search(r'\(polygon\n\t+\(pts\n(.*?)\n\t+\)', blk, re.S)
                pts = [(float(x), float(y)) for x, y in re.findall(r'\(xy (\S+) (\S+)\)', pol[1])] if pol else []
                if net and ly and len(pts) >= 3:
                    self._tears.append((s, e, net[1].replace('\\"', '"'), ly[1], pts))
        return self._tears

    def text(self, uid):
        s, e = self.span[uid]
        return self.txt[s:e]

    def sub(self, uid, new):
        """replace (or with '' delete) an item; returns the edit, so it can be withdrawn"""
        s, e = self.span[uid]
        if not new and self.txt[e:e + 1] == '\n':            # a deletion takes its line break too
            e += 1
        self.edits.append((s, e, new))
        return self.edits[-1]

    def add(self, item):
        """queue a new item; returns the edit, so `edits.remove` can withdraw it (a rip-up)"""
        self.edits.append((self.tail, self.tail, item))
        return self.edits[-1]

    def segment(self, net, layer, w, a, b):
        return self.add(f"\t(segment\n\t\t(start {num(a[0])} {num(a[1])})\n\t\t(end {num(b[0])} {num(b[1])})\n"
                 f"\t\t(width {num(w)})\n\t\t(layer {qs(layer)})\n\t\t(net {qs(net)})\n"
                 f"\t\t(uuid \"{uuid.uuid4()}\")\n\t)\n")

    def via(self, net, x, y, size, drill, layers, free=False):
        """free: a stitching via with no track. KiCad re-nets a trackless via from the copper it
        touches on load/save unless it is marked free (a GND via came back -BATT, 2026-10-19)"""
        return self.add(f"\t(via\n\t\t(at {num(x)} {num(y)})\n\t\t(size {num(size)})\n\t\t(drill {num(drill)})\n"
                 f"\t\t(layers {' '.join(qs(l) for l in layers)})\n" + ("\t\t(free yes)\n" if free else '')
                 + f"\t\t(net {qs(net)})\n\t\t(uuid \"{uuid.uuid4()}\")\n\t)\n")

    def zone(self, net, layer, pts, priority, clearance=0.2, min_w=0.25, name=None):
        """an unfilled solid-connect zone (the refill draws its copper): sharp corners (faceted
        arcs unrounded, kpcb_fillet) + KiCad's 0.2 fillet, as a designer draws power zones by hand"""
        from kpcb_fillet import fillet_outline, FILLET
        pts, r, _note = fillet_outline(pts)
        r = r or FILLET
        sm = f"\t\t\t(smoothing fillet)\n\t\t\t(radius {num(r)})\n" if r else ''
        xy = ''.join(f"\t\t\t\t(xy {num(x)} {num(y)})\n" for x, y in pts)
        return self.add(f"\t(zone\n\t\t(net {qs(net)})\n\t\t(layer {qs(layer)})\n\t\t(uuid \"{uuid.uuid4()}\")\n"
                        f"\t\t(name {qs(name or 'route ' + net)})\n\t\t(hatch edge 0.5)\n\t\t(priority {priority})\n"
                        f"\t\t(connect_pads yes\n\t\t\t(clearance {num(clearance)})\n\t\t)\n\t\t(min_thickness {num(min_w)})\n"
                        f"\t\t(fill yes\n\t\t\t(thermal_gap 0.5)\n\t\t\t(thermal_bridge_width 0.5)\n{sm}"
                        f"\t\t\t(island_removal_mode 0)\n\t\t)\n\t\t(polygon\n\t\t\t(pts\n{xy}\t\t\t)\n\t\t)\n\t)\n")

    def save(self, out, inplace=False):
        """inplace: OUT is this run's own output being amended (the post-write gate), never the input"""
        if not inplace and os.path.abspath(out) == os.path.abspath(self.path):
            raise SystemExit("refusing to overwrite the input board: write a copy (-o OUT), "
                             "check it with kdrc.py, then move it into place")
        parts, pos = [], 0
        for s, e, new in sorted(self.edits, key=lambda x: (x[0], x[1])):
            if s < pos:
                raise SystemExit("internal: overlapping edits, nothing written")
            parts += [self.txt[pos:s], new]
            pos = e
        parts.append(self.txt[pos:])
        with open(out, 'w', encoding='utf-8') as fh:
            fh.write(''.join(parts))
