#!/usr/bin/env python3
"""usage.py - how Claude sessions used these skills, mined from Claude Code's transcripts.

  tools/usage.py PROJECT_DIR [--since YYYY-MM-DD] [--dev] [--max N]
  tools/usage.py --selftest

PROJECT_DIR is the directory Claude Code ran in (its transcripts live in
~/.claude/projects/<that path, every non-alphanumeric as '-'>/), or a transcript directory
itself. The backlog holds what someone noticed; the transcripts hold every call. Sections:

  calls    sessions, skill-tool calls per tool and command, Skill loads, reference reads
  crashes  tracebacks raised inside a skill script on a CLI call, by frame + exception;
           `script changed since` when git touched that script after the last one (a fix
           in a shared module such as kcommon.py does not mark it: re-run the command)
  usage    argparse errors: a flag or command Claude expected and the tool lacks
  help     -h / --help calls: where the router and docstrings did not answer
  inline   python that imports the skill modules, a question no command answers: count,
           how many raised (and why), the model attributes and internals they reach for

A session that edits a skill file is skill development and is left out unless --dev.
Transcripts log some tool calls twice; each tool_use id counts once. Default --since: 30
days back. Stdlib only.
"""
import argparse, collections as C, datetime as dt, glob, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(ROOT, 'skills', '*', 'SKILL.md')))
SCRIPTS = {os.path.basename(p)[:-3]: p for p in glob.glob(os.path.join(ROOT, 'skills', '*', 'scripts', '*.py'))}
CLI = [n for n, p in SCRIPTS.items() if re.search(r"__name__ == ['\"]__main__", open(p).read())]
T = '|'.join(sorted(map(re.escape, SCRIPTS), key=len, reverse=True))        # any module (imports, frames)
TC = '|'.join(sorted(map(re.escape, CLI), key=len, reverse=True))           # the tools people run
INV = re.compile(rf'\bpython3?(?:\s+-\S+)*\s+["\']?(?:[^\s=\'"]*/)?({TC})\.py\b["\']?([^|;&\n]*)')
ASSIGN = re.compile(rf'\b([A-Za-z_]\w*)=["\']?(?:[^\s;&|"\']*/)?({TC})\.py["\']?(?=[\s;&|)]|$)')
IMPORT = re.compile(rf'^\s*(?:from\s+({T})\s+import\s+([\w, ()]+)|import\s+({T})\b)', re.M)
FRAME = re.compile(r'File "([^"]+)", line (\d+), in (\S+)')
EXC = re.compile(r'^([A-Z]\w*(?:Error|Exception)|KeyboardInterrupt)\b:?(.*)$')
SKILLDIR = re.compile(r'/(?:%s)/' % '|'.join(map(re.escape, SKILLS or ['skills'])))
PATCH = re.compile(rf'sed -i[^\n|;]*\b({T})\.py|[\'"](?:\S*/)?({T})\.py[\'"][\s\S]*\.replace\([\s\S]*[\'"]w[\'"]')


def tdir_of(p):
    p = os.path.abspath(os.path.expanduser(p))
    if glob.glob(os.path.join(p, '*.jsonl')):
        return p
    base = os.path.expanduser(os.environ.get('CLAUDE_CONFIG_DIR', '~/.claude'))
    t = os.path.join(base, 'projects', re.sub(r'[^A-Za-z0-9]', '-', p))
    if not os.path.isdir(t):
        sys.exit(f"no transcripts for {p}: looked in {t}")
    return t


def load(path, since):
    """[(id, tool, input, ts)] in order, each tool_use id once, and {id: result text}"""
    calls, res, seen = [], {}, set()
    with open(path, errors='replace') as fh:
        for line in fh:
            if '"tool_use"' not in line and '"tool_result"' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            c = (d.get('message') or {}).get('content')
            for b in c if isinstance(c, list) else ():
                if not isinstance(b, dict):
                    continue
                if b.get('type') == 'tool_use' and b.get('id') not in seen:
                    seen.add(b.get('id'))
                    if (d.get('timestamp') or '') >= since:
                        calls.append((b.get('id'), b.get('name'), b.get('input') or {}, d.get('timestamp') or ''))
                elif b.get('type') == 'tool_result':
                    o = b.get('content')
                    res[b.get('tool_use_id')] = ('\n'.join(x.get('text', '') for x in o if isinstance(x, dict))
                                                 if isinstance(o, list) else o or '')
    return calls, res


def is_dev(calls):
    # ponytail: a heuristic (an Edit/Write under skills/<name>/, or a Bash patch naming a script);
    # a use session that writes a file called kpcb.py would read as dev
    for _i, name, inp, _t in calls:
        if name in ('Edit', 'Write', 'NotebookEdit') and SKILLDIR.search(inp.get('file_path', '')):
            return True
        if name == 'Bash' and PATCH.search(inp.get('command', '')):
            return True
    return False


def norm(s):
    """a grouping key: quoted strings and numbers blanked"""
    return re.sub(r'\d+', 'N', re.sub(r"'[^']*'|\"[^\"]*\"", "'..'", s.strip()))[:110]


def analyse(tdir, since='', dev=False):
    st = {k: C.Counter() for k in ('sessions', 'tool', 'cmd', 'skill', 'reads', 'help', 'attr', 'imp', 'inline_exc')}
    st.update(crash={}, usage={}, inline=[])
    for f in sorted(glob.glob(os.path.join(tdir, '**', '*.jsonl'), recursive=True)):
        calls, res = load(f, since)
        if not calls:
            continue
        d = is_dev(calls)
        st['sessions']['dev' if d else 'use'] += 1
        if d and not dev:
            continue
        var = {}
        for cid, name, inp, ts in calls:
            out = res.get(cid, '')
            if name == 'Skill':
                st['skill'][inp.get('skill', '?')] += 1
            elif name == 'Read' and SKILLDIR.search(inp.get('file_path', '')) and inp['file_path'].endswith(('.md', '.py')):
                st['reads'][re.sub(r'.*/(?=[^/]+/[^/]+$)', '', inp['file_path'])] += 1
            if name != 'Bash':
                continue
            cmd = inp.get('command', '')
            for m in ASSIGN.finditer(cmd):
                var[m.group(1)] = m.group(2)
            x = re.sub(r'\$\{?([A-Za-z_]\w*)\}?(?=[\s"\';|&)]|$)', lambda m: f'{var[m.group(1)]}.py' if m.group(1) in var else m.group(0), cmd)
            inline = bool(IMPORT.search(cmd)) and ('<<' in cmd or ' -c ' in cmd)
            for m in INV.finditer(x):
                toks = [t for t in m.group(2).split() if not t.startswith(('2>', '>'))]
                sub = next((t for t in toks if re.fullmatch(r'[a-z][a-z-]*', t)), '')
                st['tool'][m.group(1)] += 1
                st['cmd'][f"{m.group(1)} {sub}".strip()] += 1
                if '-h' in toks or '--help' in toks:
                    st['help'][f"{m.group(1)} {sub}".strip()] += 1
            for m in re.finditer(rf'^({TC})\.py: error: (.*)$', out, re.M):
                g = st['usage'].setdefault((m.group(1), norm(m.group(2))), [0, '', '', ''])
                g[0] += 1
                if ts >= g[1]:
                    g[1:] = [ts, m.group(2)[:110], re.sub(r'\s*\d?>&?\d?$', '', next(
                        (i.group(0).strip() for i in INV.finditer(x) if i.group(1) == m.group(1)), cmd))[:200]]
            exc = next((m for m in map(EXC.match, reversed(out.splitlines())) if m), None) if 'Traceback' in out else None
            frames = [fr for fr in FRAME.findall(out) if os.path.basename(fr[0])[:-3] in SCRIPTS] if exc else []
            if inline:
                st['inline'].append((ts, cmd, bool(exc)))
                for v in set(re.findall(r'(\w+)\s*=\s*(?:\w+\.)?(?:Board|Netlist)\(', cmd)) or {'b', 'nl'}:
                    st['attr'].update(f"{v}.{a}" for a in re.findall(rf'\b{v}\.(\w+)', cmd))
                for m in IMPORT.finditer(cmd):
                    st['imp'].update(f"{m.group(1)}.{n}" for n in re.findall(r'\w+', m.group(2) or '') if n != 'import')
                if exc:
                    st['inline_exc'][f"{exc.group(1)}{exc.group(2)[:90]}"] += 1
            elif frames and '"<stdin>"' not in out and '"<string>"' not in out:
                path, line, fn = frames[-1]
                key = (os.path.basename(path), fn, exc.group(1), norm(exc.group(2)))
                g = st['crash'].setdefault(key, [0, '', '', '', line])
                g[0] += 1
                if ts >= g[1]:
                    g[1:] = [ts, exc.group(2).strip()[:110], ' '.join(cmd.split())[:200], line]
    return st


def changed_since(script, ts):
    """did git commit to SCRIPT after TS (an ISO time)?"""
    p = SCRIPTS.get(script[:-3])
    if not p or not ts:
        return False
    r = subprocess.run(['git', '-C', ROOT, 'log', '-1', '--format=%cI', '--', p], capture_output=True, text=True)
    try:
        return dt.datetime.fromisoformat(r.stdout.strip()) > dt.datetime.fromisoformat(ts.replace('Z', '+00:00'))
    except ValueError:
        return False


def report(st, tdir, since, mx):
    top = lambda c, n=mx: ', '.join(f"{k} {v}" for k, v in c.most_common(n)) or '-'   # noqa: E731
    s = st['sessions']
    print(f"usage: {tdir}  since {since or 'the start'}")
    print(f"sessions {s['use']} use" + (f" (+{s['dev']} skill-development, left out; --dev counts them)" if s['dev'] else ''))
    print(f"skill-tool calls {sum(st['tool'].values())}: {top(st['tool'], 99)}")
    print(f"  top commands: {top(st['cmd'], mx * 2)}")
    print(f"  Skill loads: {top(st['skill'])}   reference/script Reads: {top(st['reads'])}")
    cr = sorted(st['crash'].items(), key=lambda kv: (-kv[1][0], kv[1][1]))
    print(f"\ncrashes inside a skill script on a CLI call: {sum(g[0] for _k, g in cr)} in {len(cr)} group(s)")
    for (f, fn, e, _m), (n, ts, msg, cmd, line) in cr[:mx]:
        print(f"  {n:3d}  {f}:{line} {fn}  {e}: {msg}   last {ts[:10]}"
              + ("   [script changed since]" if changed_since(f, ts) else ''))
        print(f"       $ {cmd}")
    us = sorted(st['usage'].items(), key=lambda kv: (-kv[1][0], kv[1][1]))
    print(f"\nusage errors: {sum(g[0] for _k, g in us)} in {len(us)} group(s)")
    for (tool, _m), (n, ts, msg, cmd) in us[:mx]:
        print(f"  {n:3d}  {tool}: {msg}   last {ts[:10]}" + ("   [script changed since]" if changed_since(tool + '.py', ts) else '')
              + f"\n       $ {cmd}")
    print(f"\nhelp lookups: {sum(st['help'].values())}: {top(st['help'])}")
    il = st['inline']
    print(f"\ninline scripts importing the skill modules: {len(il)} ({sum(r for *_x, r in il)} raised)")
    print(f"  attributes: {top(st['attr'], mx * 2)}")
    print(f"  imports: {top(st['imp'], mx * 2)}")
    if st['inline_exc']:
        print(f"  raised: {top(st['inline_exc'])}")
    for ts, cmd, raised in sorted(il, reverse=True)[:mx]:
        body = ' | '.join(ln.strip() for ln in cmd.split('<<', 1)[-1].splitlines()[1:]
                          if ln.strip() and not re.match(r"(import |from |sys\.path|EOF|'?EOF'?$)", ln.strip()))
        print(f"  [{ts[:10]}{' raised' if raised else ''}] {body[:220]}")


def selftest():
    def use(i, name, inp):
        return {'timestamp': '2026-11-01T00:00:00Z', 'message': {'content': [{'type': 'tool_use', 'id': i, 'name': name, 'input': inp}]}}
    def res(i, text):
        return {'timestamp': '2026-11-01T00:00:01Z', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': i, 'content': text}]}}
    tb = lambda fr, e: f'Traceback (most recent call last):\n  File "{fr}", line 657, in _pagespan\n{e}'   # noqa: E731
    s1 = [use('a1', 'Bash', {'command': 'P=x/skills/kicad-review/scripts/kpcb.py; python3 $P b.kicad_pcb where -h'}),
          use('a1', 'Bash', {'command': 'P=x/skills/kicad-review/scripts/kpcb.py; python3 $P b.kicad_pcb where -h'}),
          res('a1', 'kpcb.py: error: the following arguments are required: cmd'),
          use('a2', 'Bash', {'command': 'python3 x/kdoc.py text D 5-7 2>&1 | head'}),
          res('a2', tb('/r/skills/kicad-review/scripts/kdoc.py', "ValueError: invalid literal for int() with base 10: '5-7'")),
          use('a3', 'Bash', {'command': "python3 - <<'EOF'\nimport sys\nfrom kpcb_board import Board\nb = Board('x')\n"
                                        "for z in b.zones: print(z.net, b.fps)\nEOF"}),
          res('a3', tb('<stdin>', "AttributeError: 'Zone' object has no attribute 'net'")),
          use('a4', 'Read', {'file_path': '/p/.claude/skills/kicad-review/references/kpcb.md'}),
          use('a5', 'Skill', {'skill': 'kicad-review'})]
    s2 = [use('b1', 'Edit', {'file_path': '/x/skills/kicad-review/scripts/kpcb.py'}),
          use('b2', 'Bash', {'command': 'python3 x/kpcb.py b where U1'})]
    with tempfile.TemporaryDirectory() as d:
        for n, rows in (('s1', s1), ('s2', s2)):
            with open(os.path.join(d, n + '.jsonl'), 'w') as fh:
                fh.write('\n'.join(map(json.dumps, rows)) + '\nnot json\n')
        st, sd = analyse(d), analyse(d, dev=True)
        late = analyse(d, since='2026-12-01')
    ok = {'sessions': st['sessions'] == {'use': 1, 'dev': 1}, 'calls': sum(st['tool'].values()) == 2,
          'dev calls': sum(sd['tool'].values()) == 3, 'help': st['help'] == {'kpcb where': 1},
          'usage': len(st['usage']) == 1, 'crash': [k[:3] for k in st['crash']] == [('kdoc.py', '_pagespan', 'ValueError')],
          'inline': len(st['inline']) == 1 and st['inline'][0][2] and st['attr']['b.zones'] == 1
                    and st['imp']['kpcb_board.Board'] == 1 and 'AttributeError' in next(iter(st['inline_exc'])),
          'reads': st['reads'] == {'references/kpcb.md': 1} and st['skill'] == {'kicad-review': 1},
          'since': sum(late['tool'].values()) == 0}
    bad = [k for k, v in ok.items() if not v]
    print(f"usage.py selftest: {len(ok) - len(bad)}/{len(ok)} passed" + (f"; FAILED {', '.join(bad)}" if bad else ''))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('project', nargs='?')
    ap.add_argument('--since', default=(dt.date.today() - dt.timedelta(days=30)).isoformat())
    ap.add_argument('--dev', action='store_true', help='count skill-development sessions too')
    ap.add_argument('--max', type=int, default=6, help='rows per section')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.project:
        ap.error('give PROJECT_DIR (or --selftest)')
    t = tdir_of(a.project)
    report(analyse(t, a.since, a.dev), t, a.since, a.max)
    return 0


if __name__ == '__main__':
    sys.exit(main())
