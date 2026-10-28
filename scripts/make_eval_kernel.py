"""Generate the paired-arm eval kernel notebook from the proven smoke notebook.

    python -X utf8 scripts/make_eval_kernel.py --config paired100
    python -X utf8 scripts/make_eval_kernel.py --config resolve60
    python -X utf8 scripts/make_eval_kernel.py --all

Each named config in `CONFIGS` is one GPU run shape and owns its own kernel id,
so generating one never overwrites another's notebook or its Kaggle history.

The setup cells (environment, source discovery, wheelhouse Python-tag check,
cutlass workaround, pip install, preflight) are copied **verbatim** from
`notebooks/03_pipeline_smoke.ipynb`, which is the only cell sequence that has
ever reached a served request. Only the run cells are replaced.

Generated rather than hand-authored because three of this project's notebook
failures were `SyntaxError`s from hand-editing JSON cell sources, and a notebook
that dies on a syntax error after vLLM has loaded wastes the whole allocation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "notebooks" / "03_pipeline_smoke.ipynb"

#: Cells taken unchanged from the smoke notebook: imports/logging, source
#: discovery, the Python-tag assert, and the wheel install + preflight.
REUSE_CELLS = (1, 2, 3, 4)


def fill(template: str, **kw: object) -> str:
    """Substitute `@@name@@` tokens in a cell template.

    Deliberately not `str.format`: these templates are Python source, and a
    future cell containing a dict literal or an f-string would make brace
    escaping a silent source of `SyntaxError` on Kaggle. `@@name@@` cannot
    collide with Python syntax.
    """
    out = template
    for key, value in kw.items():
        out = out.replace("@@" + key + "@@", str(value))
    assert "@@" not in out, f"unsubstituted token in template: {out[out.index('@@'):][:40]!r}"
    return out


PAIRED_MARKDOWN = """# 10 - Paired eval run at the grader's call budget

Two arms over the **same 12 tasks** `probe_c12` ran, at the grader's
`max_tool_calls=100` instead of the probe's 30.

## Cell 3 is the gate; it should now pass on Python 3.13

Kaggle moved the GPU image to Python 3.13 on 2026-10-07 while the competition
wheelhouse still ships cp312. That is survivable, because it was never as bad as
it looked: **vLLM ships `cp38-abi3`** so it installs on any Python, **torch is not
in the wheelhouse at all** (it comes from the image, 2.11.0+cu128), and only **9
of 41** wheels are genuinely version-locked. Measured on the 3.13 image with those
9 skipped: `import vllm` succeeded and `torch.cuda.is_available()` was True.

So `vendor/cp313/` carries cp313 builds of exactly those 9, at the **same
versions** — a retag, not an upgrade — and cell 3 now checks whether every
version-locked wheel is *satisfiable* rather than whether the tags happen to
match. If it reports `UNRESOLVED`, the named wheel needs a cp313 build added to
`vendor/cp313/` and the dataset re-pushed.

Pinning does **not** undo the image change: `original` resolves to today's image
(`KAGGLE_DOCKER_IMAGE` matched the pinned digest exactly). It is kept so the stack
stops moving between arms, which a paired comparison requires.

## Run All by hand, and here is the catch

**An interactive session publishes nothing.**
`/kaggle/working` is only committed when a version is saved, which is why
`kaggle kernels output` returned a stale zip for `probe_c12` and nothing at all
for the first attempt here. So this notebook is built so the **log alone is a
complete record**: `session_runner` prints every ledger row behind `LEDGER_ROW `,
and the last cell reprints all of them inside a marked block.

## When it finishes

1. Copy everything between `=== COPY FROM HERE ===` and `=== TO HERE ===` in the
   last cell's output.
2. Save it locally as `ledger/incoming/paired100.log`.
3. `python scripts/recover_from_log.py --log ledger/incoming/paired100.log --write`

Optionally also **Quick Save** (which saves the current outputs without re-running)
and download `eval_ledger.zip` / `eval_results.zip` from the Output panel — that
additionally recovers the patches and traces, which the log does not carry. The
log is the floor; the zips are the ceiling.

## What it answers

1. **What does a task cost at 100 calls?** The k=4 reference plan is priced off
   `probe_c12`'s 30-call numbers and underprices it by roughly 3x.
2. **Does `v03_budget_guard` reduce the waste?** The headline resolution rate is
   far too noisy at n=12 to read. The quantities to read are the **coder's share
   of tool calls** and the **verbatim re-issue rate**, both of which v03 targets
   directly and both of which have a large measured baseline: 47% coder share and
   235 of 491 calls repeated.
3. **Do v03's sampling ceilings remove the two `ContextWindowExceededError`
   deaths?** `fastapi_13207` and `fastapi_13786` died one token over the window.

## What it does NOT answer

Resolution rate. Twelve tasks at one sample cannot separate a +0.05 effect from
noise; the ship rule in `stats.py` still needs the k=4 reference. Nothing here
should be reported as a score.

## Deliberate deviation

`max_time_minutes` is set to 30, not the grader's 60, to bound the tail: one task
in `probe_c12` (`fastapi_14258`) looped to 173 tool calls and 1.57M prompt tokens
and was stopped only by the time cap. The ledger row does not record the time
cap, so a task lost to it is indistinguishable from one lost legitimately -- but
both arms get the same cap and the comparison is paired, so it cannot favour
either arm. Tool calls are at the grader's 100, which is the budget under study.
"""

TORCH_CELL = '''
# Put the torch the prebuilt vllm was COMPILED against on this image, before the
# wheelhouse install, so vllm/_C.abi3.so links.
#
# MEASURED: wheelhouse vllm-0.19.1 declares `Requires-Dist: torch==2.10.0` and
# `Requires-Python: <3.14,>=3.10`. Kaggle's image ships torch 2.11.0+cu128, and
# vllm/_C then fails with `undefined symbol: _ZN3c1013MessageLoggerC1EPKciib`, a
# libtorch C++ symbol. abi3 pins the PYTHON abi, not the C++ one. So Python 3.13
# was never the blocker -- torch being one minor version off is.
#
# The wheels ride in from kernel 12 (CPU + internet), because torch is not in the
# wheelhouse and this kernel has no internet.
# All THREE of torch, torchvision and torchaudio, because they are one unit.
# Installing torch alone left the image's torchvision (built for 2.11) in place and
# the server died with `RuntimeError: operator torchvision::nms does not exist` --
# torchvision registers its compiled ops into torch's dispatcher, so a mismatched
# pair fails at registration rather than at import. vllm-0.19.1 pins exactly
# torch==2.10.0, torchvision==0.25.0, torchaudio==2.10.0.
TORCH_WANT = '2.10.0'
WANT = (('torch', '2.10.0'), ('torchvision', '0.25.0'), ('torchaudio', '2.10.0'))

cands = sorted(Path('/kaggle/input').rglob('torch-' + TORCH_WANT + '*.whl'))
say('torch ' + TORCH_WANT + ' wheels found: ' + str([c.name for c in cands]))
assert cands, (
    'no torch ' + TORCH_WANT + ' wheel under /kaggle/input. Run kernel '
    '12_fetch_torch and attach it via kernel_sources. Without it vllm cannot link.')

TORCH_DIR = cands[0].parent
PIN_WHEELS = []
for pkg, ver in WANT:
    hit = sorted(TORCH_DIR.glob(pkg + '-' + ver + '*.whl'))
    assert hit, (
        'no ' + pkg + ' ' + ver + ' wheel in ' + str(TORCH_DIR) + '. torch, '
        'torchvision and torchaudio must be installed as a matched set, or '
        'torchvision fails to register its ops against torch.')
    PIN_WHEELS.append(str(hit[0]))
    say('  will install ' + hit[0].name)

say('installing the matched torch set from ' + str(TORCH_DIR))
# WITH deps, from that directory only: torch 2.10 and 2.11 pin different nvidia-*
# versions and the image's are installed for 2.11. Mixing them is the same class of
# mismatch being fixed here, so the matching set is installed rather than trusted.
# Install by WHEEL PATH, not by requirement. The wheel is torch-2.10.0+cu128-...,
# and a `torch==2.10.0` specifier is ambiguous enough to have already broken the
# fetch step ("Cannot install torch==2.10.0 and torch==2.10.0+cu128"). A path
# cannot be misresolved. --find-links still covers the nvidia-* dependencies.
r = subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--force-reinstall',
                    '--no-index', '--find-links', str(TORCH_DIR)] + PIN_WHEELS,
                   capture_output=True, text=True)
say('torch set pip rc ' + str(r.returncode))
if r.returncode != 0:
    say((r.stderr or '')[-2500:])

# Verify the ops actually REGISTER, not merely that the versions read correctly.
# `torch.ops.torchvision.nms` is the exact operator whose absence killed the
# previous run, so it is the honest check: a version string can agree while the
# dispatcher disagrees.
chk = subprocess.run([sys.executable, '-c',
                      'import torch, torchvision, torchaudio;'
                      'print("torch", torch.__version__, torch.version.cuda);'
                      'print("torchvision", torchvision.__version__);'
                      'print("torchaudio", torchaudio.__version__);'
                      'print("nms op", torch.ops.torchvision.nms is not None)'],
                     capture_output=True, text=True)
say('torch set now: ' + ((chk.stdout or '') + (chk.stderr or '')).strip()[-800:])
assert chk.returncode == 0 and TORCH_WANT in (chk.stdout or ''), (
    'the matched torch set is not active, or torchvision ops do not register. '
    'A mismatched torchvision raises "operator torchvision::nms does not exist" '
    'inside the inference server, long after this point.')
'''

BUNDLE_GATE_CELL = """# Gate: every arm's bundle must already be in the PUBLISHED lab dataset.
#
# Placed before the torch install deliberately. `push_dataset.py` is a separate
# publish action from `git commit`, so a bundle can exist locally, be committed,
# and still be absent here -- and arm 2 would then fail only AFTER arm 1 had
# spent ~3 GPU-h. The gate costs milliseconds and protects the allocation.
#
# `.yml` is checked for by name because it is NEVER discovered by the harness
# (only agent.yaml / root_agent.yaml), so a .yml-only bundle scores 0.00 while
# looking present.
BUNDLES = LAB / 'bundles'
_missing, _bad = [], []
for _arm in @@arms@@:
    _d = BUNDLES / _arm
    if not _d.is_dir():
        _missing.append(_arm)
        continue
    _roots = [q.name for q in _d.rglob('*') if q.name in ('agent.yaml', 'root_agent.yaml')]
    _ymls = [str(q.relative_to(_d)) for q in _d.rglob('agent.yml')]
    say('  ' + _arm.ljust(22) + ' roots=' + str(sorted(set(_roots))) + (' WARN .yml: ' + str(_ymls) if _ymls else ''))
    if not _roots:
        _bad.append(_arm + ' (no agent.yaml/root_agent.yaml)')
assert not _missing, (
    'bundle(s) absent from the published lab dataset: ' + str(_missing)
    + ' -- run: python scripts/push_dataset.py -m "<note>" and wait for the new version')
assert not _bad, 'bundle(s) present but undiscoverable: ' + str(_bad)
_runner = LAB / 'scripts' / 'session_runner.py'
assert _runner.is_file(), 'no session_runner.py at ' + str(_runner)
say('bundle gate OK for ' + str(len(@@arms@@)) + ' arm(s)')
"""


#: Opt-in, via the config key `assert_task_list`. Also not emitted for configs
#: that omit it, for the same byte-identity reason.
#:
#: `push_dataset.py` copies only a WHITELIST of task lists into the dataset
#: (`scripts/push_dataset.py:53`), so a list that exists in the repo can be
#: absent on Kaggle. `session_runner` does check for it (line 455) and exits 2
#: before vLLM starts, but only after the ~4-minute torch and wheelhouse
#: installs -- and it exits per ARM, so the second arm pays the price again.
#: Checking here costs milliseconds and states the expected count, so a
#: truncated list is visible as truncated rather than as a short ledger.
TASK_LIST_GATE_CELL = """# Gate: the task list must be IN the published dataset, and the right length.
_tl = LAB / 'tasks' / '@@task_list@@'
assert _tl.is_file(), (
    'no task list at ' + str(_tl) + ' -- push_dataset.py copies only a whitelist '
    "of task lists (scripts/push_dataset.py:53). Add '@@task_list@@' to it and "
    're-push the dataset.')
_ids = [x.strip() for x in _tl.read_text(encoding='utf-8').splitlines() if x.strip()]
say('task list @@task_list@@: ' + str(len(_ids)) + ' id(s), expect @@n_tasks@@')
assert len(_ids) == @@n_tasks@@, (
    'task list has ' + str(len(_ids)) + ' ids, not @@n_tasks@@. The dataset copy is '
    'stale or truncated; re-push it. Both arms must run the SAME set or the '
    'pairing is meaningless.')
assert len(set(_ids)) == len(_ids), 'duplicate ids in @@task_list@@'
"""

#: Opt-in, via the config key `assert_gpu`. NOT emitted for configs that omit
#: it, so regenerating an older kernel still produces byte-identical output.
#:
#: The reused smoke cell already prints `nvidia-smi` and asserts `N_GPU >= 2`,
#: but it only WARNS when the compute capability is below 8.0 -- it was written
#: to discover whether a T4 could serve W4A16 at all. For a measurement run that
#: is not enough: `machine_shape` is validated by the Kaggle CLI only on >= 2.2
#: and an unrecognised value is SILENTLY IGNORED on older ones, so a push that
#: asks for L4 x4 can be handed T4 x2 and the log would say so only in passing.
#: One run has already been lost that way. This cell turns that into a stop.
GPU_ASSERT_CELL = """# Hard gate on the accelerator, before anything expensive runs.
#
# `enable_gpu` is a boolean; the GPU TYPE comes from `machine_shape` in
# kernel-metadata.json, which an older CLI accepts and ignores without a word.
# So the notebook verifies what it was actually given rather than what it asked
# for. Weights plus overhead are ~26 GB across 4 cards and the grader's 32,768
# context needs ~39 GB more of KV at 1.21 MB/token: only L4 x4 (92 GB) holds it.
_want = '@@want_gpu@@'
_names = [r.split(',')[0].strip() for r in nvsmi('name').splitlines() if r.strip()]
say('accelerator: ' + str(_names))
assert len(_names) >= 4, (
    'expected 4 GPUs, got ' + str(len(_names)) + ' -- machine_shape was not honoured. '
    'Check "machine_shape": "NvidiaL4" in kernel-metadata.json and that the Kaggle '
    'CLI is >= 2.2; an invalid value is silently ignored.')
assert all(_want.lower() in n.lower() for n in _names), (
    'expected ' + _want + ' x4, got ' + str(_names) + '. A T4 x2 allocation has '
    'already cost this project a run: it cannot load the weights at all.')
assert MEM_GB > 80, (
    'only ' + format(MEM_GB, '.1f') + ' GB of VRAM; the weights plus a 32k context '
    'need ~65 GB and this run would die after the install.')
assert MAX_MODEL_LEN == 32768, (
    'MAX_MODEL_LEN is ' + str(MAX_MODEL_LEN) + ', not the grader 32768. The KV budget '
    'computed from this GPU set cannot hold the grader context, so any result would '
    'be a pipeline test rather than a measurement.')
say('accelerator gate OK: ' + str(len(_names)) + ' x ' + _want
    + ', ' + format(MEM_GB, '.1f') + ' GB, max_model_len ' + str(MAX_MODEL_LEN))
"""

#: Opt-in, via the config key `guardrail_traces`. Prints the per-arm behavioural
#: metrics from `scripts/analyze_traces.py` into the LOG.
#:
#: Load-bearing for a decode experiment: `reissue_rate` is the pre-registered
#: kill criterion for greedy decode, and it lives in the traces, which travel
#: home only inside `eval_results.zip`. A guard-rail that arrives only when the
#: run went well is not a guard-rail, so it is computed on Kaggle and printed.
GUARDRAIL_CELL = '''
# Behavioural guard-rail, per arm, straight into the log.
#
# `reissue_rate` = repeat-argument tool calls / calls that actually spent budget.
# It is how this project detects an agent looping on one failing action: a
# freed budget once raised it by +0.151, with 174 `submit_patch` calls in one
# task and 136 malformed `edit_file` in another. Greedy decode is deterministic
# given the context, so it is exactly the intervention that could make a loop
# self-sustaining -- the validator warns about it by name.
#
# Wrapped: a reporting bug must never destroy a completed run.
try:
    sys.path.insert(0, str(LAB / 'scripts'))
    sys.path.insert(0, str(LAB / 'src'))
    import analyze_traces

    say('=== GUARD-RAIL: behavioural metrics per arm ===')
    _per_arm = {}
    for arm in ARMS:
        run_id = RUN_PREFIX + arm.split('_')[0]
        tdir = WORK / 'results' / run_id / 'traces'
        if not tdir.is_dir():
            say('  ' + run_id + ': no traces dir at ' + str(tdir))
            continue
        m = analyze_traces.arm_metrics(tdir)
        _per_arm[run_id] = m
        say('  ' + run_id + ': ' + str(len(m)) + ' trace(s)')
        for key in analyze_traces.COMPARED:
            vals = [v[key] for v in m.values()]
            if vals:
                vals_sorted = sorted(vals)
                say('    ' + key.ljust(18)
                    + ' mean ' + format(sum(vals) / len(vals), '.3f')
                    + '  median ' + format(vals_sorted[len(vals_sorted) // 2], '.3f')
                    + '  max ' + format(max(vals), '.3f'))
        # Name the worst offenders: a mean can hide one pathological task, and
        # one pathological task is what the kill criterion is written against.
        worst = sorted(m.items(), key=lambda kv: -kv[1]['reissue_rate'])[:3]
        for t, mm in worst:
            say('    top reissue  ' + t.ljust(18)
                + ' rate ' + format(mm['reissue_rate'], '.3f')
                + '  calls ' + format(mm['counted_calls'], '.0f'))

    # The paired delta, which is what the pre-registered reading asks for.
    if len(_per_arm) == 2:
        (ra, ma), (rb, mb) = list(_per_arm.items())
        shared = sorted(set(ma) & set(mb))
        say('  paired on ' + str(len(shared)) + ' task(s): ' + rb + ' minus ' + ra)
        for key in analyze_traces.COMPARED:
            if shared:
                d = [mb[t][key] - ma[t][key] for t in shared]
                say('    d_' + key.ljust(18) + format(sum(d) / len(d), '+.3f'))
        say('  KILL CRITERION: d_reissue_rate >= +0.100 refutes greedy decode.')
except Exception as exc:
    say('guard-rail cell raised (not fatal): ' + type(exc).__name__ + ': ' + str(exc))
'''


STAGE_DEPS_CELL = '''
# The reused setup cells do not import importlib; this cell needs both it and
# importlib.util, and `import importlib` alone does not bind the submodule.
import importlib
import importlib.util

# session_runner refuses to run (exit 4) unless inline_snapshot and dirty_equals
# are importable. That gate is right: probe_c12 lost 5 of 12 tasks to pytest
# COLLECTION errors from exactly these two packages, which scores as unresolved
# and is indistinguishable from a bad patch. C004 measured them moving clean-N
# from 71 to 102.
#
# The first attempt at this kernel passed neither the gate nor a staging step, so
# both arms died ~30 s in, after creating an empty results directory. 0.76 GPU-h
# for two empty directory entries.
#
# scripts/stage_test_deps.py cannot be used here: it fetches from PyPI, and this
# competition refuses internet with the L4 accelerator. So the wheels travel in
# the lab dataset and are installed offline.
#
# --no-deps is deliberate and load-bearing. inline_snapshot declares
# pytest>=8.3.4 and rich>=13.7.1; letting pip satisfy those could upgrade
# pygments or rich in the interpreter the per-task venvs inherit, and a newer
# Pygments is already a KNOWN cause of benchmark test failures (rich asserts
# guess_lexer(...) == 'python' and newer Pygments answers 'ipython'). Changing
# the test environment to fix the test environment is how a measurement stops
# meaning anything. dirty_equals declares no required deps at all.
# vendor/ mirrors the repo subdirectory for subdirectory: test_deps here, and the
# cp313 wheel overlay (used by cell 3) alongside it.
VENDOR = LAB / 'vendor' / 'test_deps'
say('vendor/test_deps: ' + (str(len(list(VENDOR.glob('*.whl')))) + ' wheels'
                            if VENDOR.is_dir() else 'DIRECTORY MISSING'))

need = ['inline_snapshot', 'dirty_equals']
say('missing before staging: ' + str([m for m in need if importlib.util.find_spec(m) is None]))
assert VENDOR.is_dir(), 'no vendor/test_deps in the lab dataset; re-run scripts/push_dataset.py'


def wheel_for(module_name):
    """Find a vendored wheel providing this IMPORT name.

    Import name and distribution name differ in spelling (underscore vs dash), so
    both are tried. Nothing clever: these are leaf packages.
    """
    stem = module_name.lower()
    for cand in (stem, stem.replace('_', '-'), stem.replace('-', '_')):
        for w in sorted(VENDOR.glob('*.whl')):
            if w.name.lower().startswith(cand + '-'):
                return w
    return None


def pip_install(wheel):
    r = subprocess.run([sys.executable, '-m', 'pip', 'install', '-q',
                        '--no-index', '--no-deps', '--find-links', str(VENDOR), str(wheel)],
                       capture_output=True, text=True)
    importlib.invalidate_caches()
    return r


# Install by following the actual ModuleNotFoundError chain rather than by
# predicting the dependency tree. The previous version installed inline_snapshot
# with --no-deps and assumed the image already had `executing`; it did not, and
# the run died after vLLM had already loaded.
#
# --no-deps plus install-only-what-is-missing is what keeps this safe. The hazard
# was never installing a package, it was UPGRADING one the per-task venvs inherit
# -- a newer Pygments is a known cause of benchmark test failures. A module that
# is absent cannot be downgraded by installing it, and one that is present is
# never requested, so neither pytest nor rich nor pygments can be touched here.
still = []
for m in need:
    for attempt in range(8):
        try:
            importlib.import_module(m)
            say('  import ' + m + ' OK')
            break
        except ModuleNotFoundError as exc:
            miss = getattr(exc, 'name', None) or str(exc)
            w = wheel_for(miss)
            if w is None:
                still.append(m + ' needs ' + str(miss) + ' (no vendored wheel)')
                say('  import ' + m + ' BLOCKED on ' + str(miss) + ': no wheel in vendor/test_deps')
                break
            say('  ' + m + ' needs ' + str(miss) + ' -> installing ' + w.name)
            rr = pip_install(w)
            if rr.returncode != 0:
                still.append(m + ': pip failed on ' + w.name)
                say((rr.stderr or '')[-800:])
                break
        except Exception as exc:
            still.append(m + ': ' + type(exc).__name__ + ': ' + str(exc))
            say('  import ' + m + ' FAILED: ' + type(exc).__name__ + ': ' + str(exc))
            break
    else:
        still.append(m + ': dependency chain deeper than 8')

# Fail HERE, before vLLM spends 2.5 minutes loading 26 GB of weights, rather than
# inside session_runner after the allocation is already committed.
assert not still, (
    'still cannot import ' + str(still) + '. session_runner would exit 4. '
    'Add the missing wheel to vendor/test_deps and re-push the dataset.')

# The harness must still import after touching the environment. This is the check
# whose absence let an earlier run reach a preflight failure instead of stopping.
#
# P003 (2026-10-12) proves this gate has to mirror session_runner's imports
# EXACTLY, not approximately. The old probe imported swegemma.evaluate.Evaluator,
# which still worked, so the gate passed -- and session_runner then died 14 s
# later on `from swegemma.models.discovery import validate_single_declared_model`,
# which the competition removed when it republished the wheelhouse on 2026-10-09.
# That symbol is GONE: the replacement is adk_submission.discover_declared_models
# (P004), and session_runner now enforces the exactly-one-model rule itself.
# A gate that checks a DIFFERENT symbol from the one the script needs is not a
# gate. So every import in start_server() is listed here, and the run stops in
# seconds instead of after a 4-minute torch install and a 26 GB model load.
#
# EXTENDED 2026-10-21 to cover build_config() as well, which was the same bug
# one level down. build_config() runs AFTER start_server(), i.e. after the 26 GB
# load, and it imports two GOOGLE ADK symbols the gate never checked --
# including `google.adk.apps._configs`, a PRIVATE module path. A rename there
# would have killed each arm ~25 minutes in, with the quota already spent, and
# the log would have blamed the harness rather than the import.
#
# Keep this list in sync with scripts/session_runner.py start_server() AND
# build_config(). `import torch` is listed for literal fidelity even though
# TORCH_CELL already deep-checks it.
probe = ('import pydantic, pydantic_core;'
         'import torch;'
         'from adk_submission import VllmConfig, VllmServer, discover_adapters,'
         ' discover_declared_models;'
         'from swegemma.config import ALLOWED_ADAPTER_EXTENSIONS;'
         'from google.adk.agents.context_cache_config import ContextCacheConfig;'
         'from google.adk.apps._configs import EventsCompactionConfig;'
         'from swegemma.config import EvalConfig, build_submission_limits;'
         'from swegemma.evaluate import Evaluator;'
         'print("harness ok", pydantic.VERSION, pydantic_core.__version__)')
h = subprocess.run([sys.executable, '-c', probe], capture_output=True, text=True)
say('harness check: ' + (h.stdout or h.stderr or '').strip()[:300])
if h.returncode != 0:
    # Name the API that moved, so the log says WHAT to fix rather than that
    # something is broken. Each import is retried alone to isolate the failure.
    for one in [x for x in probe.split(';') if x.strip().startswith(('import ', 'from '))]:
        r = subprocess.run([sys.executable, '-c', one], capture_output=True, text=True)
        say('  ' + ('ok  ' if r.returncode == 0 else 'FAIL') + ' ' + one.strip()[:110])
        if r.returncode != 0:
            say('       ' + (r.stderr or '').strip().splitlines()[-1][:200])
assert h.returncode == 0, (
    'the harness API session_runner needs is not importable; refusing to spend '
    'the allocation. The wheelhouse is NOT frozen -- it was republished '
    '2026-10-09 -- so check whether a symbol moved before assuming a bad install.')
'''

RUN_CELL = '''
ARMS = @@arms@@
RUN_PREFIX = '@@run_prefix@@'
TASK_LIST = '@@task_list@@'
MAX_TOOL_CALLS = @@max_tool_calls@@
MAX_TIME_MINUTES = @@max_time_minutes@@
CONCURRENCY = @@concurrency@@
# The per-task cap plus headroom for the model load and the final grade, so the
# subprocess timeout can never fire BEFORE the cap it is meant to backstop.
PER_ARM_TIMEOUT_S = @@per_arm_timeout_min@@ * 60

RUNNER = str(LAB / 'scripts' / 'session_runner.py')
WORK = Path('/kaggle/working')


def archive_everything(tag):
    """Persist after EVERY arm, so a failure in arm 2 cannot lose arm 1.

    This is the probe_c12 lesson: the run succeeded and the output did not come
    home. Archiving is cheap and a partial result is still a result.
    """
    made = []
    for d in ('results', 'ledger'):
        p = WORK / d
        if p.is_dir() and any(p.rglob('*')):
            base = str(WORK / ('eval_' + d))
            shutil.make_archive(base, 'zip', root_dir=p)
            made.append(Path(base + '.zip').name)
    say('[' + tag + '] archived: ' + (', '.join(made) or 'nothing yet'))


summary = []
for arm in ARMS:
    run_id = RUN_PREFIX + arm.split('_')[0]
    cmd = [sys.executable, RUNNER,
           '--lab', str(LAB), '--data', str(DATA), '--model-path', str(MODEL),
           '--variant', arm, '--task-list', TASK_LIST,
           '--run-id', run_id, '--concurrency', str(CONCURRENCY),
           '--max-time-minutes', str(MAX_TIME_MINUTES),
           '--max-tool-calls', str(MAX_TOOL_CALLS),
           '--max-model-len', str(MAX_MODEL_LEN)]
    say('=' * 70)
    say('ARM ' + arm + '  run_id=' + run_id)
    say('  ' + ' '.join(cmd))

    t0 = time.time()
    rc, out, err = -1, '', ''
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=PER_ARM_TIMEOUT_S)
        rc, out, err = proc.returncode, proc.stdout or '', proc.stderr or ''
    except subprocess.TimeoutExpired as exc:
        rc = -9
        out = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b'').decode('utf-8', 'replace')
        err = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b'').decode('utf-8', 'replace')
        err = err + NL + '*** KILLED at ' + str(PER_ARM_TIMEOUT_S // 60) + ' min ***'
    wall = time.time() - t0

    # Full stdout to a file per arm: the ledger is the record, but when a run
    # fails the stdout is the only thing that says why.
    (WORK / ('stdout_' + run_id + '.txt')).write_text(
        NL.join(['rc=' + str(rc), 'wall_s=' + format(wall, '.0f'), '',
                 '=== STDOUT ===', out, '', '=== STDERR ===', err]),
        encoding='utf-8')

    say('  rc=' + str(rc) + '  wall=' + format(wall / 60, '.1f') + ' min')

    # Reprint this arm's ledger rows immediately. An interactive session can be
    # lost at any moment and publishes nothing, so a row that has been printed is
    # banked and a row that has not is gone.
    rows_here = [ln for ln in out.splitlines() if ln.startswith('LEDGER_ROW ')]
    say('  ledger rows echoed by this arm: ' + str(len(rows_here)))
    for ln in rows_here:
        print(ln, flush=True)

    say('  --- stdout tail ---')
    say(out[-6000:] or '(empty)')
    if rc != 0:
        say('  --- stderr tail ---')
        say(err[-3000:] or '(empty)')
    summary.append((arm, run_id, rc, wall))
    archive_everything(arm)

say('=' * 70)
for arm, run_id, rc, wall in summary:
    say(arm.ljust(22) + ' rc=' + str(rc).rjust(3) + '  ' + format(wall / 60, '5.1f') + ' min')
'''

REPORT_CELL = '''
# Echo every ledger row to stdout. Wrapped, because a bug in reporting must
# never hide a successful run -- and the log is recoverable even if a zip is not
# (scripts/recover_from_log.py exists for exactly that).
try:
    for arm in ARMS:
        run_id = RUN_PREFIX + arm.split('_')[0]
        jl = WORK / 'ledger' / 'runs' / run_id / 'task_results.jsonl'
        say('=== LEDGER ' + run_id + ' ===')
        if not jl.is_file():
            say('  MISSING: ' + str(jl))
            continue
        rows = [json.loads(x) for x in jl.read_text(encoding='utf-8').splitlines() if x.strip()]
        say('  rows: ' + str(len(rows)))
        for r in rows:
            say('  ROW ' + json.dumps(r, sort_keys=True))
        n = len(rows) or 1
        say('  resolved  ' + str(sum(1 for r in rows if r.get('resolved'))) + '/' + str(len(rows)))
        say('  gold_hit  ' + str(sum(1 for r in rows if r.get('gold_hit'))) + '/' + str(len(rows)))
        calls = [r.get('tool_calls_used') or 0 for r in rows]
        say('  calls: median ' + str(sorted(calls)[len(calls) // 2]) + '  max ' + str(max(calls)))
        say('  wall:  mean ' + format(sum(r.get('wall_seconds') or 0 for r in rows) / n / 60, '.1f') + ' min')
except Exception as exc:
    say('report cell raised (not fatal): ' + type(exc).__name__ + ': ' + str(exc))

try:
    archive_everything('final')
except Exception as exc:
    say('archive raised (not fatal): ' + str(exc))

say('=== files in /kaggle/working ===')
for q in sorted(WORK.iterdir()):
    say('  ' + q.name + '  ' + (str(q.stat().st_size) if q.is_file() else '(dir)'))

# The copy block. An interactive session publishes nothing, so this printed text
# is the primary record -- not a convenience. Rebuilt from the ledger FILES
# rather than from captured stdout, so it is complete even if an arm's subprocess
# output was truncated. The LEDGER_ROW prefix is what recover_from_log.py parses,
# so it is reapplied here verbatim.
print()
print('=== COPY FROM HERE ===')
total = 0
for arm in ARMS:
    run_id = RUN_PREFIX + arm.split('_')[0]
    jl = WORK / 'ledger' / 'runs' / run_id / 'task_results.jsonl'
    if not jl.is_file():
        print('# MISSING ledger for ' + run_id)
        continue
    for line in jl.read_text(encoding='utf-8').splitlines():
        if line.strip():
            print('LEDGER_ROW ' + line.strip())
            total += 1
print('=== TO HERE ===')
print()
print('rows in block: ' + str(total) + '   (expect @@expect_rows@@: @@n_tasks@@ tasks x @@n_arms@@ arm(s))')
print('Save the block as ledger/incoming/@@log_name@@, then run:')
print('  python scripts/recover_from_log.py --log ledger/incoming/@@log_name@@ --write')
'''

RESOLVE_MARKDOWN = """# 11 - Is the rig able to resolve anything at all?

**One arm, `v00_public_baseline`, the same 12 `probe_c12` tasks, at the grader's
own `max_time_minutes=60`.** This is not a comparison and produces no delta. It
answers a prior question that invalidates every comparison until it is settled.

## The question

| Run | Date | Call ceiling | Time cap | Resolved |
|---|---|---|---|---|
| `probe_c12` | 2026-10-06 | 30 | 30 min | **2 / 12** |
| `paired100_v00` | 2026-10-07 | 100 | 30 min | **0 / 12** |
| `paired100_v03` | 2026-10-07 | 100 | 30 min | **0 / 12** |

Resolution went **down** when the call budget went up. Three causes are not
separated by those runs:

1. **Noise.** At n=12 and k=1, 2/12 and 0/12 are not distinguishable.
2. **Truncation by the 30-minute cap**, which was a deliberate deviation from
   the grader's 60. `paired100_v00` averaged **24.4 min** of wall per task
   against a 30-minute cap, so the cap was plausibly binding, and the ledger row
   does not record whether a task hit it. In a paired comparison that was
   harmless because both arms shared the cap. For an absolute number it is fatal.
3. **The environment changed.** torch 2.10.0 was installed between the two runs.

This run removes cause 2 and re-tests cause 3. It cannot settle cause 1, and is
not intended to: the reading is **binary**. If this returns a non-zero
resolution, the rig measures and the 30-minute cap was the culprit. If it
returns 0/12 with wall times well under 60 minutes, the cap was *not* the
culprit and the 2/12 from `probe_c12` is the thing needing explanation.

**Why `v00` and not `v03`:** `v00` is the arm the 0.13 leaderboard number
belongs to, so a non-zero result here is comparable to something. `v03` is
~3x faster and would be the cheaper probe, but its number would be
uninterpretable against the public baseline.

## Why this gates everything else

A rig that resolves nothing cannot rank bundles: every variant scores 0 and
every delta is 0. The k=4 reference on `clean-N` is the project's headline
number and is priced in GPU-hours; buying it on a rig that cannot resolve would
waste the single largest planned allocation. So this cheap single-arm run comes
first, by design.

## Cost

12 tasks, one arm, concurrency 12, a 60-minute per-task cap and an 80-minute
subprocess backstop. Expect **~1.0-1.5 GPU-h** depending on how many tasks run
the cap out. Budget 45.00 GPU-h/week; this is ~3%.
"""

ANALYZER_MARKDOWN = """# 14 - Does removing the code_analyzer let the agent edit at all?

**Two arms, `v00_public_baseline` then `v05_no_analyzer`, the same 12
`probe_c12` tasks, at the grader's own `max_tool_calls=100` and
`max_time_minutes=60`.** Both arms run in **one session**, which is the whole
point -- see "Why both arms" below.

## The hypothesis, and why it is worth GPU

P005 ran `v00` at this exact shape and resolved 0/12. Re-reading its 12 traces
with corrected call accounting (EXPERIMENTS.md T002) found the mechanism:

| Outcome | n | sub-agent share of charged calls | first charged edit |
|---|---|---|---|
| clean source-only patch | 1 | 0.00 | call 5 |
| source change + leaked scratch | 4 | 0.44 | 1, 11, 15, 81 |
| patch, no source change | 2 | 0.55 | 17, 62 |
| **no patch at all** | **5** | **0.91** | **never** |

**In 4 of the 5 no-patch tasks the agent never called `write_file` or
`edit_file` once in 100 charged calls**; the fifth tried once after exhaustion
and was refused. The `code_analyzer` sub-agent took 90-98% of the budget
re-issuing near-identical calls, and the coder never got a turn.
Spearman(sub-agent share, outcome quality) = **-0.90** over 12 tasks.

`v05` deletes that sub-agent and gives its tools to the coder, so the agent
loses no capability. If the gradient is causal, those 5 tasks should start
producing patches.

## What is being measured, and what decides

**`gold_hit` is the read.** It needs no test execution, and it is exactly the
quantity the mechanism predicts: a task that never edits has no files, so it
scores 0 by construction. Resolution comes free from the same run and is
reported, but **`resolved` is what authorises shipping and `gold_hit` only
ranks** -- see CLAUDE.md. Optimising a surrogate is how you win the surrogate.

| Quantity | `resolve60_v00` (P005) |
|---|---|
| `gold_hit` | **3 / 12 = 0.250** |
| `gold_exact` | 1 / 12 |
| `resolved` | 0 / 12 |

## Power, stated before the run

`se_unit` is ~0.030 on the 129 public tasks, so on 12 tasks it is
~0.030 * sqrt(129/12) = **0.098**, and at k=1 against k=1 the detectable delta
is **~0.24** -- about 3 of 12 tasks flipping. The mechanism targets 5 tasks, so
**this run is adequately powered for the effect it predicts and honestly
underpowered for anything smaller.** A delta of +0.08 (one task) will not be
distinguishable from noise and must not be read as one.

## Why both arms, when one would have cost half

This kernel was first written with a single `v05` arm, paired against
`resolve60_v00`'s existing rows: same task list, same caps, same pinned image,
and the wheelhouse verified at `lastUpdated 2026-10-09 14:43:19` on 2026-10-12.
At k=1 against k=1 that has the same detectable delta as two fresh arms, for
half the quota.

**That design is dead, and the reason is the point.** Re-checking before launch
on 2026-10-13 showed the wheelhouse republished at **2026-10-12 19:51:31** --
hours after the check that cleared it. P005 ran against the 10-09 build, so a
`v05` arm run today would be compared across a dependency-stack change, and
**nothing in the ledger would record that it happened.** The wheelhouse arrives
as `dataset_sources`, which always resolves to latest; `docker_image_pinning_type`
pins the image only and no setting of ours freezes it.

So both arms run in one session, where they are immune to this by construction.
The extra ~2 GPU-h buys the only thing that makes the delta mean anything.

Same task list, same caps, same bundle hashes recorded per row. vLLM is not
bitwise deterministic under continuous batching, so neither arm reproduces
itself anyway; the pairing is per-task, which is what `compare_arms` reads.

**A CPU probe (`kernels/13_harness_api`, 0 GPU-h) is re-run against the new
wheelhouse before this kernel is pushed.** P003 died 14 s into a GPU allocation
on an import that a wheelhouse republication had deleted; checking costs
nothing and that failure cost 0.23 GPU-h.

## How to read the result

- **`gold_hit` up by >= 0.25** -- the mechanism is real and `v05` acts on it.
  Then, and only then, buy a confirming arm and read `resolved`.
- **`gold_hit` flat** -- heavy analyzer use was a *symptom* of hard tasks, not
  their cause. Retire the bundle; do not tune it.
- **`gold_hit` up but the coder's own re-issue rate rises to absorb the freed
  budget** -- the pathology relocated rather than disappeared. Retire it. This
  is the bundle's own `rejected_alternative` argument turned against itself.

## Cost

12 tasks, **two arms**, concurrency 12, a 60-minute per-task cap and an
80-minute subprocess backstop per arm. P005 cost **2.02 GPU-h** for one arm at
this exact shape, so expect **~4.0-5.0 GPU-h**. Budget 45.00 GPU-h/week with
42.75 h remaining; this is ~11%. Priced against the cap rather than a previous
run's mean, which is the error that made P005 land 35% over estimate.

Each arm's ledger rows are echoed to the log the moment that arm finishes, so a
session lost during arm 2 still banks arm 1.
"""

#: One entry per GPU run shape. Named rather than assembled from loose flags,
#: because the notebook, the kernel id and the markdown must all agree -- and
#: because a run shape is a thing this project refers to by name afterwards.
#:
#: `paired100` reproduces the 2026-10-07 paired kernel exactly; regenerating it
#: must leave `kernels/10_run_eval/` byte-identical.
CAP60_MARKDOWN = """# 17 - Does the decode clamp still help at the GRADER'S 60-minute cap?

**Two arms, `v00_public_baseline` then `v08_decode_clamp`, over **36** tasks
(`clean_dev36`, a seed-1001 sample of the 60 in `clean_dev`), at
`max_tool_calls=100` and `max_time_minutes=60` -- the grader's real cap.** Both
arms in **one session**.

## Why this run exists

P008 found the clamp works: timeouts 26/60 -> 16/60 (p=0.0525) and `gold_hit`
29/60 -> 40/60 (15 gained / 4 lost, p=0.0192), with the mechanism confirmed
(p99 completion tokens per step 4,132 -> 1,308; steps over 2048 down 114 -> 11;
median step untouched at 38 -> 37; ~1,300 MORE steps out of 11% LESS decode).

**But P008 ran at a 30-minute cap, which FAVOURS the faster arm by
construction** -- that bias was pre-registered, and it is the reason P008 cannot
settle whether this bundle is worth anything on the grader. The grader runs
**60** minutes. If the clamp only converts timeouts when the cap is artificially
tight, it buys nothing where it matters.

Timeouts are known to bind at 60 minutes too: P006 put v00 at **6/12** hitting a
60-minute cap. So there is room for the clamp to help. This run measures whether
it does.

## Why 36 tasks, and how they were chosen

KV on L4x4 is **55,616 tokens**, so concurrency cannot exceed ~10.5x at full
context and stays at 12. At a 60-minute cap each wave costs a full hour:

| tasks | waves | per arm (+25 min load) | two arms | wall | GPU-h at ~2x |
|---|---|---|---|---|---|
| 60 | 5 | 325 min | 650 min | **10.8 h** | ~21.7 -- above the 9 h end of the session cap |
| **36** | **3** | **205 min** | **410 min** | **6.8 h** | **~13.7** |

**The 36 are a seeded random sample (seed 1001), taken once and used as drawn.**
They were NOT selected on P008 outcomes -- doing so would manufacture the result
this run is meant to test. For transparency the draw happens to be slightly
CONSERVATIVE: within it, P008's gap was gold_hit 17/36 vs 22/36 (+0.139) against
+0.183 over the full 60.

## Pre-registered reading

The endpoints and their order are unchanged from P008; only the cap moves.

- **timeouts down and `gold_hit` up** -> the clamp works at the cap that ships.
  This is the result that would make v08 the best bundle the project has.
- **timeouts down but `gold_hit` flat** -> the clamp buys completion without
  buying localization at 60 min; P008's `gold_hit` gain was a 30-minute artifact.
- **timeouts flat** -> at 60 minutes the long-decode tail no longer decides the
  outcome, and the clamp is irrelevant to the grader however well it worked at 30.

`resolved` is reported and remains the only metric that authorizes shipping, but
**this run cannot adjudicate it** -- it is n=36 against a base rate near 0.05.
Saying so now prevents a one-task swing being read as a finding later.

## Not a time series

**Not comparable to P005/P006/P007/P008 row-for-row** -- different cap, and for
P008 a different task set. The comparison that counts is the two arms inside this
session.
"""


DECODE_MARKDOWN = """# 18 - Does GREEDY DECODE produce better patches?

**Two arms, `v10_clamp_timecap` (control, `temperature: 0.2`) then `v11_greedy`
(`temperature: 0.0`), over the 60 fastapi tasks of `clean_dev`, at
`max_tool_calls=100` and `max_time_minutes=30` -- the cap both bundles ship in
their own `eval_config.yaml`.** Both arms in **one session**. Pairing across
sessions is never an option here: identical v00 bytes read `gold_hit` 36/60 and
29/60 in two sessions, and one cross-session pairing read **+0.167 where the
truth was 0.000**.

## Why this run exists

Nine bundles have failed to beat the competition's own published baseline. Every
one of them moved navigation, budget, topology or `thinking_budget`.
**`temperature: 0.2 / top_p: 0.95 / top_k: 40` is byte-identical in all ten
bundles built so far** (verified 2026-10-21). Decode sampling is the one knob
class never varied, and it is one schema-legal line.

The mechanism is about error tolerance, not intelligence. Prose tolerates a
suboptimal token; **a diff does not.** An `edit_file` argument has to name a real
identifier and reproduce its context exactly, so one plausible-but-wrong token
inside a hunk means the patch fails to apply, or applies and fails its test.
`resolved` is binary per task. At temperature 0.2 the model samples on every
token, including those. Greedy decode takes the argmax instead.

## The arms differ by ONE line

| | `v10_clamp_timecap` | `v11_greedy` |
|---|---|---|
| `temperature` | **0.2** | **0.0** |
| `top_p` / `top_k` | 0.95 / 40 | 0.95 / 40 (inert at t=0, deliberately untouched) |
| `thinking_budget` | 1024 | 1024 |
| `eval_config.yaml` | `max_time_minutes: 30` | byte-identical |
| prompts, topology, tools | | byte-identical |
| `bundle_hash` | `9033b8826a9add43` | `422e1a0746a14400` |

`diff -r` reports two differing files: `MANIFEST.yaml` (lab metadata, never
shipped) and `configs/sampling.yaml`, whose only non-comment difference is the
`temperature:` line.

## `resolved` DECIDES. `gold_hit` DOES NOT.

`gold_hit` is **retired as a ranking metric** and appears here as a descriptive
column only. Same-byte sessions swung it **0.117** -- larger than the effect it
was being used to detect. A `gold_hit` gain is not a reason to ship v11 and a
`gold_hit` loss is not a reason to kill it. `stats.decide` keys on `resolved`.

## Power, stated before the run, and it is unflattering

`se_unit` is ~0.030 on 129 tasks, so ~0.044 on 60, and `detectable_delta` at
**k=1 per arm is 0.093** -- about 6 of 60 tasks. Against the 0.05 design target
`stats.is_underpowered` returns True, so the honest verdict space is
**UNDERPOWERED** or an effect large enough to be surprising.

The base rate is the harder problem, not n. P007 saw `resolved` 3/60 vs 3/60
with **zero discordant pairs**. k=2 at this shape is ~11.6 h of wall clock, past
the 9-12 h session cap; k=2 on 36 tasks detects 0.085, no better, for more
quota. **So no affordable local design adjudicates `resolved` at this base
rate**, and that is said here rather than discovered afterwards.

What this run can genuinely read is the **guard-rail**, below -- which is where
greedy decode would do its damage.

## The guard-rail, and the pre-registered kill

Greedy decode is deterministic given the context, so an agent that re-reads the
same file and re-issues the same failing edit can get **the same tokens back**.
The validator warns about exactly this: *"temperature 0 can trap the agent
re-issuing one failing edit forever; because it keeps calling tools the 3-nudge
rule never fires and the budget drains."* The pathology is measured here, not
hypothetical: `reissue_rate` rose **+0.151** when a budget was freed, with
**174** `submit_patch` calls in one task and **136** malformed `edit_file` in
another.

So this notebook computes `reissue_rate`, `coder_call_share`, `counted_calls`
and `workspace_writes` per arm **on Kaggle, into the log**, not only into the
results zip -- a guard-rail that arrives only when the run went well is not one.

**KILL CRITERION: `d_reissue_rate >= +0.100` paired, or any task in the v11 arm
with a pathological repeat count that has no counterpart in v10, refutes the
knob.** Do not then retune to 0.1: what is refuted is determinism, not the size
of 0.2.

## Pre-registered readings

Full version in `bundles/v11_greedy/MANIFEST.yaml`, written before any result
existed. In short:

- **`resolved` up significantly** -> the first intervention in eleven bundles to
  move the ship metric. Check the discordant-pair count by hand first; this
  outcome requires a large effect given the power above.
- **`resolved` flat, UNDERPOWERED** -> **the expected outcome.** The knob is not
  refuted, it is unmeasured. Record it as UNDERPOWERED, never as HOLD. Then
  decide on the guard-rail: reissue flat-or-down and timeouts flat-or-down means
  greedy is free, and a free change to the one untried knob class is worth a
  submission slot.
- **reissue rate up materially** -> killed, see above.
- **`resolved` down significantly** -> sampling was load-bearing; the jitter was
  buying escape from local minima. That is a real result and worth the quota: it
  closes the last untried knob class.
- **timeouts up** -> read with the reissue rate. Greedy changes which tokens are
  produced, not how many, so a timeout rise is most likely the loop.

## Read nothing else off this run

- **Not the leaderboard.** The private set is 58 tasks, one task is 0.0172, and
  identical bytes have scored 0.12 / 0.13 / 0.15.
- **Not a time series** against P005-P009. Different cap, different task set,
  different control arm -- the control here is **v10**, not v00.
- **Count the rows before reading anything: expect 120** (60 x 2). P009 v1
  returned 0 rows and still reported COMPLETE.

## Cost: ~10.5-13 GPU-h, from a MEASURED run of this exact shape

**P008 ran 60 tasks, 2 arms, concurrency 12, a 30-minute cap -- identical to
this -- and cost 10.57 GPU-h.** That measurement is the estimate, not an
arithmetic reconstruction of it. The arithmetic is shown only as a check: 5
waves x 30 min = 150 min of agent time per arm, plus ~25 min for install and the
26 GB model load, is ~175 min per arm and ~5.8 h of wall for two, which at the
measured ~2 GPU-h per wall hour on L4 x4 gives ~11.7 -- consistent with 10.57.

Plan against **13 GPU-h**, for two reasons that are specific rather than
cautious. P008's estimate of ~6 GPU-h came from pricing waves and quoting them
as GPU-hours, a 1.76x underrun; and P009 saw the competition shard take 1,059 s
to read from `/kaggle/input` against 89.78 s on 2026-10-01, which is load time
nobody can predict. Against it: **both arms here carry the clamp**
(`thinking_budget: 1024`), where P008's control arm was the slow 4096 one, so
this should run no longer than P008 did.

`kaggle quota` read **27.78 h remaining, refreshing 2026-10-24** at 2026-10-21
14:0x UTC -- but a cap60 run was still RUNNING at that moment and had not
finished drawing. **Re-read `kaggle quota` before pushing**; if the margin is
under ~15 h, wait for the 10-24 refresh rather than running a half-sized version.
Well inside the 9-12 h session cap either way.

Each arm's ledger rows are echoed the moment that arm finishes, so a session
lost during arm 2 still banks arm 1.
"""


CLAMP_MARKDOWN = """# 16 - Does clamping the thinking budget convert timeouts into completions?

**Two arms, `v00_public_baseline` then `v08_decode_clamp`, over the 60 fastapi
tasks of `clean_dev`, at `max_tool_calls=100` and `max_time_minutes=30`.** Both
arms in **one session** -- pairing across sessions is not an option (identical
v00 bytes scored gold_hit 3/12 and 5/12 in two different sessions).

## The hypothesis

v08 is v00 with ONE knob moved: `thinking_budget` 4096 -> 1024. Prompts,
topology, tools, temperature, top_p, top_k and `max_output_tokens` are
byte-identical.

T007 established, over P007's 120 task-runs, that per-step latency is set by
**decode and essentially nothing else**:

    corr(completion tokens per step, seconds per step) = +0.968
    corr(prompt     tokens per step, seconds per step) = -0.437

    v00 timed out  (n=22): 36 steps, 50.6 s/step, 712 completion tok/step
    v00 completed  (n=38): 95 steps, 16.5 s/step, 212 completion tok/step
                           prompt tok/step 7,551 vs 8,691 -- essentially equal

and that verbosity buys no quality: binned by verbosity, seconds per step rise
10.6 -> 58.4 while `gold_hit` FALLS 10/15 -> 7/15. Two rival explanations were
tested and killed -- context growth (prompt tokens are 97% of all tokens yet
correlate negatively with latency) and our own concurrency (timed-out tasks ran
at LOWER contention, median 9 vs 11).

The clamp value is chosen from the per-step distribution over 8,422 observed
agent steps -- p50=40, p75=186, p90=625, p95=1,199, p99=4,123, max=8,192 -- which
is skewed enough that **1024 touches only 6.1% of steps while removing ~29.6% of
total decode.**

## The primary endpoint is the TIMEOUT RATE, not resolution

This is a power argument, not a preference, and it is the whole reason this run
is affordable. In P007, at this exact shape:

| endpoint | result | verdict |
|---|---|---|
| `resolved` | 3/60 vs 3/60, **zero** discordant pairs | UNDERPOWERED, ranked nothing |
| `gold_hit` | 36/60 vs 31/60, 5 gained / 10 lost | null, p=0.302 |
| **timeout rate** | **22/60 vs 35/60, 17 / 4** | **p=0.0072** |

The timeout rate is the only endpoint this project has ever moved detectably at
affordable k. Resolution remains the ship metric and is reported, but it is not
what this run is sized for.

## Why a 30-minute cap and not the grader's 60

Arithmetic, not preference. KV on L4x4 is **55,616 tokens**, i.e. max ~10.5x
concurrency at full context, so concurrency cannot rise above 12 to buy waves --
it would only add preemption. 60 tasks at concurrency 12 is therefore **5 waves**:

| cap | waves | per arm (+25 min load) | two arms | fits a 9-12 h session? |
|---|---|---|---|---|
| 60 min (the grader's) | 5 | 325 min | **10.8 h** | **no, and with no margin** |
| **30 min** | 5 | **175 min** | **5.8 h** | yes -- P007's proven shape |

**The cap is not neutral, and its bias is the OPPOSITE of P007's.** A tighter cap
*favours* the faster arm, and v08 is the faster arm by construction. So a
positive result here is **weaker than it looks**, and a null is **strong against**
v08. That is the mirror image of the warning on run 15, and it is stated in
advance so it cannot be discovered afterwards.

Timeouts are known to bind at the grader's cap too -- P006 put v00 at 6/12
hitting 60 minutes -- so this is a mechanism check at a tighter cap, not a claim
about the grader's absolute rate.

## Pre-registered readings

Full version in `bundles/v08_decode_clamp/MANIFEST.yaml`. In short:

- **timeout rate down significantly, `gold_hit` flat or up** -> the mechanism
  works. First bundle to move the binding constraint.
- **timeout rate down, `gold_hit` down by more** -> clamping is NOT free. The
  quality cost is real; retry at 2048 (2.5% of steps, 14% of decode).
- **timeout rate flat** -> `thinking_budget` was not what produced the long
  steps. Steps were observed at exactly 8,192 tokens, i.e. hitting
  `max_output_tokens` rather than the thinking cap, so the long steps are long in
  VISIBLE output. That is a different bundle, not a retune of this one.

**Not comparable to P005/P006 as a time series** -- different cap. P007's v00 arm
ran this same shape, so it is a useful consistency check on the environment, but
the comparison that counts is the two arms inside THIS session.
"""


GRAPH_MARKDOWN = """# 15 - Does giving the coder the graph tools improve localization?

**Two arms, `v00_public_baseline` then `v06_graph_coder`, over the 60 fastapi
tasks of `clean_dev`, at `max_tool_calls=100` and a deliberately reduced
`max_time_minutes=30`.** Both arms in **one session** -- P006 settled that
pairing across sessions is not an option (identical v00 bytes scored gold_hit
3/12 and 5/12 in two sessions).

## The hypothesis

v06 gives the ROOT coder `search_similar_code` and `get_code_neighbors`, which
in v00 only the read-only `code_analyzer` sub-agent holds. The coder has always
navigated with `grep` and with `read_file`, which returns at most **150 lines /
10,000 chars** per charged call. `search_similar_code(query, k)` returns the
full source of the top-k symbols in ONE charged call. The claim is that the
coder has been denied the cheaper instrument, and that this costs localization.

Pre-registered reading is in `bundles/v06_graph_coder/MANIFEST.yaml`. The
primary metric is **gold_hit**, not resolution: P005 and P006 both returned
0/12 resolved, so resolution cannot rank anything at affordable k.

## Why 60 tasks and a 30-minute cap, not 12 tasks and 60 minutes

This is a power decision, taken against this project's own D4 arithmetic rather
than by habit.

| shape | n | paired SE (gold_hit) | detectable delta | cost |
|---|---|---|---|---|
| 12 tasks, 60 min (P006's shape) | 12 | ~0.17 | ~0.42 | ~4.4 GPU-h |
| 24 tasks, 60 min | 24 | ~0.12 | ~0.30 | ~5 GPU-h |
| **60 tasks, 30 min** | **60** | **~0.065** | **~0.16** | **~6 GPU-h** |

A 12-task run cannot see an effect smaller than 0.42, which no capability change
will produce. Halving the per-task cap doubles the number of tasks per GPU-hour,
and n buys power faster than per-task realism does **for a ranking question**.

**The cap is not neutral, and that is stated deliberately.** At 30 minutes most
tasks are truncated: in P006 v00's median wall was 60.4 min with 6 of 12 tasks
terminated by the 60-minute cap. So this run measures *gold_hit reachable within
30 minutes*, which **favours** v06's efficiency claim by construction. A null
here is therefore strong evidence against v06; a positive result is weaker than
it looks and must be confirmed at 60 minutes before anything is concluded about
the grader.

Both arms share the cap and the comparison is paired per task, so the cap cannot
favour either arm.

## What must not be read off this run

- **Not resolution.** Under a 30-minute cap resolution is near-useless, and
  these rows are NOT comparable to P005/P006's 60-minute rows. Do not put them
  in a time series with them.
- **Not the leaderboard.** v06 was submitted 2026-10-13; its 58-task private
  score is the ship authority and this run is only a pre-filter.
- **Context deaths first.** v06 pipes symbol source into the ROOT context, whose
  input ceiling is 32768 - 8192 = 24,576 tokens. Count
  `ContextWindowExceededError` in the `error` field BEFORE reading gold_hit. If
  it rose, v06 is refuted on mechanics.

## Cost

60 tasks x 2 arms, concurrency 12, 30-minute per-task cap, 45-minute per-arm
subprocess backstop per wave. 5 waves per arm at ~30 min = ~2.5 h per arm, so
~5 h of agent time plus ~1 h for install and model load: **~6 GPU-h**, about 16%
of the 38.40 h remaining on 2026-10-13. Well inside the 9-12 h session cap.
"""


CONFIGS = {
    "paired100": {
        "out_dir": "kernels/10_run_eval",
        "notebook": "10_run_eval.ipynb",
        "kernel_id": "ahmedsherif382/swegemma-paired-eval",
        "kernel_title": "swegemma paired eval",
        "markdown": PAIRED_MARKDOWN,
        # v00 is the reference the leaderboard number belongs to; v03 is the
        # variant under test. Paired on the same 12 tasks so the comparison is
        # within-task rather than between-samples.
        "arms": ("v00_public_baseline", "v03_budget_guard"),
        "run_prefix": "paired100_",
        "task_list": "probe12.txt",
        "max_tool_calls": 100,
        "max_time_minutes": 30,
        "concurrency": 12,
        "per_arm_timeout_min": 70,
        "log_name": "paired100.log",
    },
    "resolve60": {
        "out_dir": "kernels/11_resolve_check",
        "notebook": "11_resolve_check.ipynb",
        "kernel_id": "ahmedsherif382/swegemma-resolve-check",
        "kernel_title": "swegemma resolve check",
        "markdown": RESOLVE_MARKDOWN,
        "arms": ("v00_public_baseline",),
        "run_prefix": "resolve60_",
        "task_list": "probe12.txt",
        "max_tool_calls": 100,
        # The grader's own cap. The whole point of the run.
        "max_time_minutes": 60,
        "concurrency": 12,
        # 60-minute cap + 20 for the 26 GB model load and the final grade.
        "per_arm_timeout_min": 80,
        "log_name": "resolve60.log",
    },
    # BOTH arms in one session, deliberately. The cheaper design -- one v05 arm
    # paired against `resolve60_v00`'s existing rows -- was built and then
    # abandoned on 2026-10-13, because the wheelhouse was republished
    # 2026-10-12 19:51 UTC, hours after the check that cleared it. P005 ran on
    # the 10-09 wheelhouse, so pairing across it would be confounded with
    # nothing in the ledger to show it. Same-session arms are immune by
    # construction, and that is worth the extra ~2 GPU-h.
    "analyzer_v05": {
        "out_dir": "kernels/14_analyzer_ab",
        "notebook": "14_analyzer_ab.ipynb",
        "kernel_id": "ahmedsherif382/swegemma-analyzer-ab",
        "kernel_title": "swegemma analyzer ab",
        "markdown": ANALYZER_MARKDOWN,
        "arms": ("v00_public_baseline", "v05_no_analyzer"),
        "run_prefix": "analyzer_",
        "task_list": "probe12.txt",
        "max_tool_calls": 100,
        # Identical to resolve60, because the comparison is against its rows.
        "max_time_minutes": 60,
        "concurrency": 12,
        "per_arm_timeout_min": 80,
        "log_name": "analyzer_v05.log",
    },
    # v00 vs v06: does the coder's own access to the graph tools move
    # localization? Sized for POWER, not for realism -- 60 tasks at a 30-minute
    # cap detects ~0.16 where P006's 12-task/60-minute shape detected ~0.42, for
    # ~1.5 GPU-h more. See GRAPH_MARKDOWN for why the cap is not neutral.
    "graph_v06": {
        "out_dir": "kernels/15_graph_ab",
        "notebook": "15_graph_ab.ipynb",
        "kernel_id": "ahmedsherif382/swegemma-graph-ab",
        "kernel_title": "swegemma graph ab",
        "markdown": GRAPH_MARKDOWN,
        "arms": ("v00_public_baseline", "v06_graph_coder"),
        "run_prefix": "graph_",
        "task_list": "clean_dev.txt",
        "max_tool_calls": 100,
        # Halved deliberately to buy n. NOT comparable to the 60-minute runs.
        "max_time_minutes": 30,
        "concurrency": 12,
        # 5 waves x 30 min = 150, plus 25 for the 26 GB model load and grade.
        "per_arm_timeout_min": 175,
        "log_name": "graph_v06.log",
    },
    # v00 vs v08: does clamping the thinking budget convert timeouts into
    # completions? The primary endpoint is the TIMEOUT RATE -- the only endpoint
    # this project has moved detectably at affordable k (P007: p=0.0072, where
    # resolved had zero discordant pairs). Same shape as graph_v06 because the
    # 60-minute cap does not fit two arms in one session: 5 waves x 60 min + load
    # is 10.8 h. See CLAMP_MARKDOWN -- the cap's bias here FAVOURS v08.
    "clamp_v08": {
        "out_dir": "kernels/16_clamp_ab",
        "notebook": "16_clamp_ab.ipynb",
        "kernel_id": "ahmedsherif382/swegemma-clamp-ab",
        "kernel_title": "swegemma clamp ab",
        "markdown": CLAMP_MARKDOWN,
        "arms": ("v00_public_baseline", "v08_decode_clamp"),
        "run_prefix": "clamp_",
        "task_list": "clean_dev.txt",
        "max_tool_calls": 100,
        # 30, not the grader's 60: KV caps concurrency at ~10.5x so 60 tasks is
        # 5 waves, and 5 x 60 + load exceeds the session cap for two arms.
        "max_time_minutes": 30,
        "concurrency": 12,
        # 5 waves x 30 min = 150, plus 25 for the 26 GB model load and grade.
        "per_arm_timeout_min": 175,
        "log_name": "clamp_v08.log",
    },
    # v00 vs v08 at the GRADER'S 60-minute cap. P008 showed the clamp works at
    # 30 min, but that cap favours the faster arm by construction, so it cannot
    # say whether the bundle helps where it ships. 36 tasks because a 60-min cap
    # makes each of 3 waves cost an hour: 5 waves would be 10.8 h wall, above the
    # 9 h end of the session cap. See CAP60_MARKDOWN.
    "cap60_v08": {
        "out_dir": "kernels/17_cap60_ab",
        "notebook": "17_cap60_ab.ipynb",
        "kernel_id": "ahmedsherif382/swegemma-cap60-ab",
        "kernel_title": "swegemma cap60 ab",
        "markdown": CAP60_MARKDOWN,
        "arms": ("v00_public_baseline", "v08_decode_clamp"),
        "run_prefix": "cap60_",
        # Seed-1001 sample of clean_dev, taken once and used as drawn.
        "task_list": "clean_dev36.txt",
        "max_tool_calls": 100,
        # The grader's real cap. This is the whole point of the run.
        "max_time_minutes": 60,
        "concurrency": 12,
        # 3 waves x 60 min = 180, plus 25 for the 26 GB model load and grade.
        "per_arm_timeout_min": 205,
        "log_name": "cap60_v08.log",
    },
    # v10 vs v11: GREEDY DECODE. The control is v10, NOT v00, because v11 is v10
    # with one line moved -- `temperature: 0.2 -> 0.0`. Decode sampling is the
    # one knob class never varied in ten bundles, all of which ship an identical
    # `temperature: 0.2 / top_p: 0.95 / top_k: 40`.
    #
    # `resolved` is primary and `gold_hit` is descriptive only: same-byte
    # sessions swung gold_hit 0.117, larger than the effects it was ranking.
    #
    # The cap is 30 because that is what BOTH bundles ship in their own
    # eval_config.yaml -- so the measurement is taken at the value that would
    # ship, and 60 tasks at concurrency 12 still fits one session (5 waves).
    #
    # `assert_gpu` and `guardrail_traces` are set here and nowhere else. The
    # first stops a non-L4 allocation in seconds; the second prints reissue/loop
    # rate into the LOG, which is the pre-registered kill criterion for greedy
    # decode and would otherwise only exist inside the results zip.
    "decode_v11": {
        "out_dir": "kernels/18_decode_ab",
        "notebook": "18_decode_ab.ipynb",
        "kernel_id": "ahmedsherif382/swegemma-decode-ab",
        "kernel_title": "swegemma decode ab",
        "markdown": DECODE_MARKDOWN,
        "arms": ("v10_clamp_timecap", "v11_greedy"),
        "run_prefix": "decode_",
        "task_list": "clean_dev.txt",
        "max_tool_calls": 100,
        # The bundles' OWN shipped cap, not a deviation chosen for cost.
        "max_time_minutes": 30,
        "concurrency": 12,
        # 5 waves x 30 min = 150, plus 25 for the 26 GB model load and grade.
        "per_arm_timeout_min": 175,
        "log_name": "decode_v11.log",
        "assert_gpu": "L4",
        "assert_task_list": True,
        "guardrail_traces": True,
    },
}


def metadata_for(cfg: dict) -> dict:
    """Kernel metadata. Everything but the identity is shared across configs."""
    return {
    "id": cfg["kernel_id"],
    "title": cfg["kernel_title"],
    "code_file": cfg["notebook"],
    "language": "python",
    "kernel_type": "notebook",
    "is_private": True,
    "enable_gpu": True,
    "enable_tpu": False,
    # This competition refuses internet with the premium accelerator, and the
    # wheelhouse is attached as a dataset, so nothing here needs PyPI.
    "enable_internet": False,
    # L4 x4 = 92 GB, the only shape that holds the weights plus a 32k context.
    # enable_gpu alone gets whatever is free, which once handed us a dead T4 x2.
    "machine_shape": "NvidiaL4",
    # Pin the environment, now for REPRODUCIBILITY rather than as a workaround.
    #
    # Kaggle moved the GPU image to Python 3.13 on 2026-10-07 and the wheelhouse
    # is cp312. Pinning does NOT undo that -- "original" resolves to today's
    # image, confirmed by KAGGLE_DOCKER_IMAGE on the running container matching
    # the pinned digest exactly (sha256:2757e0c7...). The real fix is the cp313
    # overlay in vendor/cp313, shipped via push_dataset.
    #
    # What the pin buys instead: the image stops moving under us mid-experiment.
    # A measurement whose dependency stack can change between arms is not a
    # paired comparison, and this is the second image change in two days.
    # Valid values are "original" and "latest" (kaggle_api_extended.py:942).
    "docker_image_pinning_type": "original",
    "dataset_sources": [
        "ahmedsherif382/swegemma-lab",
        "metric/gemma-4-developer-agent-wheelhouse",
    ],
    "competition_sources": ["gemma-4-developer-agent"],
    "model_sources": ["google/gemma-4/other/gemma-4-31b-it-qat-w4a16-ct/2"],
    # The CPU kernel that fetched torch 2.10.0+cu128. The wheelhouse's vllm-0.19.1
    # declares torch==2.10.0 and the GPU image ships 2.11.0+cu128, so vllm/_C fails
    # to link against a libtorch C++ symbol. torch is not in the wheelhouse and
    # this kernel has no internet, so its output rides in as a data source.
    "kernel_sources": ["ahmedsherif382/swegemma-fetch-torch"],
    }


def code_cell(source: str) -> dict:
    lines = source.strip("\n").split("\n")
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [ln + "\n" for ln in lines[:-1]] + [lines[-1]],
    }


def md_cell(source: str) -> dict:
    lines = source.strip("\n").split("\n")
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": [ln + "\n" for ln in lines[:-1]] + [lines[-1]],
    }


def build(cfg: dict) -> int:
    """Write one config's notebook and kernel metadata."""
    out_dir = ROOT / cfg["out_dir"]
    out_nb = out_dir / cfg["notebook"]

    # The task list is read here only to state the expected row count in the
    # notebook's own output, so a short ledger is visible as short in the log.
    task_file = ROOT / "data" / "tasks" / cfg["task_list"]
    assert task_file.is_file(), f"no such task list: {task_file}"
    n_tasks = len([x for x in task_file.read_text(encoding="utf-8").splitlines() if x.strip()])
    arms = list(cfg["arms"])
    tokens = {
        "arms": repr(arms),
        "run_prefix": cfg["run_prefix"],
        "task_list": cfg["task_list"],
        "max_tool_calls": cfg["max_tool_calls"],
        "max_time_minutes": cfg["max_time_minutes"],
        "concurrency": cfg["concurrency"],
        "per_arm_timeout_min": cfg["per_arm_timeout_min"],
        "log_name": cfg["log_name"],
        "n_tasks": n_tasks,
        "n_arms": len(arms),
        "expect_rows": n_tasks * len(arms),
    }

    smoke = json.loads(SMOKE.read_text(encoding="utf-8"))
    cells = [md_cell(cfg["markdown"])]
    # Cells 1-3 discover sources and build the wheel plan; TORCH_CELL then puts the
    # right torch in place; cell 4 installs the wheelhouse against it and verifies
    # that vllm/_C links. The torch step MUST precede cell 4, or cell 4's deep
    # import check would be testing the wrong torch.
    cells.append(smoke["cells"][1])
    # Straight after the cell that runs `nvidia-smi`, so a wrong accelerator
    # stops the run in seconds rather than after a 4-minute torch install.
    # MEM_GB, MAX_MODEL_LEN and nvsmi() are all defined by that cell.
    if cfg.get("assert_gpu"):
        cells.append(code_cell(fill(GPU_ASSERT_CELL, want_gpu=cfg["assert_gpu"])))
    cells += [smoke["cells"][i] for i in (2, 3)]
    # Fail on a missing bundle BEFORE the torch install, not after arm 1.
    cells.append(code_cell(fill(BUNDLE_GATE_CELL, **tokens)))
    if cfg.get("assert_task_list"):
        cells.append(code_cell(fill(TASK_LIST_GATE_CELL, **tokens)))
    cells.append(code_cell(TORCH_CELL))
    cells.append(smoke["cells"][4])
    # MAX_MODEL_LEN is set by the smoke notebook's own cells; assert it exists so
    # a refactor there cannot silently leave it undefined here.
    reused = "".join("".join(smoke["cells"][i]["source"]) for i in REUSE_CELLS)
    cells.append(code_cell(
        "assert 'MAX_MODEL_LEN' in dir() or 'MAX_MODEL_LEN' in globals(), (\n"
        "    'MAX_MODEL_LEN is not defined; the reused setup cells changed')\n"
        "say('MAX_MODEL_LEN=' + str(MAX_MODEL_LEN))"
    ) if "MAX_MODEL_LEN" in reused else code_cell(
        "# The smoke notebook sets MAX_MODEL_LEN in a cell this kernel does not\n"
        "# reuse, so it is set here, at the grader's value.\n"
        "MAX_MODEL_LEN = 32768\n"
        "say('MAX_MODEL_LEN=' + str(MAX_MODEL_LEN))"
    ))
    cells.append(code_cell(STAGE_DEPS_CELL))
    cells.append(code_cell(fill(RUN_CELL, **tokens)))
    if cfg.get("guardrail_traces"):
        cells.append(code_cell(GUARDRAIL_CELL))
    cells.append(code_cell(fill(REPORT_CELL, **tokens)))

    nb = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_nb.write_text(json.dumps(nb, indent=1), encoding="utf-8", newline="\n")
    (out_dir / "kernel-metadata.json").write_text(
        json.dumps(metadata_for(cfg), indent=2) + "\n", encoding="utf-8", newline="\n")

    # Compile every code cell. A SyntaxError discovered on Kaggle costs the whole
    # allocation; discovered here it costs nothing.
    for i, c in enumerate(nb["cells"]):
        if c["cell_type"] == "code":
            compile("".join(c["source"]), f"<cell {i}>", "exec")
    print(f"wrote {out_nb} ({len(nb['cells'])} cells, all code cells compile)")
    print(f"wrote {out_dir / 'kernel-metadata.json'}")
    print(f"  arms={arms} tasks={n_tasks} cap={cfg['max_time_minutes']}min "
          f"calls={cfg['max_tool_calls']} expect_rows={tokens['expect_rows']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", choices=sorted(CONFIGS), default="paired100",
                    help="which run shape to generate (default: paired100)")
    ap.add_argument("--all", action="store_true", help="regenerate every config")
    args = ap.parse_args()
    names = sorted(CONFIGS) if args.all else [args.config]
    for name in names:
        print(f"--- {name} ---")
        rc = build(CONFIGS[name])
        if rc:
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
