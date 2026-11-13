"""kfp.py BOARD vendor [--lib NICK] [--models DIR] [--apply]: make a project self-contained.

Every footprint the board takes from a library outside the repo (not stock, not in the
project) is copied into the project library NICK (default: the one project fp-lib-table
library): the library file as is when the board copy matches it, else the board's own copy
in library form (a fix made on the board, so Update Footprint becomes a no-op; when the
board's instances differ, the first is written and the rest named). Every 3D model resolving
outside the repo (on any footprint) is copied into DIR (default: where the repo's models
already live, else lib/3dmodels) with its .step/.wrl siblings, its path written as
${KIPRJMOD}/... Lib IDs move to NICK on the board and in every schematic's Footprint field,
so Update PCB keeps them; NICK goes into the project fp-lib-table if missing.

Dry run by default: it prints every copy and edit. --apply writes them in place (refused while
KiCad holds the project, like kproj; --force overrides). A model file already in DIR that
differs is never overwritten: that path stays as it was. Then prove nothing else changed: `kfp.py BOARD libs`
(nothing outside the repo), `kverify.py .` (the schematics), `kpcb.py BOARD diff OLD` (only lib
ids and model paths). Also listed: symbol libraries resolving outside the repo (copying those
is not done here), and what Update Footprint from a stock library would change, by direction:
library-only items (stock moved on: worth pulling), board-only items (a local fix it would
undo), or both."""
import filecmp, glob, os, re, shutil
from collections import Counter
from kcommon import _lib_table, _global_cfg, expand_vars, fp_lib_dirs, kicad_env, kicad_running, natkey, refrange
from kfp import board_spans, dump, lib_copy, load, proj_of, q, u
from kfp_diff import canon

MODEL_EXT = ('.step', '.stp', '.wrl')


def _where_fn(proj):
    """path -> 'stock' | 'repo' | 'outside the repo'"""
    env = kicad_env(proj)
    stock = [os.path.realpath(d) for d in env['_stock'].values() if d]
    real = os.path.realpath(proj)

    def where(p):
        rp = os.path.realpath(p)
        if any(rp.startswith(s + os.sep) for s in stock):
            return 'stock'
        return 'repo' if rp.startswith(real + os.sep) else 'outside the repo'
    return where, env


def _model_path(w, env, proj):
    rp = expand_vars(w, env)
    if not os.path.isabs(rp) and '${' not in rp:
        rp = os.path.join(proj, rp)
    if os.path.isfile(rp):
        return rp
    return next((os.path.splitext(rp)[0] + e for e in MODEL_EXT if os.path.isfile(os.path.splitext(rp)[0] + e)), None)


def _same(A, B):
    """two canon()s equal except for 3D model paths (vendoring re-points those)"""
    return all(A[c] == B[c] for c in A if c != 'models')


def _rr(refs):
    refs = sorted(refs, key=natkey)
    return refrange(refs) if len(refs) > 1 else refs[0]


def c_vendor(a):
    proj = proj_of(a.file)
    where, env = _where_fn(proj)
    dirs = fp_lib_dirs(proj)
    local = {}
    _lib_table(os.path.join(proj, 'fp-lib-table'), env, local)
    repo_libs = [n for n, d in local.items() if where(d) == 'repo']
    nick = a.lib or (repo_libs[0] if len(repo_libs) == 1 else '')
    if not nick:
        print(f"vendor: name the project library with --lib (project fp-lib-table has: {' '.join(local) or 'none'})")
        return 1
    target = local.get(nick) or os.path.join(proj, 'lib', nick + '.pretty')
    spans, _mc = board_spans(a.file)
    use = {}
    for ref, txt in spans.items():
        m = re.match(r'\t?\(footprint "((?:[^"\\]|\\.)*)"', txt)
        use.setdefault(m.group(1) if m else '?', []).append(ref)
    # models: every one outside the repo, on any footprint
    mods = {}
    for ref, txt in spans.items():
        for w in re.findall(r'\(model "((?:[^"\\]|\\.)*)"', txt):
            rp = _model_path(w, env, proj)
            if rp and where(rp) == 'outside the repo':
                mods.setdefault(w, (rp, []))[1].append(ref)
    have = Counter(os.path.dirname(rp) for w, rp in ((w, _model_path(w, env, proj)) for t in spans.values()
                   for w in re.findall(r'\(model "((?:[^"\\]|\\.)*)"', t)) if rp and where(rp) == 'repo')
    mdir = a.models or (have.most_common(1)[0][0] if have else os.path.join(proj, 'lib', '3dmodels'))
    mdir = os.path.join(proj, mdir) if not os.path.isabs(mdir) else mdir
    newpath = {w: '${KIPRJMOD}/' + os.path.relpath(os.path.join(mdir, os.path.basename(rp)), proj)
               for w, (rp, _r) in mods.items()}
    copies, fpw, edits = {}, [], 0                 # copies: {dst: src}; fpw: (dst, text)
    for w, (rp, refs) in sorted(mods.items()):
        sib = {os.path.join(mdir, os.path.basename(s)): s for e in MODEL_EXT
               for s in [os.path.splitext(rp)[0] + e] if os.path.isfile(s)}
        clash = [d for d, s in sib.items() if os.path.isfile(d) and not filecmp.cmp(d, s, shallow=False)]
        if clash:                                  # never overwrite a different file already in the repo
            print(f"  KEEP {w}: {os.path.relpath(clash[0], proj)} exists and differs; this path stays as is ({_rr(refs)})")
            del newpath[w]
            continue
        copies.update({d: s for d, s in sib.items() if not os.path.isfile(d)})
    fix_models = lambda t: re.sub(r'\(model "((?:[^"\\]|\\.)*)"',                   # noqa: E731
                                  lambda m: f'(model "{newpath.get(m.group(1), m.group(1))}"', t)
    moved = {}                                     # old fpid -> new fpid
    print(f"vendor into {nick} ({os.path.relpath(target, proj)}), models into {os.path.relpath(mdir, proj)}")
    for fpid, refs in sorted(use.items()):
        lib, _, name = fpid.partition(':')
        d = dirs.get(lib)
        if not d or lib == nick or where(d) != 'outside the repo':
            continue
        fps = load(a.file, sorted(refs, key=natkey), proj)
        keys = [canon(f.t) for f in fps]
        odd = [f.ref for f, k in zip(fps, keys) if k != keys[0]]
        lf, _why = lib_copy(fpid, proj)
        same = lf is not None and canon(lf.t) == keys[0]
        dst = os.path.join(target, name + '.kicad_mod')
        if same:
            with open(lf.src, encoding='utf-8') as fh:
                body = fh.read()
            how = 'library file'
        else:
            t = fps[0].t
            with open(a.file, encoding='utf-8') as fh:
                vers = re.search(r'\(version (\d+)\)', fh.read(400))
            t = [t[0], t[1], ['version', vers.group(1) if vers else '20240108'], ['generator', q('kfp')]] + \
                [c for c in t[2:] if not (isinstance(c, list) and c and c[0] in ('version', 'generator'))]
            for c in t:
                if isinstance(c, list) and len(c) > 2 and c[0] == 'property' and u(c[1]) == 'Reference':
                    c[2] = q('REF**')
            body = dump(t) + '\n'
            how = f"{fps[0].ref}'s board copy (it differs from the library: kfp diff {fps[0].ref})"
        body = fix_models(body)
        if os.path.isfile(dst):
            if not _same(canon(load(dst)[0].t), keys[0]):
                print(f"  SKIP {fpid}: {nick} already has a different {name}.kicad_mod"); continue
            how = f"already in {nick}, re-pointed only"
        else:
            fpw.append((dst, body))
        moved[fpid] = f"{nick}:{name}"
        print(f"  footprint {fpid} -> {nick}:{name}  ({_rr(refs)}): {how}"
              + (f"; {' '.join(odd)} differ from it and keep their board copy" if odd else ''))
    print(f"  models: {len(copies)} file(s) from {', '.join(sorted({os.path.dirname(s) for s in copies.values()}))}, "
          f"{len(newpath)} path(s) re-pointed")
    for w, (rp, refs) in sorted(mods.items())[:a.max]:
        if w in newpath:
            print(f"    {w} -> {newpath[w]}  ({_rr(refs)})")
    if len(mods) > a.max:
        print(f"    ... +{len(mods) - a.max} more (--max)")
    # board and schematic edits
    with open(a.file, encoding='utf-8') as fh:
        btxt = fh.read()
    for ref, s in spans.items():
        m = re.match(r'\t?\(footprint "((?:[^"\\]|\\.)*)"', s)
        n = s
        if m and m.group(1) in moved:
            old, new = m.group(1), moved[m.group(1)]
            n = n.replace(f'(footprint "{old}"', f'(footprint "{new}"', 1).replace(
                f'(property "Footprint" "{old}"', f'(property "Footprint" "{new}"')
        n = fix_models(n)
        if n != s:
            btxt, k = btxt.replace(s, n, 1), btxt.count(s)
            if k != 1:
                raise SystemExit(f"vendor: {ref}'s footprint text is not unique on the board; nothing written")
            edits += 1
    sch = {}
    for p in sorted(glob.glob(os.path.join(proj, '**', '*.kicad_sch'), recursive=True)):
        if '-backups' in p or os.path.basename(p).startswith('_autosave'):
            continue
        with open(p, encoding='utf-8') as fh:
            s = fh.read()
        m = re.search(r'\n\t\(lib_symbols\n.*?\n\t\)\n', s, re.S)   # the cache stays the library's
        cut = m.end() if m else 0
        n, k = s[cut:], 0
        for old, new in moved.items():
            k += n.count(f'(property "Footprint" "{old}"')
            n = n.replace(f'(property "Footprint" "{old}"', f'(property "Footprint" "{new}"')
        if k:
            sch[p] = s[:cut] + n
            print(f"  schematic {os.path.relpath(p, proj)}: {k} Footprint field(s)")
    table = None
    if nick not in local:
        tp = os.path.join(proj, 'fp-lib-table')
        cur = open(tp, encoding='utf-8').read() if os.path.isfile(tp) else '(fp_lib_table\n\t(version 7)\n)\n'
        ent = (f'\t(lib (name "{nick}") (type "KiCad") (uri "${{KIPRJMOD}}/{os.path.relpath(target, proj)}") '
               '(options "") (descr ""))\n')
        table = (tp, cur[:cur.rstrip().rfind(')')] + ent + ')\n')
        print(f"  fp-lib-table: add {nick}")
    print(f"  board: {edits} footprint(s) re-pointed")
    _symbols(proj, env, where)
    _stock_rank(a, proj, use, where, dirs)
    if not (fpw or copies or edits or sch or table):
        print("nothing outside the repo: already self-contained"); return 0
    if not a.apply:
        print("(dry run: --apply writes all of it in place; first commit, so `kpcb.py BOARD diff OLD` has an OLD)")
        return 0
    busy = [] if a.force else kicad_running(proj)
    if busy:
        print("vendor: refused, " + '; '.join(busy)); return 3
    os.makedirs(target, exist_ok=True)
    os.makedirs(mdir, exist_ok=True)
    for dst, s in copies.items():
        shutil.copy2(s, dst)
    for dst, body in fpw:
        with open(dst, 'w', encoding='utf-8') as fh:
            fh.write(body)
    with open(a.file, 'w', encoding='utf-8') as fh:
        fh.write(btxt)
    for p, n in sch.items():
        with open(p, 'w', encoding='utf-8') as fh:
            fh.write(n)
    if table:
        with open(table[0], 'w', encoding='utf-8') as fh:
            fh.write(table[1])
    print(f"wrote {len(fpw)} footprint(s), {len(copies)} model file(s), the board, {len(sch)} schematic(s)"
          f"{', fp-lib-table' if table else ''}. Check: kfp.py {a.file} libs; kverify.py {proj}; kpcb.py {a.file} diff OLD")
    return 0


def _symbols(proj, env, where):
    """symbol libraries the schematics use that resolve outside the repo"""
    dirs = {}
    _lib_table(os.path.join(proj, 'sym-lib-table'), env, dirs)
    cfg = _global_cfg()
    if cfg:
        _lib_table(os.path.join(cfg, 'sym-lib-table'), env, dirs)
    used = Counter()
    for p in glob.glob(os.path.join(proj, '**', '*.kicad_sch'), recursive=True):
        if '-backups' not in p:
            with open(p, encoding='utf-8') as fh:
                used.update(re.findall(r'\(lib_id "([^":]+):', fh.read()))
    out = sorted(n for n in used if n in dirs and where(dirs[n]) == 'outside the repo')
    if out:
        print("  symbols from outside the repo (not copied: the schematic caches them): "
              + ', '.join(f"{n} ({used[n]})" for n in out))


def _other_stock(cur):
    """footprint dirs of the other KiCad installs (stable beside nightly): another stock version"""
    pats = ('/usr/share/kicad*/footprints', '/usr/local/share/kicad*/footprints',
            '/Applications/KiCad*/KiCad.app/Contents/SharedSupport/footprints', 'C:/Program Files/KiCad/*/share/kicad/footprints')
    return [d for p in pats for d in glob.glob(p) if os.path.realpath(d) != os.path.realpath(cur or '')]


def _stock_rank(a, proj, use, where, dirs):
    """stock footprints whose library file differs from the board copy. Direction comes from a
    second stock version (another KiCad install): the board equal to the older file = stock
    moved on (worth pulling); both stock files equal and the board not = a local fix that
    Update Footprint would undo. Only one stock version: just what differs."""
    from kfp import read_mod
    rows = []
    others = _other_stock(kicad_env(proj)['_stock'].get('FOOTPRINT'))
    for fpid, refs in use.items():
        d = dirs.get(fpid.partition(':')[0])
        if not d or where(d) != 'stock':
            continue
        lf, _why = lib_copy(fpid, proj)
        if lf is None:
            continue
        L = canon(lf.t)
        f = load(a.file, sorted(refs, key=natkey)[:1], proj)[0]
        B = canon(f.t)
        parts = []
        for c in ('pads', 'shapes', 'zones', 'type'):
            lo, bo = sum((L[c] - B[c]).values()), sum((B[c] - L[c]).values())
            if lo or bo:
                parts.append(f"{c} {lo} library-only / {bo} board-only")
        if not parts:
            continue
        olds = [canon(read_mod(p).t) for o in others
                for p in [os.path.join(o, os.path.basename(d), fpid.partition(':')[2] + '.kicad_mod')] if os.path.isfile(p)]
        cmp = lambda X, Y: all(X[c] == Y[c] for c in ('pads', 'shapes', 'zones', 'type'))   # noqa: E731
        v = ('worth pulling: the board matches the other install\'s older stock copy' if any(cmp(B, O) for O in olds) else
             'a local fix, stock unchanged: Update Footprint would undo it' if olds and all(cmp(L, O) for O in olds) else
             'both moved: stock changed and the board differs from either' if olds else
             'differs (one stock version installed, direction unknown)')
        rows.append((v, fpid, refs, ', '.join(parts)))
    if rows:
        print(f"  stock footprints Update Footprint would change ({len(rows)}; pads, graphics, rule areas, type; "
              f"compared with {len(others)} other install(s)):")
        for v, fpid, refs, parts in sorted(rows, key=lambda r: (r[0], r[1]))[:a.max]:
            print(f"    {fpid:<40} {_rr(refs):<11} {v}; {parts}")
