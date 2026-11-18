"""part.py `bom`, `jlc` and `check`: whole-board costing and JLC assembly triage."""
import sys, os, re, json, itertools
import concurrent.futures as cf
from part_core import (best_buy, buy_qty, cfg, conv, dk_search, dk_token, dmoney1, _FX, jlc_detail,
                       lcsc_detail, load_knet, money, mouser_search, price_at, third_note, trunc)

CODE_RE = re.compile(r'\bC\d{3,}\b')

def _missing(missing, a, jlc=None):
    """Codes LCSC could not detail, split into JLC-assembly-only parts (LCSC does
    not sell them retail; JLC catalog price, never added to an LCSC total) and codes
    neither catalog knows."""
    jlc = jlc if jlc is not None else {c: jlc_detail(c, a.fresh) for c in missing}
    only = [c for c in missing if jlc.get(c)]
    for c in only:
        h = jlc[c]
        up = price_at(h.get('ladder') or [], 1)
        print(f"JLC assembly only (no LCSC retail, not in the total): {c} {h.get('mpn')}  "
              f"{dmoney1(up, 'USD', a)}@1 JLC catalog, JLC stock {h.get('stock')}")
    rest = [c for c in missing if c not in only]
    if rest:
        print(f"unresolved codes (neither LCSC nor JLC has them): {' '.join(rest)}")

def _sheet_rules(a):
    """--sheet-qty LoRa=2 -> [('/LoRa/', 2)], longest first: a part on that sheet or a
    sheet under it is bought for 2 boards instead of --qty (a variant fitted on some)."""
    out = []
    for s in getattr(a, 'sheet_qty', None) or []:
        p, _, n = s.rpartition('=')
        if not p.strip('/') or not n.isdigit():
            sys.exit(f"--sheet-qty: want SHEET=N (e.g. /Root/LoRa/=2 or LoRa=2), got {s!r}")
        out.append(('/' + p.strip('/') + '/', int(n)))
    return sorted(out, key=lambda r: -len(r[0]))

def _rule(sheet, rules):
    """The --sheet-qty rule a sheet path falls under (whole path segments), or None."""
    s = '/' + (sheet or '').strip('/') + '/'
    return next((r for r in rules if r[0] in s), None)

def _collect(nl, rules):
    """From a parsed netlist: {code: refs}, no-code refs, {mpn: refs} (the no-code refs
    that name an MPN, priceable off LCSC), {ref: its --sheet-qty rule or None}."""
    want, nocode, mpns, grp = {}, [], {}, {}
    for ref, c in nl.comps.items():
        if c['dnp'] or not c['in_bom']:
            continue
        grp[ref] = _rule(c.get('sheet'), rules)
        mpn = (c.get('props') or {}).get('MPN', '').strip()
        if re.fullmatch(r'C\d+', c['lcsc'] or ''):
            want.setdefault(c['lcsc'], []).append(ref)
        elif c['prefix'] not in ('H', 'TP'):
            nocode.append(ref)
            if mpn:
                mpns.setdefault(mpn, []).append(ref)
    for r in rules:
        if r not in grp.values():
            print(f"--sheet-qty {r[0]}={r[1]}: no fitted part sits on that sheet", file=sys.stderr)
    return want, nocode, mpns, grp

def _need(refs, grp, boards):
    return sum((grp.get(r) or (None, boards))[1] for r in refs)

_NORM = lambda s: re.sub(r'\s', '', (s or '').upper())    # noqa: E731

def _offers(mpn, need, a, provs):
    """{provider: offer}: the cheapest exact-MPN offer per provider that has stock for
    the buy, price breaks tried, ext in USD."""
    out = {}
    for p in provs:
        res, _ = (dk_search if p == 'digikey' else mouser_search)(mpn, 6, a)
        for d in res:
            if _NORM(d.get('mpn')) != _NORM(mpn) or not d.get('ladder'):
                continue
            q, u = best_buy(need, d['ladder'], d.get('moq'), d.get('multiple'))
            ext = conv((u or 0) * q, d.get('currency') or 'USD', 'USD')
            if (d.get('stock') or 0) >= q and ext is not None and (p not in out or ext < out[p]['ext']):
                out[p] = {'sku': d.get('sku'), 'buy': q, 'ext': ext, 'stock': d.get('stock')}
    return out

def _split(lines, ship):
    """Cheapest supplier set. lines: [{source: ext}] (each source that can fill the line);
    ship: {source: (cost, free_over or None)}. Each line goes to its cheapest source in
    the set, each used source adds its shipping unless its subtotal reaches free_over.
    Returns (total, {source: subtotal}, [source per line]), or None when no set covers
    every line (drop the unsourced lines first)."""
    # ponytail: a line is never moved to a dearer source just to reach a free-shipping
    # threshold; that is worth a few lines' price at most
    srcs, best = sorted({s for o in lines for s in o}), None
    for k in range(1, len(srcs) + 1):
        for sub in itertools.combinations(srcs, k):
            if not all(any(s in o for s in sub) for o in lines):
                continue
            pick = [min((s for s in sub if s in o), key=o.get) for o in lines]
            subt = {}
            for o, s in zip(lines, pick):
                subt[s] = subt.get(s, 0) + o[s]
            tot = 0
            for s, v in subt.items():
                cost, free = ship.get(s) or (0, None)
                tot += v + (0 if free is not None and v >= free else cost)
            if best is None or tot < best[0] - 1e-9:
                best = (tot, subt, pick)
    return best

def _ship(a, provs):
    """{source: (cost, free_over)} in USD from config.json `shipping`, given there in
    the display currency: {"lcsc": [25, null], "digikey": [10, 100]}."""
    raw = cfg('shipping', 'PARTSEARCH_SHIPPING') or {}
    if isinstance(raw, str):
        raw = json.loads(raw)
    out = {}
    for s in ['lcsc'] + provs:
        v = raw.get(s)
        if v is None:
            continue
        cost, free = ((v if isinstance(v, list) else [v]) + [None])[:2]
        out[s] = (conv(cost or 0, a.currency, 'USD') or 0,
                  conv(free, a.currency, 'USD') if free else None)
    return out

def _alts(rows, a, n):
    """The cheapest drop-in by `alt`'s rules for the n costliest lines, at each line's
    need: [(row, (ext_usd, buy, hit))], only where it costs less."""
    import argparse, contextlib, io
    from part_pick import c_alt
    out = []
    # ponytail: sequential, ~10-30 s cold per line; pick's module state is not thread-safe
    for r in sorted(rows, key=lambda x: -x['ext'])[:n]:
        b = argparse.Namespace(**dict(vars(a), args=[r['lcsc']], qty=r['need'], w=[], json=False,
                                      _collect=[], minstock=max(a.minstock, r['buy'])))
        with contextlib.redirect_stdout(io.StringIO()):
            c_alt(b)
        best = None
        for h in b._collect:
            if not h.get('ladder'):
                continue
            q, u = best_buy(r['need'], h['ladder'], h.get('moq'), h.get('multiple'))
            ext = conv((u or 0) * q, h.get('currency') or 'USD', 'USD')
            if ext is not None and ext < r['ext'] - 1e-9 and (best is None or ext < best[0]):
                best = (ext, q, h)
        if best:
            out.append((r, best))
    return out

def _lcsc_csv(path, rows, mpn_lines, nl):
    """LCSC's BOM tool upload (lcsc.com/bom): one row per line at the buy quantity."""
    import csv
    comp = lambda refs: (nl.comps.get(refs[0]) if nl and refs and refs[0] != '?' else None) or {}  # noqa: E731
    with open(path, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['Quantity', 'Manufacture Part Number', 'Manufacturer', 'LCSC Part Number',
                    'Designator', 'Package', 'Value'])
        for r in rows + mpn_lines:
            c = comp(r['refs'])
            w.writerow([r['buy'], r.get('mpn') or '', (c.get('props') or {}).get('Manufacturer', ''),
                        r.get('lcsc') or '', ','.join(x for x in r['refs'] if x != '?'),
                        (c.get('footprint') or '').split(':')[-1], c.get('value', '')])
    print(f"wrote {path}: {len(rows) + len(mpn_lines)} lines for LCSC's BOM tool")

def c_bom(a):
    src = a.args[0] if a.args else '-'
    txt = sys.stdin.read() if src == '-' else open(src, encoding='utf-8', errors='replace').read()
    want, nocode, mpns, grp, nl = {}, [], {}, {}, None
    rules = _sheet_rules(a)
    if src.endswith('.net'):
        nl = load_knet(src)        # prefer kcommon.py's real S-expression parser
        if nl is not None:
            want, nocode, mpns, grp = _collect(nl, rules)
        else:
            print("(kcommon.py not importable, falling back to regex)", file=sys.stderr)
            if rules:
                print("--sheet-qty needs kcommon.py: every part priced at --qty", file=sys.stderr)
            for m in re.finditer(r'\(comp\s+\(ref "([^"]+)"\)(.*?)(?=\(comp\s+\(ref|\(libparts)', txt, re.S):
                ref, blob = m.group(1), m.group(2)
                if '"dnp"' in blob:
                    continue
                cm = re.search(r'\(name "LCSC(?: Part)?"\)\s*\(value "(C\d+)"\)', blob)
                if cm:
                    want.setdefault(cm.group(1), []).append(ref)
                else:
                    nocode.append(ref)
    else:
        for line in txt.splitlines():
            m = CODE_RE.search(line)
            if m:
                n = re.search(r'\bx?(\d+)\s*$', line.strip())
                want.setdefault(m.group(0), []).extend(['?'] * (int(n.group(1)) if n else 1))
    if not want and not mpns:
        print("no LCSC codes found. netlist needs an 'LCSC Part' property, or pass a "
              "text file with one C-code per line"); return
    boards = a.qty or 1
    provs = [p.strip().lower() for p in (getattr(a, 'vs', None) or '').split(',') if p.strip()]
    if set(provs) - {'digikey', 'mouser'}:
        print(f"--vs: digikey and/or mouser, got {getattr(a, 'vs', None)!r}"); return 1
    if 'digikey' in provs and not dk_token(a.fresh)[0]:
        print(f"--vs digikey: {dk_token(a.fresh)[1]}"); provs.remove('digikey')
    if 'mouser' in provs and not cfg('mouser_api_key', 'MOUSER_API_KEY'):
        print("--vs mouser: no key (set MOUSER_API_KEY or config.json mouser_api_key)"); provs.remove('mouser')

    def one(item):
        code, refs = item
        r = lcsc_detail(code, a.fresh)
        if not r:
            return code, None
        need = _need(refs, grp, boards)
        q, up = best_buy(need, r.get('ladder'), r.get('moq'), r.get('multiple'))
        row = {'lcsc': code, 'mpn': r.get('mpn'), 'refs': refs, 'per_board': len(refs),
               'need': need, 'buy': q, 'unit': up, 'ext': (up or 0) * q,
               'break': q > buy_qty(need, r.get('moq'), r.get('multiple')),
               'stock': r.get('stock'), 'package': r.get('package')}
        if provs and r.get('mpn'):
            row['offers'] = _offers(r['mpn'], need, a, provs)
        return code, row
    with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        res = list(ex.map(one, sorted(want.items())))
        mpn_lines = [{'lcsc': None, 'mpn': m, 'refs': refs, 'per_board': len(refs),
                      'need': _need(refs, grp, boards), 'buy': _need(refs, grp, boards)}
                     for m, refs in sorted(mpns.items())]
        if provs:
            for L, o in zip(mpn_lines, ex.map(lambda L: _offers(L['mpn'], L['need'], a, provs), mpn_lines)):
                L['offers'] = o
    rows = [r for _, r in res if r]
    missing = [c for c, r in res if not r]
    total = sum(r['ext'] for r in rows)
    # what one board of each variant costs: unit price x placements, overbuy excluded
    per = {}
    for r in rows:
        for ref in r['refs']:
            k = (grp.get(ref) or ('base', 0))[0]
            per[k] = per.get(k, 0) + (r['unit'] or 0)
    split = alts = None
    if provs:
        lines, srcd, unsourced = [], [], []
        for r in rows + mpn_lines:
            o = {s: v['ext'] for s, v in (r.get('offers') or {}).items()}
            if r.get('lcsc') and isinstance(r['stock'], int) and r['stock'] >= r['buy']:
                o['lcsc'] = r['ext']
            if o:
                lines.append(o); srcd.append(r)
            else:
                unsourced.append(r.get('lcsc') or r['mpn'])
        ship = _ship(a, provs)
        best = _split(lines, ship)
        only = _split([{'lcsc': o['lcsc']} if 'lcsc' in o else o for o in lines], ship)
        split = {'shipping_usd': ship, 'unsourced': unsourced,
                 'best': best and {'total_usd': best[0], 'subtotal_usd': best[1],
                                   'lines': {(r.get('lcsc') or r['mpn']): s for r, s in zip(srcd, best[2])}},
                 'lcsc_first_total_usd': only and only[0],
                 'lcsc_lines': sum(1 for o in lines if 'lcsc' in o), 'lines': len(lines)}
    if getattr(a, 'alt', 0):
        alts = _alts(rows, a, a.alt)
    if getattr(a, 'lcsc_csv', None):
        _lcsc_csv(a.lcsc_csv, rows, mpn_lines, nl)
    if a.json:
        print(json.dumps({'boards': boards, 'sheet_qty': dict(rules), 'lines': rows,
                          'mpn_only_lines': mpn_lines, 'total_usd': round(total, 4),
                          'per_board_usd': {k: round(v, 4) for k, v in per.items()},
                          'total_display': {'currency': a.currency,
                                            'amount': round(conv(total, 'USD', a.currency) or total, 4)},
                          'split': split,
                          'alts': [{'lcsc': r['lcsc'], 'ext_usd': r['ext'], 'alt': h.get('sku'),
                                    'mpn': h.get('mpn'), 'mfr': h.get('mfr'), 'buy': q, 'alt_ext_usd': e}
                                   for r, (e, q, h) in alts or []],
                          'unresolved': missing, 'jlc_only': [c for c in missing if jlc_detail(c, a.fresh)],
                          'no_lcsc_code': sorted(nocode)}, indent=1)); return
    vt = ''.join(f", {p} x{n}" for p, n in rules)
    print(f"{boards} board(s){vt}, {len(rows)} distinct LCSC parts\n")
    print(f"{'lcsc':<12} {'mpn':<26} {'pkg':<12} {'/bd':>4} {'buy':>7} {'unit':>10} "
          f"{'ext':>9}  {'stock':>10}  refs")
    for r in sorted(rows, key=lambda x: -x['ext']):
        low = '  LOW STOCK' if isinstance(r['stock'], int) and r['stock'] < r['buy'] else ''
        brk = f"  (need {r['need']}, a break)" if r['break'] else ''
        print(f"{r['lcsc']:<12} {trunc(r['mpn'],26):<26} {trunc(r['package'],12):<12} "
              f"{r['per_board']:>4} {r['buy']:>7} {dmoney1(r['unit'],'USD',a):>10} "
              f"{dmoney1(r['ext'],'USD',a):>9}  "
              f"{r['stock']:>10,}  {' '.join(r['refs'][:6])}{low}{brk}")
        if low and third_note(lcsc_detail(r['lcsc']), r['buy']):
            print(f"{'':<12} {third_note(lcsc_detail(r['lcsc']), r['buy'])}")
    ct = conv(total, 'USD', a.currency)
    if a.currency != 'USD' and ct is not None:
        _FX['used'] = True
        print(f"\ntotal parts cost: {money(ct, a.currency)} ({money(total,'USD')}) "
              f"for {boards} board(s)" + ('' if rules else f"  ({money(ct/boards, a.currency)}/board)"))
    else:
        print(f"\ntotal parts cost: {money(total,'USD')} for {boards} board(s)"
              + ('' if rules else f"  ({money(total/boards,'USD')}/board)"))
    if rules:
        print("per board (LCSC lines, unit x placements, overbuy excluded): base "
              + dmoney1(per.get('base', 0), 'USD', a)
              + ''.join(f", {p} +{dmoney1(per.get(p, 0), 'USD', a)}" for p, _ in rules))
    print("excludes DNP parts, shipping, tax, PCB and assembly")
    _missing(missing, a)
    if nocode:
        print(f"\n{len(nocode)} placed component(s) have NO LCSC part number and are not "
              f"costed here:\n  {' '.join(sorted(nocode))}")
    if split:
        _print_split(split, rows + mpn_lines, a)
    if alts is not None:
        _print_alts(alts, a)

def _print_split(sp, lines, a):
    b, m = sp['best'], lambda x: dmoney1(x, 'USD', a)     # noqa: E731
    print(f"\nsupplier split ({sp['lines']} lines sourceable, exact-MPN matches, price breaks tried)")
    if not sp['shipping_usd']:
        print("  shipping: none configured, so 0 everywhere and the split over-favours small orders; "
              "set config.json \"shipping\": {\"lcsc\": [COST, FREE_OVER|null], \"digikey\": [...]} "
              "in your display currency, brokerage/duty included")
    if b:
        print("  cheapest: " + ' + '.join(f"{s} {m(v)}" for s, v in sorted(b['subtotal_usd'].items()))
              + f" = {m(b['total_usd'])} incl. shipping")
    if sp['lcsc_first_total_usd'] is not None:
        print(f"  vs LCSC wherever it has stock ({sp['lcsc_lines']} lines, the rest as above): "
              f"{m(sp['lcsc_first_total_usd'])} incl. shipping")
    for r in lines:
        k = r.get('lcsc') or r['mpn']
        s = (b or {}).get('lines', {}).get(k)
        if s and s != 'lcsc':
            o = r['offers'][s]
            was = (f"LCSC {m(r['ext'])}" + ('' if (r['stock'] or 0) >= r['buy'] else ', short')
                   if r.get('lcsc') else 'no LCSC code')
            print(f"    {trunc(k,12):<12} {trunc(r['mpn'],24):<24} -> {s} {o['sku']} x{o['buy']} {m(o['ext'])}  (was {was})")
    if sp['unsourced']:
        print(f"  no source has stock: {' '.join(sp['unsourced'])}")

def _print_alts(alts, a):
    m = lambda x: dmoney1(x, 'USD', a)     # noqa: E731
    print(f"\ncheaper drop-ins for the costliest lines ({len(alts)} found; `alt`'s rules: same "
          f"category + package, equal-or-better ratings. Read each datasheet before swapping)")
    for r, (e, q, h) in alts:
        lib = {'base': 'BASIC', 'expand': 'ext'}.get(h.get('library'), '')
        print(f"  {r['lcsc']:<11} {trunc(r['mpn'],22):<22} {m(r['ext']):>9} -> {h.get('sku')} "
              f"{trunc(h.get('mpn'),22)} ({trunc(h.get('mfr'),16)}) x{q} {m(e)}  saves {m(r['ext'] - e)} {lib}")
    if alts:
        print(f"  total if all taken: saves {m(sum(r['ext'] - e for r, (e, _, _) in alts))}")

def c_jlc(a):
    """Basic vs Extended for C-codes already chosen. Extended costs $3 USD per unique
    line on a JLC assembly order, so this is the fee-triage command."""
    codes, refs = [], {}
    for x in a.args:
        if x.endswith('.net') and os.path.exists(x):
            # A bare regex would take capacitor refdes C108/C221 for LCSC codes. Only
            # the "LCSC Part" property is a code, so parse rather than pattern-match.
            nl = load_knet(x)
            if nl is None:
                print(f"jlc: could not parse {x} (kcommon.py not importable)"); return 1
            for ref, c in nl.comps.items():
                if c['dnp'] or not c['in_bom']:
                    continue
                if re.fullmatch(r'C\d+', c['lcsc'] or ''):
                    codes.append(c['lcsc'])
                    refs.setdefault(c['lcsc'], []).append(ref)
        elif os.path.exists(x):
            codes += re.findall(r'\bC\d{3,}\b', open(x, encoding='utf8', errors='ignore').read())
        else:
            codes += re.findall(r'\bC\d{3,}\b', x.upper())
    codes = list(dict.fromkeys(codes))
    if not codes:
        print("jlc: give C-codes or a file containing them"); return 1
    qty = a.qty or 1
    ext = 0
    with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        res = list(ex.map(lambda c: (c, jlc_detail(c, a.fresh)), codes))
    rf = lambda c: (' ' + trunc(','.join(refs[c]), 22)) if refs.get(c) else ''
    print(f"{'code':<11} {'lib':<6} {'stock':>10}  {'unit@'+str(qty):<12} {'part':<28} note")
    for code, h in res:
        if not h:
            print(f"{code:<11} {'-':<6} {'-':>10}  {'-':<12} {'':<28} "
                  f"not in JLC assembly library{rf(code)}")
            continue
        if h.get('library') == 'expand':
            ext += 1
        up = price_at(h.get('ladder') or [], buy_qty(qty, h.get('moq'), h.get('multiple')))
        st = h.get('stock')
        print(f"{code:<11} {('BASIC' if h.get('library')=='base' else 'ext'):<6} "
              f"{(f'{st:,}' if isinstance(st,int) else '?'):>10}  "
              f"{dmoney1(up,'USD',a):<12} {trunc(h.get('mpn'),28):<28} "
              f"{trunc(h.get('desc'),30)}{rf(code)}")
    if ext:
        print(f"\n  {ext} Extended line(s) -> {dmoney1(3.0*ext,'USD',a)} in JLC setup fees "
              f"(US$3 per unique Extended part, charged once per order)")
    return 0

def c_check(a):
    """One-shot sourcing triage for a whole board: LCSC pricing + JLC Basic/
    Extended status + missing-LCSC-code triage in a single table and a single
    pass over the netlist, instead of running `bom` then `jlc` separately and
    cross-referencing the two by eye. Same 'refuse to regex a .net' rule as
    `jlc`: a bare C\\d+ scan would mistake capacitor refdes (C108) for LCSC
    codes, so this needs knet.py to parse the 'LCSC Part' property properly."""
    if not a.args or not a.args[0].endswith('.net'):
        print("check: give a .net file, e.g. part.py check board.net --qty 5"); return 1
    src = a.args[0]
    nl = load_knet(src)
    if nl is None:
        print(f"check: could not parse {src} (kcommon.py not importable)"); return 1
    want, nocode, _, grp = _collect(nl, _sheet_rules(a))
    if not want:
        print("no LCSC codes found. netlist needs an 'LCSC Part' property"); return 1
    boards = a.qty or 1

    def one(item):
        code, refs = item
        return code, refs, lcsc_detail(code, a.fresh), jlc_detail(code, a.fresh)
    with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        results = list(ex.map(one, sorted(want.items())))

    rows, total, missing, ext_n = [], 0.0, [], 0
    jlc = {code: jh for code, _, _, jh in results}
    for code, refs, r, jh in results:
        if not r:
            missing.append(code); continue
        per = len(refs)
        need = _need(refs, grp, boards)
        q, up = best_buy(need, r.get('ladder'), r.get('moq'), r.get('multiple'))
        ext = (up or 0) * q
        total += ext
        lib = jh.get('library') if jh else None
        if lib == 'expand':
            ext_n += 1
        rows.append({'lcsc': code, 'mpn': r.get('mpn'), 'refs': refs, 'per_board': per,
                     'need': need, 'buy': q, 'unit': up, 'ext': ext, 'stock': r.get('stock'),
                     'package': r.get('package'),
                     'jlc': {'base': 'BASIC', 'expand': 'ext'}.get(lib, 'not in JLC lib' if jh else '?')})
    if a.json:
        print(json.dumps({'boards': boards, 'lines': rows,
                          'total_parts_usd': round(total, 4),
                          'extended_line_fee_usd': round(3.0 * ext_n, 2),
                          'unresolved': missing, 'jlc_only': [c for c in missing if jlc.get(c)],
                          'no_lcsc_code': sorted(nocode)}, indent=1))
        return
    print(f"{boards} board(s), {len(rows)} distinct LCSC parts\n")
    print(f"{'lcsc':<12} {'mpn':<24} {'pkg':<10} {'/bd':>4} {'buy':>7} {'unit':>10} "
          f"{'ext':>9}  {'stock':>9}  {'jlc':<14} refs")
    for r in sorted(rows, key=lambda x: -x['ext']):
        low = '  LOW STOCK' if isinstance(r['stock'], int) and r['stock'] < r['buy'] else ''
        st = r['stock']
        print(f"{r['lcsc']:<12} {trunc(r['mpn'],24):<24} {trunc(r['package'],10):<10} "
              f"{r['per_board']:>4} {r['buy']:>7} {dmoney1(r['unit'],'USD',a):>10} "
              f"{dmoney1(r['ext'],'USD',a):>9}  "
              f"{(f'{st:,}' if isinstance(st,int) else '?'):>9}  {r['jlc']:<14} "
              f"{' '.join(r['refs'][:6])}{low}")
        if low and third_note(lcsc_detail(r['lcsc']), r['buy']):
            print(f"{'':<12} {third_note(lcsc_detail(r['lcsc']), r['buy'])}")
    ct = conv(total, 'USD', a.currency)
    if a.currency != 'USD' and ct is not None:
        _FX['used'] = True
        print(f"\nparts cost: {money(ct, a.currency)} ({money(total,'USD')}) for {boards} board(s)")
    else:
        print(f"\nparts cost: {money(total,'USD')} for {boards} board(s)")
    if ext_n:
        print(f"assembly  : {ext_n} Extended line(s) -> {dmoney1(3.0*ext_n,'USD',a)} in JLC "
              f"setup fees (US$3/unique Extended part, charged once per order)")
    print("excludes shipping, tax, PCB fabrication and DNP parts")
    if missing:
        print()
        _missing(missing, a, jlc)
    if nocode:
        print(f"\n{len(nocode)} placed component(s) have NO LCSC part number - not costed "
              f"and cannot go to JLC assembly:\n  {' '.join(sorted(nocode))}")
    return 0
