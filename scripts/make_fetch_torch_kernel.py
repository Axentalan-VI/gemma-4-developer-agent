"""Generate a CPU kernel that fetches torch 2.10.0+cu128 for the GPU kernel.

    python -X utf8 scripts/make_fetch_torch_kernel.py

Why this exists, measured rather than assumed:

The competition wheelhouse's `vllm-0.19.1` declares `Requires-Dist: torch==2.10.0`
and `Requires-Python: <3.14,>=3.10`. Kaggle's GPU image ships **torch
2.11.0+cu128**, so `vllm/_C.abi3.so` fails to link with
`undefined symbol: _ZN3c1013MessageLoggerC1EPKciib` -- a libtorch C++ symbol.
`abi3` pins the Python ABI, not the C++ one. So Python 3.13 was never the real
problem: **torch is**, and it is exactly one minor version off.

torch is not in the wheelhouse (it comes from the image), and the GPU kernel has
no internet because this competition refuses it with the L4 accelerator. Hence
the split this project's CLAUDE.md already prescribes: **a CPU kernel with
internet fetches what PyPI holds, and the GPU kernel consumes its output as a
data source.** That costs no GPU quota and no local bandwidth -- the 917 MB wheel
never touches this machine.

Attach the output to the GPU kernel with
`"kernel_sources": ["ahmedsherif382/swegemma-fetch-torch"]`.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "kernels" / "12_fetch_torch"
OUT_NB = OUT_DIR / "12_fetch_torch.ipynb"

#: Pinned to what the wheelhouse vllm declares. Not "latest", not "whatever
#: works": the whole point is to match the ABI the prebuilt vllm was compiled
#: against, so a different version would reintroduce the bug it fixes.
TORCH = "2.10.0"
TORCHVISION = "0.25.0"
TORCHAUDIO = "2.10.0"
CUDA_INDEX = "https://download.pytorch.org/whl/cu128"

MARKDOWN = f"""# 12 - Fetch torch {TORCH}+cu128 for the GPU kernel (CPU, internet, ~5 min)

The wheelhouse's `vllm-0.19.1` declares `torch=={TORCH}`. Kaggle's GPU image ships
torch 2.11.0+cu128, so `vllm/_C.abi3.so` will not link
(`undefined symbol: _ZN3c1013MessageLoggerC1EPKciib`, a libtorch C++ symbol).

torch is not in the wheelhouse and the GPU kernel has no internet, so this CPU
kernel downloads it and the GPU kernel consumes this kernel's **output** as a data
source. No GPU quota, no local bandwidth.

Output: `/kaggle/working/torch{TORCH.replace('.', '')}/*.whl`
"""

FETCH = f'''
import json
import subprocess
import sys
import time
from pathlib import Path

OUT = Path('/kaggle/working/torch{TORCH.replace('.', '')}')
OUT.mkdir(parents=True, exist_ok=True)


def say(msg=''):
    print('[' + time.strftime('%H:%M:%S') + '] ' + str(msg), flush=True)


# --platform/--python-version force a cross-download: this kernel is CPU and may
# even be a different Python, but the wheels have to match the GPU image, which is
# cp313 / manylinux_2_28 / x86_64. Without these flags pip would resolve for THIS
# interpreter and the GPU kernel would reject every wheel.
#
# --extra-index-url is required, not optional: torch's +cu128 build lives on the
# PyTorch index, but its nvidia-* dependencies (nvidia-cuda-nvrtc-cu12==12.8.93 and
# friends) live on PyPI. With only the PyTorch index, pip resolved torch and then
# died with "Could not find a version that satisfies nvidia-cuda-nvrtc-cu12" and
# downloaded nothing at all.
BASE = [sys.executable, '-m', 'pip', 'download',
        '--index-url', '{CUDA_INDEX}',
        '--extra-index-url', 'https://pypi.org/simple',
        '--only-binary=:all:',
        '--python-version', '313',
        # --platform is EXACT, not a floor: pip accepts only the tags listed, and
        # does not infer that manylinux_2_28 can run a manylinux_2_12 wheel. torch
        # itself is manylinux_2_28, but its nvidia-* deps are tagged all over the
        # ladder -- nvidia_cuda_nvrtc_cu12 12.8.93 is
        # `manylinux2010_x86_64.manylinux_2_12_x86_64`. With only _2_28 listed, pip
        # reported "from versions: none" for a wheel that exists, twice. So the
        # whole ladder is passed; repeated --platform is supported.
        '--platform', 'manylinux_2_28_x86_64',
        '--platform', 'manylinux_2_27_x86_64',
        '--platform', 'manylinux_2_24_x86_64',
        '--platform', 'manylinux_2_17_x86_64',
        '--platform', 'manylinux2014_x86_64',
        '--platform', 'manylinux_2_12_x86_64',
        '--platform', 'manylinux2010_x86_64',
        '--platform', 'manylinux1_x86_64',
        '-d', str(OUT)]

# WITH dependencies. torch 2.10 and 2.11 pin different nvidia-* versions, and the
# image's are installed for 2.11; mixing them is exactly the class of mismatch
# being fixed here, so the matching set is fetched rather than assumed compatible.
#
# The +cu128 local version is REQUIRED in the specifier, not decoration. With both
# indexes visible, `torch==2.10.0` matches the PyPI build AND the PyTorch index's
# 2.10.0+cu128, and pip refuses: "Cannot install torch==2.10.0 and
# torch==2.10.0+cu128 because these package versions have conflicting
# dependencies." Naming the local version disambiguates it.
TARGETS = ['torch=={TORCH}+cu128', 'torchvision=={TORCHVISION}+cu128',
           'torchaudio=={TORCHAUDIO}+cu128']

say('downloading ' + ', '.join(TARGETS))
r = subprocess.run(BASE + TARGETS, capture_output=True, text=True)
say('pip rc ' + str(r.returncode))
if r.returncode != 0:
    say((r.stdout or '')[-2000:])
    say((r.stderr or '')[-3000:])
    # Retry one at a time: a single unresolvable target otherwise aborts the batch
    # and leaves nothing, which is the same trap as the wheelhouse bulk install.
    say('retrying individually')
    for t in TARGETS:
        rr = subprocess.run(BASE + [t], capture_output=True, text=True)
        say('  ' + t + ' rc ' + str(rr.returncode))
        if rr.returncode != 0:
            say('    ' + (rr.stderr or '')[-800:])

wheels = sorted(OUT.glob('*.whl'))
total = sum(w.stat().st_size for w in wheels)
say('')
say(str(len(wheels)) + ' wheel(s), ' + format(total / 1e9, '.2f') + ' GB')
for w in wheels:
    say('  ' + w.name + '  ' + format(w.stat().st_size / 1e6, '.1f') + ' MB')

# The one wheel the whole exercise is for. Fail loudly if it is absent, because a
# partial download would send the GPU kernel back into the same ABI error.
have_torch = [w for w in wheels if w.name.startswith('torch-{TORCH}')]
say('')
say('torch {TORCH} present: ' + str(bool(have_torch)))
(Path('/kaggle/working') / 'fetch_manifest.json').write_text(
    json.dumps({{'torch': '{TORCH}', 'wheels': [w.name for w in wheels],
                 'bytes': total}}, indent=2), encoding='utf-8')
assert have_torch, 'torch {TORCH} did not download; the GPU kernel cannot be fixed without it'
say('DONE')
'''

METADATA = {
    "id": "ahmedsherif382/swegemma-fetch-torch",
    "title": "swegemma fetch torch",
    "code_file": "12_fetch_torch.ipynb",
    "language": "python",
    "kernel_type": "notebook",
    "is_private": True,
    # CPU + internet. The competition only refuses internet with the premium
    # accelerator, so this split is what makes the fetch possible at all.
    "enable_gpu": False,
    "enable_tpu": False,
    "enable_internet": True,
    "dataset_sources": [],
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

    compile(FETCH, "<fetch>", "exec")
    nb = {
        "cells": [cell("markdown", MARKDOWN), cell("code", FETCH)],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_NB.write_text(json.dumps(nb, indent=1), encoding="utf-8", newline="\n")
    (OUT_DIR / "kernel-metadata.json").write_text(
        json.dumps(METADATA, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT_NB} (compiles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
