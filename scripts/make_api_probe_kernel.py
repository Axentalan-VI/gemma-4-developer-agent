"""Generate the CPU-only harness-API probe kernel.

    python -X utf8 scripts/make_api_probe_kernel.py
    kaggle kernels push -p kernels/13_harness_api

Why this exists. P003 (2026-10-12) died 14 s into a GPU allocation on
`ModuleNotFoundError: No module named 'swegemma.models.discovery'`, an import
that had worked in P002 five days earlier. The competition republished the
wheelhouse on **2026-10-09 14:43**, so the harness API moved under us and the
dependency stack is NOT frozen the way the project's notes assumed.

This kernel answers "where did the API go" for **0 GPU-hours**, because it
**installs nothing**: it reads the wheels as zip archives. That means it cannot
fail on a dependency resolution, cannot need torch, and finishes in seconds.
Installing the stack to find out would need the GPU image and ~5 minutes.

Deliberately CPU + internet OFF: the wheelhouse rides in as a dataset, so there
is nothing to download, and a CPU kernel spends no GPU quota at all.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "kernels" / "13_harness_api"
OUT_NB = OUT_DIR / "13_harness_api.ipynb"

MARKDOWN = """# 13 - Where did the harness API go? (CPU, 0 GPU-h)

P003 died on `from swegemma.models.discovery import validate_single_declared_model`,
which worked in P002 on 2026-10-07. The competition **republished the wheelhouse
on 2026-10-09 14:43**, between the two runs.

This kernel installs **nothing**. It opens the wheels as zip archives and reports:

1. which `swegemma` / `adk_submission` distributions are present, and their versions;
2. every module inside `swegemma/models/`;
3. every archive member, in any wheel, that defines or mentions
   `validate_single_declared_model`;
4. the same for the competition directory, in case the harness ships there too.

The output is the fix: it names the module that now holds the symbol, which goes
straight into `scripts/session_runner.py` `start_server()` and into the eval
kernel's preflight gate.

**Do not add a GPU to this kernel.** It needs none, and a CPU kernel costs no
GPU quota.
"""

PROBE_CELL = r'''
import json
import re
import sys
import zipfile
from pathlib import Path

WANTED = 'validate_single_declared_model'
CANDIDATES = ('swegemma', 'adk_submission')

def say(*a):
    print(*a, flush=True)

roots = [Path('/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse'),
         Path('/kaggle/input/competitions/gemma-4-developer-agent')]
for r in roots:
    say('root', r, 'exists' if r.is_dir() else 'MISSING')

say('')
say('=' * 70)
say('1. distributions present')
say('=' * 70)

wheels = []
for r in roots:
    if r.is_dir():
        wheels += sorted(r.rglob('*.whl'))
say('total wheels visible:', len(wheels))
for w in wheels:
    if any(c in w.name.lower() for c in CANDIDATES):
        say('  ', w.name, '  <-', w.parent)

say('')
say('=' * 70)
say('2. contents of swegemma/models/ and anything named discovery')
say('=' * 70)

def members(w):
    try:
        with zipfile.ZipFile(w) as z:
            return z.namelist()
    except Exception as exc:
        say('  cannot read', w.name, type(exc).__name__, exc)
        return []

for w in wheels:
    if not any(c in w.name.lower() for c in CANDIDATES):
        continue
    names = members(w)
    say('--', w.name, '(' + str(len(names)), 'members)')
    for n in names:
        if '/models/' in n and n.endswith('.py'):
            say('     models:', n)
    for n in names:
        if 'discovery' in n.lower():
            say('     discovery:', n)

say('')
say('=' * 70)
say('3. which module defines ' + WANTED + '?')
say('=' * 70)

# Scan EVERY wheel, not just the two named ones: the symbol may have moved to a
# different distribution entirely, which is exactly the case a name-based search
# would miss.
pat_def = re.compile(rb'def\s+' + WANTED.encode() + rb'\s*\(')
hits_def, hits_mention = [], []
for w in wheels:
    try:
        with zipfile.ZipFile(w) as z:
            for n in z.namelist():
                if not n.endswith('.py'):
                    continue
                try:
                    blob = z.read(n)
                except Exception:
                    continue
                if pat_def.search(blob):
                    hits_def.append((w.name, n))
                elif WANTED.encode() in blob:
                    hits_mention.append((w.name, n))
    except Exception:
        continue

say('DEFINED in:')
for wn, n in hits_def or []:
    say('   ', wn, '->', n)
if not hits_def:
    say('    NOTHING DEFINES IT. The symbol is gone, not moved -- find what')
    say('    replaced it by reading the new models/__init__.py below.')

say('mentioned in (not a definition):')
for wn, n in hits_mention[:25]:
    say('   ', wn, '->', n)

say('')
say('=' * 70)
say('4. the new swegemma/models/__init__.py, verbatim')
say('=' * 70)

for w in wheels:
    if 'swegemma' not in w.name.lower():
        continue
    with zipfile.ZipFile(w) as z:
        for n in z.namelist():
            if n.endswith('swegemma/models/__init__.py'):
                say('--', w.name, n)
                say(z.read(n).decode('utf-8', 'replace')[:6000])

say('')
say('=' * 70)
say('5. adk_submission/discovery.py -- the module that APPEARED')
say('=' * 70)

# P004 round 1 found that swegemma/models/discovery.py is gone while
# adk_submission GAINED a discovery.py, and that nothing anywhere defines
# validate_single_declared_model. So the function was RENAMED, not relocated,
# and the replacement has to be read off the new module's public surface.
for w in wheels:
    if 'adk_submission' not in w.name.lower():
        continue
    with zipfile.ZipFile(w) as z:
        for n in z.namelist():
            if n.endswith('discovery.py') or n.endswith('adk_submission/__init__.py'):
                body = z.read(n).decode('utf-8', 'replace')
                say('')
                say('--- ' + w.name + ' :: ' + n + ' (' + str(len(body)) + ' B) ---')
                for line in body.splitlines():
                    if re.match(r'\s*(def |class |__all__|from |import )', line):
                        say('   ' + line.rstrip()[:160])

say('')
say('=' * 70)
say('6. anything that validates a declared model, by behaviour not by name')
say('=' * 70)

for w in wheels:
    if not any(c in w.name.lower() for c in CANDIDATES):
        continue
    with zipfile.ZipFile(w) as z:
        for n in z.namelist():
            if not n.endswith('.py'):
                continue
            body = z.read(n).decode('utf-8', 'replace')
            for m in re.finditer(r'^\s*def\s+(\w*(declared|model|validate)\w*)\s*\(',
                                 body, re.M | re.I):
                say('   ', w.name, n, '->', m.group(1))

say('')
say('=' * 70)
say('7. the replacement, in full: discover_declared_models + validate_directory')
say('=' * 70)

# P004 round 2 identified these two as the successors to the deleted
# validate_single_declared_model. session_runner needs the exact signature and
# return shape to call them, so print each def block verbatim.
TARGETS = ('discover_declared_models', 'validate_directory')
for w in wheels:
    if 'adk_submission' not in w.name.lower():
        continue
    with zipfile.ZipFile(w) as z:
        for n in z.namelist():
            if not n.endswith('discovery.py'):
                continue
            src = z.read(n).decode('utf-8', 'replace').splitlines()
            for t in TARGETS:
                start = next((k for k, l in enumerate(src)
                              if l.startswith('def ' + t)), None)
                if start is None:
                    say('   ' + t + ': not found in ' + n)
                    continue
                # Run to the next top-level def/class/decorator. Testing for
                # "column 0" instead stops at the signature's own closing
                # paren, which is why round 3 printed only three lines.
                end = next((k for k in range(start + 1, len(src))
                            if src[k].startswith(('def ', 'class ', '@'))), len(src))
                say('')
                say('--- ' + t + '  (' + n + ' lines ' + str(start + 1)
                    + '-' + str(end) + ') ---')
                for l in src[start:min(end, start + 70)]:
                    say('   ' + l.rstrip()[:170])
        # And how __init__ re-exports it, which is the import path to use.
        for n in z.namelist():
            if n.endswith('adk_submission/__init__.py'):
                body = z.read(n).decode('utf-8', 'replace')
                i = body.find('from .discovery import')
                say('')
                say('--- re-export block from adk_submission/__init__.py ---')
                say(body[i:i + 400] if i >= 0 else '(no .discovery re-export found)')

say('')
say('=== COPY FROM HERE ===')
print(json.dumps({
    'wheels_visible': len(wheels),
    'defined_in': hits_def,
    'mentioned_in': hits_mention[:25],
}, indent=1))
say('=== TO HERE ===')
'''

METADATA = {
    "id": "ahmedsherif382/swegemma-harness-api",
    "title": "swegemma harness api",
    "code_file": "13_harness_api.ipynb",
    "language": "python",
    "kernel_type": "notebook",
    "is_private": True,
    # CPU ONLY, on purpose. This spends no GPU quota, and it needs no GPU: the
    # wheels are read as zip archives rather than installed.
    "enable_gpu": False,
    "enable_tpu": False,
    "enable_internet": False,
    "dataset_sources": ["metric/gemma-4-developer-agent-wheelhouse"],
    "competition_sources": ["gemma-4-developer-agent"],
}


def code_cell(source: str) -> dict:
    lines = source.strip("\n").split("\n")
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": [ln + "\n" for ln in lines[:-1]] + [lines[-1]]}


def md_cell(source: str) -> dict:
    lines = source.strip("\n").split("\n")
    return {"cell_type": "markdown", "metadata": {},
            "source": [ln + "\n" for ln in lines[:-1]] + [lines[-1]]}


def main() -> int:
    nb = {
        "cells": [md_cell(MARKDOWN), code_cell(PROBE_CELL)],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    for i, c in enumerate(nb["cells"]):
        if c["cell_type"] == "code":
            compile("".join(c["source"]), f"<cell {i}>", "exec")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_NB.write_text(json.dumps(nb, indent=1), encoding="utf-8", newline="\n")
    (OUT_DIR / "kernel-metadata.json").write_text(
        json.dumps(METADATA, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT_NB} (all code cells compile)")
    print(f"wrote {OUT_DIR / 'kernel-metadata.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
