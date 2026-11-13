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
ids and model paths). Symbols the same way (see _sym_plan): from a library outside the repo or
edited in the schematic, the cached copy goes into --symlib NICK. Also listed: what Update
Footprint from a stock library would change, by direction:
library-only items (stock moved on: worth pulling), board-only items (a local fix it would
undo), or both."""
import filecmp, glob, json, os, re, shutil, subprocess, tempfile
from collections import Counter
from kcommon import (_lib_table, _global_cfg, expand_vars, fp_lib_dirs, kicad_cli, kicad_env, kicad_running, natkey,
                     project_root, refrange)
from kfp import board_spans, dump, lib_copy, load, proj_of, q, u
from kfp_diff import canon

MODEL_EXT = ('.step', '.stp', '.wrl')
_STR = r'"((?:[^"\\]|\\.)*)"'                   # a quoted atom, escapes kept
SYMLIB_NEW = '(kicad_symbol_lib\n\t(version 20251024)\n\t(generator "kfp")\n\t(generator_version "10.0")\n)\n'  # 10.0's


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
    return refrange(refs) if len(refs) > 1 else refs[0] if refs else '-'


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
    copies, fpw, edits, kept = {}, [], 0, 0        # copies: {dst: src}; fpw: (dst, text)
    for w, (rp, refs) in sorted(mods.items()):
        sib = {os.path.join(mdir, os.path.basename(s)): s for e in MODEL_EXT
               for s in [os.path.splitext(rp)[0] + e] if os.path.isfile(s)}
        clash = [d for d, s in sib.items() if os.path.isfile(d) and not filecmp.cmp(d, s, shallow=False)]
        if clash:                                  # never overwrite a different file already in the repo
            print(f"  KEEP {w}: {os.path.relpath(clash[0], proj)} exists and differs; this path stays as is ({_rr(refs)})")
            del newpath[w]
            kept += 1
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
    print(f"  models: {len(copies)} file(s)" + (f" from {', '.join(sorted({os.path.dirname(s) for s in copies.values()}))}"
                                                 if copies else '') + f", {len(newpath)} path(s) re-pointed")
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
    block, sch, libs, stable, slines = _sym_plan(a, proj, env, where, moved)
    for p in _schematics(proj):
        if p in sch:
            s = sch[p]
        else:
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
    for ln in slines:
        print(ln)
    table = None
    if nick not in local:
        tp = os.path.join(proj, 'fp-lib-table')
        cur = open(tp, encoding='utf-8').read() if os.path.isfile(tp) else '(fp_lib_table\n\t(version 7)\n)\n'
        ent = (f'\t(lib (name "{nick}") (type "KiCad") (uri "${{KIPRJMOD}}/{os.path.relpath(target, proj)}") '
               '(options "") (descr ""))\n')
        table = (tp, cur[:cur.rstrip().rfind(')')] + ent + ')\n')
        print(f"  fp-lib-table: add {nick}")
    print(f"  board: {edits} footprint(s) re-pointed")
    _stock_rank(a, proj, use, where, dirs)
    if not (fpw or copies or edits or sch or table or libs or stable or block):
        print(f"nothing more to vendor ({kept} model path(s) kept outside: KEEP above)" if kept else
              "nothing outside the repo: already self-contained"); return 0
    if block:
        print(f"vendor: {block}" + ('; nothing written' if a.apply else ''))
        return 1
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
    for path, txt in [*libs.items(), *([table] if table else []), *([stable] if stable else [])]:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(txt)
    print(f"wrote {len(fpw)} footprint(s), {len(libs)} symbol librar{'y' if len(libs) == 1 else 'ies'}, {len(copies)} "
          f"model file(s), the board, {len(sch)} schematic(s){', fp-lib-table' if table else ''}"
          f"{', sym-lib-table' if stable else ''}. Check: kfp.py {a.file} libs; kverify.py {proj}; kpcb.py {a.file} diff OLD")
    return 0


def _schematics(proj):
    return [p for p in sorted(glob.glob(os.path.join(proj, '**', '*.kicad_sch'), recursive=True))
            if '-backups' not in p and not os.path.basename(p).startswith(('_autosave', '~'))]


def _blocks(txt, ind, lo=0, hi=None):
    """[(start, end, raw name)] of the `(symbol "NAME"` nodes `ind` tabs deep (KiCad's own
    layout: a node with children closes on a line of its own at its indent)"""
    pre = '\n' + '\t' * ind
    out = []
    for m in re.compile(re.escape(pre) + r'\(symbol ' + _STR).finditer(txt, lo, len(txt) if hi is None else hi):
        s = m.start() + 1
        out.append((s, txt.index(pre + ')', s) + len(pre) + 1, m.group(1)))
    return out


def _units(t, item, name):
    """unit names ITEM_u_s -> NAME_u_s (KiCad refuses a unit not prefixed by its symbol's name)"""
    return re.sub(r'\(symbol "' + re.escape(item) + r'(_\d+_\d+")', lambda m: '(symbol "' + name + m.group(1), t)


def _fp_field(t, moved):
    return re.sub(r'\(property "Footprint" ' + _STR, lambda m: f'(property "Footprint" "{moved.get(m.group(1), m.group(1))}"', t)


def _lib_form(txt, ind, item, name, moved):
    """a symbol node `ind` tabs deep as a top-level library symbol NAME: its units renamed with
    it, the Reference value cut to its prefix (a cache holds a placed one, "U8"), footprints
    re-pointed as on the board"""
    t = '\n'.join(ln[ind - 1:] for ln in txt.split('\n'))
    t = _units(f'\t(symbol "{name}"' + t[t.index('\n'):], item, name)
    t = re.sub(r'(\(property "Reference" )' + _STR, lambda m: m.group(1) + '"' + re.sub(r'[\d?]+$', '', m.group(2)) + '"',
               t, count=1)
    return _fp_field(t, moved)


def _erc_mismatch(a, proj):
    """(uuids of the placed symbols ERC calls lib_symbol_mismatch, '') - KiCad's own compare of a
    schematic's cached copy with the library - or (None, why not)"""
    path, tmp = a.erc, None
    if not path:
        root = project_root(proj)
        if not root:
            return None, 'no root schematic'
        fd, tmp = tempfile.mkstemp(suffix='.json', prefix='kfp_erc_')
        os.close(fd)
        root = os.path.join(proj, root)
        try:
            subprocess.run([kicad_cli(root), 'sch', 'erc', '--format', 'json', '--severity-all', '-o', tmp, root],
                           capture_output=True, text=True)
        except OSError as e:
            os.remove(tmp)
            return None, f'kicad-cli: {e}'
        path = tmp
    try:
        with open(path, encoding='utf-8') as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return None, 'kicad-cli ERC gave no report'
    finally:
        if tmp:
            os.remove(tmp)
    return {i.get('uuid') for s in d.get('sheets', []) for v in s.get('violations', [])
            if v.get('type') == 'lib_symbol_mismatch' for i in v.get('items', [])}, ''


def _sym_plan(a, proj, env, where, moved):
    """Symbols to vendor: those from a library outside the repo, and those ERC finds edited in
    the schematic (lib_symbol_mismatch), whatever their library. Each schematic's cached copy
    is the one written, into the project library NICK (--symlib, default the one project
    sym-lib-table library in the repo) under its library name; a second version of one name
    (two sheets, or KiCad's NAME_1) gets NAME_1, NAME_2. NICK's own copy of a name is replaced when
    no symbol in the project uses it, else the new one takes the next free name. Then lib_id
    moves to NICK:NAME on every instance and in each cache (lib_name dropped), and Footprint
    fields in the copied symbols follow the vendored footprints in both places, so ERC sees
    library and cache equal. A symbol whose library is in no table is only counted. Returns
    (why --apply must refuse or '', {schematic: text}, {library: text}, sym-lib-table (path,
    text) or None, report lines)."""
    local, dirs = {}, {}
    _lib_table(os.path.join(proj, 'sym-lib-table'), env, local)
    _lib_table(os.path.join(proj, 'sym-lib-table'), env, dirs)
    cfg = _global_cfg()
    if cfg:
        _lib_table(os.path.join(cfg, 'sym-lib-table'), env, dirs)
    repo = [n for n, d in local.items() if where(d) == 'repo']
    nick = a.symlib or (repo[0] if len(repo) == 1 else '')
    block = ''
    if nick in local and where(local[nick]) != 'repo':
        block = f"--symlib {nick} resolves outside the repo ({local[nick]})"
    target = local.get(nick) or os.path.join(proj, 'lib', nick + '.kicad_sym')
    if nick and os.path.isdir(target):
        block = f"{nick} is a .kicad_symdir library (one file per symbol): not written by this tool"
    texts, entries, placed = {}, [], []
    for p in _schematics(proj):
        with open(p, encoding='utf-8') as fh:
            txt = texts[p] = fh.read()
        m = re.search(r'\n\t\(lib_symbols\n.*?\n\t\)\n', txt, re.S)
        if m:
            entries += [(p, s, e, key) for s, e, key in _blocks(txt, 2, m.start(), m.end())]
        for pm in re.finditer(r'\n\t\(symbol\n', txt):
            s = pm.start() + 1
            b = txt[s:txt.index('\n\t)', s) + 3]
            one = {t: (re.search(r'\n\t\t\(' + t + ' ' + _STR + r'\)', b) or [None, None])[1]
                   for t in ('lib_name', 'lib_id', 'uuid')}
            refs = set(re.findall(r'\(reference ' + _STR + r'\)', b)) or \
                set(re.findall(r'\(property "Reference" ' + _STR, b)[:1])
            if one['lib_id']:
                placed.append(dict(one, sch=p, s=s, e=s + len(b), key=one['lib_name'] or one['lib_id'], refs=refs))
    edited, why_not = _erc_mismatch(a, proj)
    users = {}
    for pl in placed:
        users.setdefault((pl['sch'], pl['key']), []).append(pl)
    vend, missing = [], Counter()
    for p, s, e, key in entries:
        us = users.get((p, key))
        if not us:
            continue                                  # unused: KiCad drops it on the next save
        lib = us[0]['lib_id'].partition(':')[0]
        ed = bool(edited) and any(x['uuid'] in edited for x in us)
        if lib not in dirs:
            missing[lib] += len(us)
            continue
        out = where(dirs[lib]) == 'outside the repo'
        if out or ed:
            vend.append(dict(sch=p, s=s, e=e, key=key, item=key.partition(':')[2] or key, lib_id=us[0]['lib_id'],
                             var=bool(us[0]['lib_name']),
                             refs={r for x in us for r in x['refs']},
                             why=', '.join(['outside the repo'] * out + ['edited in the schematic'] * ed)))
    for v in vend:
        v['canon'] = _lib_form(texts[v['sch']][v['s']:v['e']], 2, v['item'], '@', moved)
    lines = []
    if missing:
        lines.append("  symbols whose library is in no sym-lib-table here (not vendored): "
                     + ', '.join(f"{n} ({k})" for n, k in sorted(missing.items())))
    if edited is None:
        lines.append(f"  in-schematic symbol edits not checked ({why_not}): only outside-the-repo symbols listed; "
                     "--erc REPORT.json reads a saved kicad-cli ERC report")
    if not vend:
        return '', {}, {}, None, lines
    if not nick:
        return (f"name the project symbol library with --symlib (sym-lib-table has: {' '.join(local) or 'none'})",
                {}, {}, None, lines + [f"  symbols to vendor: {len({v['lib_id'] for v in vend})}: "
                                       + ' '.join(sorted({v['lib_id'] for v in vend}, key=natkey))])
    libtxt = open(target, encoding='utf-8').read() if os.path.isfile(target) else SYMLIB_NEW
    have = {n: (s, e) for s, e, n in _blocks(libtxt, 1)}
    extended = set(re.findall(r'\(extends ' + _STR + r'\)', libtxt))
    vkeys = {(v['sch'], v['key']) for v in vend}
    used = {pl['lib_id'].partition(':')[2] for pl in placed
            if pl['lib_id'].partition(':')[0] == nick and (pl['sch'], pl['key']) not in vkeys}
    name_of, act = {}, {}                             # canon -> name; name -> (what, library text)
    for v in sorted(vend, key=lambda v: v['var']):   # KiCad's NAME_1 variants after the plain ones
        if v['canon'] in name_of:
            v['name'] = name_of[v['canon']]
            continue
        base = v['lib_id'].partition(':')[2]
        for k in range(99):
            n = f"{base}_{k}" if k else base
            if n in act:
                continue
            if n in have:
                s, e = have[n]
                if _lib_form(libtxt[s:e], 1, n, '@', {}) == v['canon']:
                    act[n] = ('same', '')
                    break
                if n in used or n in extended:
                    continue
                act[n] = ('replace', v['canon'].replace('(symbol "@', f'(symbol "{n}'))
                break
            act[n] = ('new', v['canon'].replace('(symbol "@', f'(symbol "{n}'))
            break
        v['name'] = name_of[v['canon']] = n
    for (lib_id, n), vs in sorted(_group(vend).items(), key=lambda x: natkey(x[0][0])):
        nk = f"{nick}:{n}"
        what = act[n][0]
        lines.append(f"  symbol {lib_id}" + (f" -> {nk}" if nk != lib_id else '')
                     + f"  ({_rr({r for v in vs for r in v['refs']})}): {vs[0]['why']}"
                     + {'same': f"; already in {nick}, re-pointed only", 'new': '',
                        'replace': "; the schematic's copy replaces the library's" if nk == lib_id else
                        f"; replaces {nick}'s own {n} (no symbol in the project uses that copy)"}[what])
    # the library: replacements in place (back to front), new ones appended
    for n, (s, e) in sorted(have.items(), key=lambda x: -x[1][0]):
        if act.get(n, ('',))[0] == 'replace':
            libtxt = libtxt[:s] + act[n][1] + libtxt[e:]
    new = [t for w, t in act.values() if w == 'new']
    if new:
        body = libtxt.rstrip()[:-1].rstrip('\n')
        libtxt = body + '\n' + '\n'.join(new) + '\n)\n'
    libs = {target: libtxt} if any(w != 'same' for w, _t in act.values()) else {}
    # the schematics: cache entries renamed (a duplicate of one already there dropped), instances re-pointed
    sch = {}
    for p in sorted({v['sch'] for v in vend}):
        txt, reps = texts[p], []
        keys = {key for q, _s, _e, key in entries if q == p}
        mine = {v['key']: v for v in vend if v['sch'] == p}
        done = set()
        for v in sorted(mine.values(), key=lambda v: v['s']):
            nk = f"{nick}:{v['name']}"
            if nk in done or (nk in keys and nk not in mine):
                reps.append((v['s'] - 1, v['e'], ''))  # its newline too
                continue
            done.add(nk)
            t = _units(f'\t\t(symbol "{nk}"' + txt[txt.index('\n', v['s']):v['e']], v['item'], v['name'])
            reps.append((v['s'], v['e'], _fp_field(t, moved)))
        for pl in placed:
            if pl['sch'] == p and pl['key'] in mine:
                b = re.sub(r'\n\t\t\(lib_name ' + _STR + r'\)', '', txt[pl['s']:pl['e']], count=1)
                b = re.sub(r'(\n\t\t\(lib_id )' + _STR, lambda m: m.group(1) + f'"{nick}:{mine[pl["key"]]["name"]}"', b,
                           count=1)
                reps.append((pl['s'], pl['e'], b))
        for s, e, t in sorted(reps, reverse=True):
            txt = txt[:s] + t + txt[e:]
        sch[p] = txt
    nw = sum(w != 'same' for w, _t in act.values())
    lines.append(f"  symbols: {nw} written into {nick} ({os.path.relpath(target, proj)}"
                 + (f", {sum(w == 'replace' for w, _t in act.values())} replacing its own copy" if nw else '')
                 + f"), {sum(len(v['refs']) for v in vend)} instance(s) re-pointed in {len(sch)} schematic(s)")
    table = None
    if nick not in local:
        tp = os.path.join(proj, 'sym-lib-table')
        cur = open(tp, encoding='utf-8').read() if os.path.isfile(tp) else '(sym_lib_table\n\t(version 7)\n)\n'
        table = (tp, cur[:cur.rstrip().rfind(')')] + f'\t(lib (name "{nick}") (type "KiCad") (uri "${{KIPRJMOD}}/'
                 f'{os.path.relpath(target, proj)}") (options "") (descr ""))\n)\n')
        lines.append(f"  sym-lib-table: add {nick}")
    return block, sch, libs, table, lines


def _group(vend):
    out = {}
    for v in vend:
        out.setdefault((v['lib_id'], v['name']), []).append(v)
    return out


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
