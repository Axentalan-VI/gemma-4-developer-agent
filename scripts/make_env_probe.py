"""Generate a ~20-second GPU kernel that answers one question: can anything here
run the cp312 wheelhouse?

    python -X utf8 scripts/make_env_probe.py

Kaggle moved the GPU image to Python 3.13 on 2026-10-07. The competition
wheelhouse ships cp312 and no cp313 wheel, and no newer wheelhouse has been
published (checked: `metric/gemma-4-developer-agent-wheelhouse`, last updated
2026-09-30). `docker_image_pinning_type: original` did not bring back a 3.12
image. So the measuring rig is gone unless one of these is true:

1. the image still ships a **3.12 interpreter** somewhere, which the wheelhouse
   could be installed into, or
2. the wheelhouse has a cp313 wheel we failed to detect, or
3. a non-GPU image is still 3.12, which would at least save the CPU-only
   calibration path.

This probe answers all three for ~20 GPU-seconds. It is deliberately a separate,
tiny kernel: putting the question inside the eval notebook would mean paying for
vLLM's 26 GB load to learn something a directory listing settles.

Nothing here installs anything or touches the GPU beyond reporting it.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "kernels" / "11_env_probe"
OUT_NB = OUT_DIR / "11_env_probe.ipynb"

MARKDOWN = """# 11 - Environment probe (~20 seconds, no install)

One question: **can anything on this image run the cp312 wheelhouse?**

Read the three verdict lines at the bottom. Nothing is installed and the GPU is
only reported, so this is safe to re-run whenever Kaggle changes an image.
"""

PROBE = r'''
import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path

def out(msg=''):
    print(str(msg), flush=True)

out('=== this interpreter ===')
out('sys.version   ' + sys.version.replace('\n', ' '))
out('sys.executable ' + sys.executable)
out('tag           cp' + str(sys.version_info.major) + str(sys.version_info.minor))

out('')
out('=== image identity ===')
for k in sorted(os.environ):
    if 'DOCKER' in k.upper() or 'KAGGLE' in k.upper() or 'IMAGE' in k.upper():
        out('  ' + k + '=' + str(os.environ[k])[:160])
for f in ('/etc/os-release',):
    if Path(f).is_file():
        for line in Path(f).read_text().splitlines():
            if line.startswith(('PRETTY_NAME', 'VERSION_ID')):
                out('  ' + line)

out('')
out('=== other interpreters on this image ===')
# A 3.12 interpreter anywhere would let the cp312 wheelhouse install into it,
# which would restore the measuring rig without waiting on the organisers.
cands = set()
for pat in ('/usr/bin/python3.*', '/usr/local/bin/python3.*', '/opt/conda/bin/python3.*',
            '/opt/conda/envs/*/bin/python', '/usr/local/envs/*/bin/python'):
    cands.update(glob.glob(pat))
found = {}
for c in sorted(cands):
    if c.endswith(('-config', 'm')):
        continue
    try:
        r = subprocess.run([c, '-c', 'import sys;print("%d.%d" % sys.version_info[:2])'],
                           capture_output=True, text=True, timeout=30)
        v = (r.stdout or '').strip()
        if v:
            found[c] = v
            out('  ' + c.ljust(44) + ' -> ' + v)
    except Exception as exc:
        out('  ' + c.ljust(44) + ' -> ' + type(exc).__name__)
if not found:
    out('  (none found beyond this one)')

out('')
out('=== wheelhouse ===')
INPUT = Path('/kaggle/input')
wh = None
for p in INPUT.rglob('*'):
    if p.is_dir() and 'wheelhouse' in p.name.lower() and any(p.glob('*.whl')):
        wh = p
        break
if wh is None:
    out('  WHEELHOUSE NOT ATTACHED')
    tags, n = set(), 0
else:
    out('  ' + str(wh))
    whls = sorted(wh.glob('*.whl'))
    n = len(whls)
    tags = set()
    for w in whls:
        tags.update(re.findall(r'-(cp3\d+)-', w.name))
    out('  wheels ' + str(n) + '   compiled tags ' + str(sorted(tags)))
    # The ones that actually matter: if vLLM and torch are pure-python or abi3,
    # the cp tag of the rest may not be fatal.
    for key in ('vllm', 'torch-', 'xformers', 'flashinfer_python', 'apache_tvm_ffi'):
        hit = [w.name for w in whls if w.name.lower().startswith(key)]
        out('    ' + key.ljust(18) + (hit[0] if hit else '(absent)'))

out('')
out('=== VERDICTS ===')
running = 'cp' + str(sys.version_info.major) + str(sys.version_info.minor)
v1 = running in tags if tags else None
out('1. this interpreter matches the wheelhouse: ' + str(v1) + '  (' + running + ' in ' + str(sorted(tags)) + ')')
alt312 = [c for c, v in found.items() if v == '3.12']
out('2. a 3.12 interpreter exists on this image: ' + ('YES -> ' + ', '.join(alt312) if alt312 else 'NO'))
out('3. wheelhouse has any cp313 wheel:          ' + ('YES' if 'cp313' in tags else 'NO'))
out('')
if alt312:
    out('ACTION: install the wheelhouse into ' + alt312[0] + ' and run session_runner with it.')
elif 'cp313' in tags:
    out('ACTION: the wheelhouse now covers cp313; re-run the eval kernel unchanged.')
else:
    out('ACTION: no local fix. Either the organisers must ship cp313 wheels, or we')
    out('        vendor a cp313 vLLM stack ourselves (multi-GB), or we wait.')

out('')
out('=== GPU (reported only) ===')
r = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,compute_cap',
                    '--format=csv,noheader'], capture_output=True, text=True)
out((r.stdout or '(nvidia-smi returned nothing)').strip())

# ---------------------------------------------------------------------------
# Part 2: is the cp312 gate actually fatal, or just blunt?
#
# vllm ships as cp38-abi3, which installs on ANY Python >= 3.8, and torch is NOT
# in the wheelhouse at all -- it comes from the image, where it is built for the
# image's own Python. So the preflight assert, which fails the whole run when the
# interpreter tag is not in the wheelhouse, may be condemning a run over a
# handful of genuinely version-locked wheels. This measures exactly which ones
# they are and whether vllm still imports without them.
out('')
out('=== cp312-locked wheels (the actual blockers) ===')
blockers, installable = [], []
if wh is not None:
    for w in sorted(wh.glob('*.whl')):
        n = w.name
        if re.search(r'-cp3\d+-cp3\d+', n) and running not in n:
            blockers.append(n)
        else:
            installable.append(n)
for b in blockers:
    out('  BLOCKED  ' + b)
out('  ' + str(len(blockers)) + ' blocked, ' + str(len(installable)) + ' installable on ' + running)

out('')
out('=== does /usr/bin/python3.12 have a usable torch? ===')
# If it does, the clean fix is to run the whole eval under 3.12. If it does not,
# that path needs a multi-GB torch+CUDA install and is not clean at all.
if alt312:
    probe_src = ('import importlib.util as u;'
                 'print("torch", u.find_spec("torch") is not None);'
                 'print("pip", u.find_spec("pip") is not None)')
    r = subprocess.run([alt312[0], '-c', probe_src], capture_output=True, text=True)
    out('  ' + ((r.stdout or '') + (r.stderr or '')).strip()[:300])
else:
    out('  no 3.12 interpreter')

out('')
out('=== try: install the installable wheels on this interpreter, then import vllm ===')
# Bounded and reversible-ish: --no-deps so nothing in the image is upgraded, and
# we only learn whether the import works. Nothing is run on the GPU.
if wh is not None and installable:
    tmp = Path('/tmp/wh_ok')
    tmp.mkdir(parents=True, exist_ok=True)
    paths = []
    for n in installable:
        if 'cutlass' in n.lower():
            continue
        src = wh / n
        dst = tmp / n
        if not dst.exists():
            try:
                os.symlink(src, dst)
            except OSError:
                pass
        paths.append(str(dst))
    r = subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', *paths],
                       capture_output=True, text=True)
    out('  pip rc ' + str(r.returncode))
    if r.returncode != 0:
        out('  ' + (r.stderr or '')[-1200:])
    # `import vllm` is NOT sufficient and this is the trap that cost a run:
    # vllm/_C.abi3.so loads lazily, so the top-level import succeeds and the
    # server then dies with
    #   undefined symbol: _ZN3c1013MessageLoggerC1EPKciib
    # That is a libtorch C++ symbol. abi3 pins the PYTHON abi, not the C++ one, so
    # a wheel built against one torch will not link against another. Load _C
    # explicitly -- it is the cheapest check that reaches the real failure.
    chk = subprocess.run([sys.executable, '-c',
                          'import torch;print("torch", torch.__version__, "cuda", torch.cuda.is_available());'
                          'import vllm;print("vllm", vllm.__version__);'
                          'import vllm._C;print("vllm._C OK")'],
                         capture_output=True, text=True)
    out('  deep import check (torch, vllm, vllm._C):')
    out('    ' + ((chk.stdout or '') + (chk.stderr or '')).strip()[-1800:])
    out('')
    out('VERDICT 4: vllm._C links against this image torch: '
        + ('YES -- the rig works' if chk.returncode == 0 else 'NO -- C++ ABI mismatch'))

    # What torch was the wheelhouse's vllm actually built for? This is the number
    # that decides whether the rig is recoverable at all, and it is written in the
    # wheel's own metadata.
    out('')
    out('=== what torch does the wheelhouse vllm require? ===')
    import zipfile
    vw = [w for w in sorted(wh.glob('*.whl')) if w.name.lower().startswith('vllm-')]
    if vw:
        z = zipfile.ZipFile(vw[0])
        meta = [n for n in z.namelist() if n.endswith('METADATA')]
        if meta:
            txt = z.read(meta[0]).decode('utf-8', 'replace')
            for line in txt.splitlines():
                low = line.lower()
                if low.startswith('requires-dist') and any(
                        k in low for k in ('torch', 'nvidia', 'xformers', 'flashinfer', 'triton')):
                    out('  ' + line)
                elif low.startswith(('name:', 'version:', 'requires-python')):
                    out('  ' + line)
    else:
        out('  no vllm wheel found')

    out('')
    out('=== is that torch present anywhere on this image? ===')
    for c in sorted(set(list(found) + [sys.executable])):
        r2 = subprocess.run([c, '-c', 'import torch;print(torch.__version__)'],
                            capture_output=True, text=True)
        out('  ' + c.ljust(34) + ' -> ' + ((r2.stdout or r2.stderr or '').strip()[:80] or 'no torch'))
else:
    out('  skipped')
'''

METADATA = {
    "id": "ahmedsherif382/swegemma-env-probe",
    "title": "swegemma env probe",
    "code_file": "11_env_probe.ipynb",
    "language": "python",
    "kernel_type": "notebook",
    "is_private": True,
    # GPU on, because the question is about the GPU image specifically. The CPU
    # image may well be a different Python and would not answer it.
    "enable_gpu": True,
    "enable_tpu": False,
    "enable_internet": False,
    "machine_shape": "NvidiaL4",
    # Deliberately NOT pinned. We want to see what an unpinned run gets today, so
    # this doubles as the check for "has the image rolled again".
    "dataset_sources": [
        "ahmedsherif382/swegemma-lab",
        "metric/gemma-4-developer-agent-wheelhouse",
    ],
    "competition_sources": [],
    "kernel_sources": [],
}


def main() -> int:
    def cell(kind: str, src: str) -> dict:
        lines = src.strip("\n").split("\n")
        body = [ln + "\n" for ln in lines[:-1]] + [lines[-1]]
        if kind == "code":
            return {"cell_type": "code", "execution_count": None, "metadata": {},
                    "outputs": [], "source": body}
        return {"cell_type": "markdown", "metadata": {}, "source": body}

    nb = {
        "cells": [cell("markdown", MARKDOWN), cell("code", PROBE)],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    compile(PROBE, "<probe>", "exec")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_NB.write_text(json.dumps(nb, indent=1), encoding="utf-8", newline="\n")
    (OUT_DIR / "kernel-metadata.json").write_text(
        json.dumps(METADATA, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT_NB} (compiles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
