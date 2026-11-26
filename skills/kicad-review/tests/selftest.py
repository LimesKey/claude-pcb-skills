#!/usr/bin/env python3
"""Runnable self-test for the kicad-review tools: one command verifies a tool edit or a refactor.

    python3 tests/selftest.py              # every case and check, in parallel: FAIL lines + the total
    selftest.py -k smooth -k 'kpcb net'    # cases whose label contains one of these, + their inputs
    selftest.py --list                     # every case label and the file:line that writes it
    selftest.py -v                         # print the passing lines too
    selftest.py -j 1                       # one case at a time (to rule out a race between cases)
    selftest.py -k table --keep            # keep the temp dir (fixtures + outputs) to poke at by hand

Exit 0 = all pass, 1 = something regressed.

Where the cases live: one st_*.py per tool family, each holding the fixture builders only it
uses. st_common.py has the shared builders, run(), check() and the fixture paths (NET, PCB, ...:
the static fixtures below).

    st_knet.py        knet.py, kverify.py, kmerge.py
    st_kpcb.py        kpcb.py read-only commands (kpcb.md): check where zones ampacity view ...
    st_kpcb_route.py  kpcb.py copper: route ripup smooth stitch fatten widen tracks copper ...
    st_kpcb_edit.py   kpcb.py placement and edits: edit move movecheck place silk label diff ...
    st_sch.py         ksch.py, ksheet.py, kproj.py, kfront.py
    st_other.py       kfp.py, kdoc.py, kdrc.py

A case that shares a fixture with another lives beside it, so a few sit in a neighbour's file:
`--list | grep LABEL` gives the file:line. Add a case next to the one it resembles, in that
file's suite():

    CASES.append(("kpcb smooth --foo", ['kpcb.py', PCB, 'smooth', '--foo'], 0, ["shown", "!not shown"]))

That is (label, argv, expected exit, needles): each needle must appear in stdout+stderr, one
starting with '!' must not, and a callable gets the output and returns a problem ('' = fine).
An in-process check, or one comparing several outputs, goes after suite()'s `yield` as
`check(ok, "what it proves")`: the runner runs every suite's cases, then resumes each suite for
its checks. -k stops at the yield, so the checks run only in the full suite.

Cases run in parallel. Cases whose temp paths overlap (a writer and the reader of its output, or
a directory and a file inside it) form one chain that runs in order, so a case must name every
temp path it reads in its argv. -k uses the same rule to also run a picked case's writers.

Every tool command needs a case: the coverage check fails on a command (a tool's CMDS key or
--help choice) that no case's argv names, or that the tool's references/*.md never mentions.

Fixtures. selftest.kicad_pcb is a 40x30 mm board carrying one deliberate fault per rule,
including both EDGECLR severities (R4 crosses, R5 is merely close), both CONNACC halves (J1
buried, J3's exit blocked by C2) and both OVERLAP cases (R1/R2 same side, TP1's drill under U1
from the back). If a rule stops firing on it, the rule is dead: a clean board reports nothing,
which looks the same as a broken check. selftest_nightly.kicad_pcb is the same board in 10.99
`(transform ...)` form and must give an identical `check`; then selftest.net,
selftest_amp2/selftest_cross.kicad_pcb (ampacity) and selftest_repeat/ (one sheet used twice).
`sync` on the two static fixtures is the negative test: they are deliberately different
circuits, so all five SYNC rules fire at once. The builders (`*_board`, `*_net`, `*_project`)
each write one small file per behaviour into the temp dir, their docstring or comment saying
what it carries: extend the one a command's cases already use, or write a sibling beside it.
kdoc's cases run on `kdoc_docs` (an uploader page container and a csv, in a temp KDOC_CACHE);
real-PDF extraction (pdftotext) is not covered.

Covered by the goldens on a real board instead: what drives kicad-cli (NO_CASE: kdrc
drc/erc/doctor, `kpcb height`, `kfp view`, `ksheet view`; and kmerge), and `ic`, since the
fixture has no regulator. `ic` must list the switchers there, and `ic <a buck>` must name an
input cap, an inductor and a feedback part and print a diagram whose IC body is visible inside
the frame (a blank-looking frame: the anchor shift reached the slots but not the IC's geometry).

Refactor safety net on a REAL board (fixtures only prove the rules fire):

    selftest.py --golden DIR BOARD.kicad_pcb BOARD.net [EXTRA.json]

The first run records GOLDEN (read-only commands, no kicad-cli) into DIR; every
later run diffs against it and exits 1 on any change. EXTRA.json adds the board's
own commands (the ones naming a ref, pad or net), a list of argv lists with {pcb}
and {net} placeholders: [["kpcb.py", "{pcb}", "ic", "U13"], ...]. Record before a refactor,
check after: a pure refactor must be byte-identical. Delete DIR to re-record.
"""
import ast, os, re, sys, glob, json, tempfile
import st_common
from st_common import CASES, CHECKS, S, SK, TMP, check, mini_project, run
import st_knet, st_kpcb, st_kpcb_route, st_kpcb_edit, st_sch, st_other

SUITES = (st_knet, st_kpcb, st_kpcb_route, st_kpcb_edit, st_sch, st_other)








































































# ---- 2026-10-19 backlog pass: typed DRU rules, drag, prune, smooth/tracks/widen/loops, silk

































# ---- 2026-10-27 backlog pass







































# any board: no ref, pad or net name (GND aside). A board's own go in EXTRA.json.
GOLDEN = [['kpcb.py', '{pcb}', c] for c in ('summary', 'check', 'span', 'zones', 'rf', 'viapad', 'ic',
                                            'height', 'unplaced', 'sheet', 'map', 'review', 'assembly')] \
    + [['kpcb.py', '{pcb}', 'sync', '{net}'], ['kpcb.py', '{pcb}', 'check', '--json']] \
    + [['knet.py', '{net}', c] for c in ('summary', 'check', 'rails', 'revpol', 'unconnected', 'bom',
                                         'powertree', 'i2c')] \
    + [['kpcb.py', '{pcb}', 'zones', '--voids'], ['kpcb.py', '{pcb}', 'net', 'GND'],
       ['ksheet.py', '{net}', 'lint'],
       ['kpcb.py', '{pcb}', 'congest', '--all'], ['kpcb.py', '{pcb}', 'tracks'], ['kpcb.py', '{pcb}', 'silk']]

def golden(d, pcb, net, extra=None):
    """Record GOLDEN (+ extra's argv lists) outputs into d, or diff against what d holds."""
    import difflib
    rec = not os.path.isdir(d) or not os.listdir(d)
    os.makedirs(d, exist_ok=True)
    bad = 0
    from concurrent.futures import ThreadPoolExecutor
    todo = GOLDEN + (json.load(open(extra)) if extra else [])
    assert all(isinstance(a, list) and a and a[0] in os.listdir(S) for a in todo), f"{extra}: [[tool.py, args..], ..]"
    argvs = [[x.format(pcb=pcb, net=net) for x in argv] for argv in todo]
    with ThreadPoolExecutor(min(8, os.cpu_count() or 1)) as ex:    # read-only commands, ~400 MB each
        outs = list(ex.map(run, argvs))
    for argv, (code, out) in zip(argvs, outs):
        out = f"{out}\nexit={code}\n"
        f = os.path.join(d, '_'.join(argv[0:1] + argv[2:]).replace('.py', '') + '.txt')
        if rec:
            open(f, 'w').write(out)
            continue
        old = open(f).read() if os.path.exists(f) else ''
        if old != out:
            bad += 1
            diff = list(difflib.unified_diff(old.splitlines(), out.splitlines(), 'golden', 'now', n=0, lineterm=''))
            print(f"CHANGED  {' '.join(argv)}  ({len(diff)} diff lines)")
            print('\n'.join('    ' + x for x in diff[2:14]))
        else:
            print(f"same     {' '.join(argv)}")
    print(f"\nrecorded {len(todo)} outputs in {d}" if rec else f"\n{len(todo) - bad}/{len(todo)} unchanged")
    return 1 if bad else 0


def router_lint():
    """SKILL.md is the router. Its description must fit the spec's 1024 chars (claude.ai
    refuses more, Claude Code clips the listing), and every link, reference file and
    `tool.py FILE cmd` it names must exist (commands from each tool's --help choices)."""
    t = open(os.path.join(SK, 'SKILL.md')).read()
    desc = ' '.join(t.split('\n---', 1)[0].split('description: >-', 1)[1].split())
    bad = [f'description {len(desc)} chars > 1024'] if len(desc) > 1024 else []
    docs = [os.path.join(SK, 'SKILL.md')] + sorted(glob.glob(os.path.join(SK, 'references', '*.md')))
    for d in docs:
        bad += [f'{os.path.basename(d)} links {ln}' for ln in re.findall(r'\]\(([^)#\s]+)', open(d).read())
                if '://' not in ln and not os.path.exists(os.path.join(os.path.dirname(d), ln))]
    bad += [f'{os.path.basename(d)} not linked from SKILL.md' for d in docs[1:]
            if f'(references/{os.path.basename(d)})' not in t]
    calls, wrong = bad_calls(t, 'SKILL.md')
    return bad + wrong, calls, len(desc)

HELP = {}                       # tool -> its subcommands (None: it has none, or they cannot be read)

def commands(tool):
    """tool's subcommands: its CMDS dict's keys, else the {a,b,..} choices its --help usage
    shows, else the list an unknown command prints. (Most tools print their docstring for
    --help, so the usage alone missed kpcb's and knet's.)"""
    if tool not in HELP:
        keys, src = None, os.path.join(S, tool + '.py')
        for n in ast.parse(open(src).read()).body if os.path.exists(src) else ():
            if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'CMDS' and isinstance(n.value, ast.Dict):
                keys = [k.value for k in n.value.keys if isinstance(k, ast.Constant)]
        if keys is None:
            sets = re.findall(r'\{(\w[\w-]*(?:,[\w-]+)+)\}', run([tool + '.py', '--help'])[1])
            keys = max((x.split(',') for x in sets), key=len, default=None)
        if keys is None:
            m = re.search(r"unknown command '__nope__' \(([\w-]+(?: \| [\w-]+)+)\)", run([tool + '.py', '__nope__'])[1])
            keys = m.group(1).split(' | ') if m else None
        HELP[tool] = keys
    return HELP[tool]

def bad_calls(text, where):
    """Every `tool.py FILE cmd` in text (FILE, DIR or a .net/.kicad_*/.pretty path) whose cmd is
    not one of that tool's --help choices. Returns (calls found, problems)."""
    calls = set(re.findall(r'`(k\w+)\.py (?:(?:FILE|DIR|\S+\.(?:net|kicad_pcb|kicad_sch|kicad_mod|pretty))\S*\s+)?([a-z][\w-]*)(?![\w.-])',
                           text))
    bad = []
    for tool, cmd in sorted(calls):
        if commands(tool) is not None and cmd not in HELP[tool]:
            bad.append(f'{where} names `{tool}.py {cmd}`: not a {tool} command')
    return len(calls), bad

def hard_imports():
    """`file:line module` for every import outside the stdlib and these scripts that is not
    under a `try:` catching ImportError: the tools promise to run on a bare python3 (numpy in
    kpcb_fillet once broke every zone writer on a Python without it)"""
    import ast
    std = set(sys.stdlib_module_names) | {os.path.splitext(os.path.basename(x))[0]
                                          for x in glob.glob(os.path.join(SK, '..', '*', '*', '*.py'))}
    out = []
    for p in sorted(glob.glob(os.path.join(SK, '..', '*', 'scripts', '*.py'))
                    + glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), '*.py'))):
        tree = ast.parse(open(p).read())
        soft = {id(n) for t in ast.walk(tree) if isinstance(t, ast.Try) and any(
                    'ImportError' in ast.unparse(h.type or ast.Name('BaseException')) for h in t.handlers)
                for b in t.body for n in ast.walk(b)}
        for n in ast.walk(tree):
            mods = ([a.name for a in n.names] if isinstance(n, ast.Import) else
                    [n.module] if isinstance(n, ast.ImportFrom) and n.module and not n.level else [])
            out += [f"{os.path.basename(p)}:{n.lineno} {m}" for m in mods
                    if m.split('.')[0] not in std and id(n) not in soft]
    return out



SRC = {}                        # tool -> its source text

def temp_paths(c, env=()):
    """the temp paths a case reads or writes: the ones in its argv, plus each (VAR, path) of
    env whose VAR its tool's source names (KDOC_CACHE: kdoc's cases share one cache)"""
    t = {x for x in c[1] if isinstance(x, str) and x.startswith(TMP)}
    if env and c[1][0] not in SRC:
        p = os.path.join(S, c[1][0])
        SRC[c[1][0]] = open(p).read() if os.path.exists(p) else ''
    return t | {v for k, v in env if k in SRC[c[1][0]]}

def suite_env(tmp):
    """the environment variables the suites point into the temp dir"""
    return tuple((k, v) for k, v in os.environ.items() if v.startswith(tmp.name))

def overlap(a, b):
    """two cases' temp paths meet: the same path, or a directory and a path inside it"""
    return any(x == y or x.startswith(y + os.sep) or y.startswith(x + os.sep) for x in a for y in b)

def with_inputs(cases, keep, env=()):
    """The kept cases plus every earlier case one shares a temp path with (the writer of
    its input, or an in-place edit before it), transitively, so any case runs alone."""
    toks = [temp_paths(c, env) for c in cases]
    for j in range(len(cases) - 1, -1, -1):
        if j in keep:
            keep |= {i for i in range(j) if overlap(toks[i], toks[j])}
    return [c for i, c in enumerate(cases) if i in keep]

def run_cases(cases, jobs, env=()):
    """(exit code, output) per case, `jobs` at a time. Cases whose temp paths overlap form one
    chain that runs in order (a writer before the reader of its output); chains run in parallel."""
    toks = [temp_paths(c, env) for c in cases]
    head = list(range(len(cases)))
    def find(i):
        while head[i] != i:
            head[i] = head[head[i]]; i = head[i]
        return i
    for j in range(len(cases)):
        for i in range(j):
            if toks[i] and toks[j] and overlap(toks[i], toks[j]):
                head[find(j)] = find(i)
    chains = {}
    for i in range(len(cases)):
        chains.setdefault(find(i), []).append(i)
    res = [None] * len(cases)
    def go(chain):
        for i in chain:
            res[i] = run(cases[i][1])
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max(1, jobs)) as ex:
        list(ex.map(go, sorted(chains.values(), key=len, reverse=True)))
    return res

def problems(case, code, out):
    """what is wrong with one case's result: its exit code, a needle missing, a '!needle'
    present, or what a callable needle returns"""
    want = case[2]
    prob = [f"exit {code} != {want}"] if code != want else []
    for n in case[3]:
        if callable(n):
            prob += [p for p in [n(out)] if p]
        elif n.startswith('!'):
            prob += [f"unwanted {n[1:]!r}"] if n[1:] in out else []
        elif n not in out:
            prob.append(f"missing {n!r}")
    return prob

NO_CASE = {                     # commands the fixture run cannot cover: they drive kicad-cli (CI has none)
    'kdrc.py': {'both', 'drc', 'erc', 'doctor'}, 'kpcb.py': {'height'}, 'kfp.py': {'view'}, 'ksheet.py': {'view'}}

def coverage_lint():
    """Every subcommand a tested tool's --help offers is named by some case's argv, and by the
    tool's references/TOOL.md (kpcb: kpcb.md or kpcb-writers.md) when it has one."""
    bad = []
    for tool in sorted({c[1][0] for c in CASES}):
        stem = tool[:-3]
        named = {a for c in CASES if c[1][0] == tool for a in c[1] if isinstance(a, str)}
        refs = [os.path.join(SK, 'references', f) for f in (f'{stem}.md', f'{stem}-writers.md')]
        doc = ''.join(open(r).read() for r in refs if os.path.exists(r))
        for cmd in commands(stem) or ():
            if cmd not in named and cmd not in NO_CASE.get(tool, ()):
                bad.append(f'{tool} {cmd}: no case runs it')
            if doc and not re.search(rf'(?<![\w-]){re.escape(cmd)}(?![\w-])', doc):
                bad.append(f'{tool} {cmd}: not in references/{stem}.md')
    return bad

def main(pick=(), listing=False, keep=False, verbose=False, jobs=os.cpu_count() or 4):
    st_common.VERBOSE = verbose or bool(pick)
    if not listing:
        rb, nc, nd = router_lint()
        ok20 = not rb and nc >= 30           # >= 30: the call regex still finds the router's calls
        check(ok20, f"router: description {nd} chars, {nc} tool calls named, links resolve"
                  + ''.join(f'\n      {b}' for b in rb))
        hard = hard_imports()
        check(not hard, "stdlib only: every other import is optional (try/except ImportError)"
                  + ''.join(f'\n      {b}' for b in hard))
    tmp = tempfile.TemporaryDirectory(delete=not keep)
    if keep:
        print(f"--keep: fixtures and case outputs stay in {tmp.name}")
    mini = mini_project(tmp.name)
    suites = [m.suite(tmp, mini) for m in SUITES]
    for s in suites:
        next(s)                        # each appends its cases and stops at its yield
    if listing:
        w = max(len(c[0]) for c in CASES)
        print('\n'.join(f"{c[0]:<{w}}  {CASES.where.get(c[0], '')}" for c in CASES)); return 0
    cov = coverage_lint()
    check(not cov, "coverage: every tool command has a case and a line in its reference"
          + ''.join(f'\n      {b}' for b in cov))
    if pick:                       # -k: matching cases only; the ad-hoc checks below read every case's output
        CASES[:] = with_inputs(CASES, {i for i, c in enumerate(CASES) if any(k in c[0] for k in pick)},
                               suite_env(tmp))
    import shutil
    if not shutil.which('rsvg-convert'):     # a PNG view needs it, and the docs call it optional
        png = [c for c in CASES if 'view' in c[1] and any(str(a).endswith('.png') for a in c[1])]
        CASES[:] = [c for c in CASES if c not in png]
        print(f"skip  {len(png)} PNG view case(s): rsvg-convert not installed")
    fails = 0
    for c, (code, out) in zip(CASES, run_cases(CASES, jobs, suite_env(tmp))):
        prob = problems(c, code, out)
        if prob:
            fails += 1
            print(f"FAIL  {c[0]}: {'; '.join(prob)}")
        elif st_common.VERBOSE:
            print(f"ok    {c[0]}")
    if pick:
        fails += CHECKS.count(False)
        n = len(CASES) + len(CHECKS)
        print(f"\n{n - fails}/{n} passed (-k {' '.join(pick)}: the ad-hoc checks are skipped, the full run"
              f" is the gate)" if CASES else f"no case label contains {pick} (--list names them)")
        return 1 if fails or not CASES else 0
    for s in suites:
        next(s, None)                  # resume: each file's ad-hoc checks
    fails += CHECKS.count(False)
    n = len(CASES) + len(CHECKS)
    print(f"\n{n - fails}/{n} passed")
    return 1 if fails else 0

if __name__ == '__main__':
    if sys.argv[1:2] == ['--lint']:           # command names in other docs (CLAUDE.md, agents)
        probs = [b for f in sys.argv[2:] for b in bad_calls(open(f).read(), f)[1]]
        print('\n'.join(probs) or f"lint: every tool command named in {len(sys.argv) - 2} file(s) exists")
        sys.exit(1 if probs else 0)
    if sys.argv[1:2] == ['--golden'] and len(sys.argv) in (5, 6):
        sys.exit(golden(*sys.argv[2:6]))
    args = sys.argv[1:]
    opt = lambda f: [v for k, v in zip(args, args[1:]) if k == f]   # noqa: E731
    sys.exit(main(opt('-k'), '--list' in args, '--keep' in args, '-v' in args,
                  int(opt('-j')[-1]) if opt('-j') else os.cpu_count() or 4))
