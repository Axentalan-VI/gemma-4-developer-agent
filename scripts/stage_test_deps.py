"""Install the benchmark repos' test dependencies into the notebook environment.

Why this exists: `container_setup.install_test_dependencies` returns immediately
when the sandbox is `SubprocessManager`, and subprocess is the only backend
available on Kaggle (no Docker daemon). So on Kaggle the per-task sandbox never
gets the repos' test dependencies, pytest dies at collection, and gold patches
appear not to resolve. The first calibration run measured 57% on gold because of
this, not because the tasks are broken.

`SubprocessManager` sets `system_site_packages=True`, so anything installed in
the notebook interpreter is visible inside every per-task venv. That is the
lever this script pulls.

It reuses the competition's own `sandbox/setup.py` for dependency *resolution*
(so we match what the grader installs) but deliberately does not call its
`main()`, because that also pip-installs the staged snapshot in editable mode --
which would shadow each task's own `/workspace` package and silently make the
agent edit files nothing imports.

    python scripts/stage_test_deps.py --data /kaggle/input/competitions/gemma-4-developer-agent
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tarfile
import time
from pathlib import Path

#: setup.py hardcodes WHEELS_DIR = Path("/wheels"), so we make that path real
#: rather than patching their module.
WHEELS_LINK = Path("/wheels")

#: Test-only packages the repos import but do not declare in pyproject, so
#: collect_from_pyproject / collect_from_requirements_files never see them.
#: Measured, not guessed: calibration run 3 attributed 34 of 55 gold failures to
#: exactly two of these -- inline_snapshot (27 tasks) and dirty_equals (7), both
#: imported by fastapi test modules whose collection error then aborts the whole
#: pytest invocation.
#:
#: Naming specific libraries is legitimate HERE and nowhere else: this is
#: environment provisioning, it never reaches the submission, and the validator
#: still bans repo names in anything we ship as a prompt.
SUPPLEMENTARY = [
    "inline_snapshot",
    "dirty_equals",
    "trio",
    "pytest-asyncio",
    "pytest-httpbin",
    "coverage",
    "flask",
]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def find_setup_py(data: Path, lab: Path | None) -> Path | None:
    for cand in (
        data / "sandbox" / "setup.py",
        data / "setup.py",
        Path("/kaggle/input/datasets/metric/gemma-4-developer-agent-metric-data/sandbox/setup.py"),
    ):
        if cand.is_file():
            return cand
    if lab:
        c = lab / "comp_sandbox" / "setup.py"
        if c.is_file():
            return c
    return None


def link_wheels(data: Path) -> Path | None:
    """Make /wheels resolve to the competition wheel cache."""
    src = data / "wheels"
    if not src.is_dir():
        log(f"no wheels dir at {src}")
        return None
    n = len(list(src.glob("*.whl")))
    if WHEELS_LINK.is_dir() or WHEELS_LINK.is_symlink():
        log(f"{WHEELS_LINK} already present")
        return WHEELS_LINK
    try:
        WHEELS_LINK.symlink_to(src, target_is_directory=True)
        log(f"symlinked {WHEELS_LINK} -> {src} ({n} wheels)")
        return WHEELS_LINK
    except OSError as exc:
        log(f"could not create {WHEELS_LINK}: {exc}")
        return None


def load_setup_module(path: Path):
    spec = importlib.util.spec_from_file_location("comp_sandbox_setup", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def extract_snapshot(snapshots: Path, instance_id: str, dest: Path) -> Path | None:
    """Unpack one task snapshot, purely to read its dependency declarations."""
    for name in (f"{instance_id}.tgz", f"{instance_id}.tar.gz", f"{instance_id}.tar"):
        p = snapshots / name
        if not p.is_file():
            continue
        dest.mkdir(parents=True, exist_ok=True)
        try:
            with tarfile.open(p) as tf:
                tf.extractall(dest, filter="data")
        except TypeError:  # Python < 3.12 has no filter kwarg
            with tarfile.open(p) as tf:
                tf.extractall(dest)
        # Snapshots may unpack with a single top-level directory.
        kids = [k for k in dest.iterdir() if k.is_dir() and not k.name.startswith(".")]
        if len(kids) == 1 and not (dest / "pyproject.toml").exists():
            return kids[0]
        return dest
    return None


def installed_version(name: str) -> str | None:
    """Current version of an installed distribution, or None."""
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="/kaggle/input/competitions/gemma-4-developer-agent")
    ap.add_argument("--lab", default="/kaggle/input/datasets/ahmedsherif382/swegemma-lab")
    ap.add_argument("--stage", default="/tmp/dep_stage")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    data = Path(args.data)
    lab = Path(args.lab) if args.lab else None
    stage = Path(args.stage)

    setup_py = find_setup_py(data, lab)
    if setup_py is None:
        log("FATAL could not find the competition sandbox/setup.py")
        return 2
    log(f"using {setup_py}")

    if link_wheels(data) is None:
        log("FATAL /wheels unavailable; setup.py resolves wheels from there")
        return 2

    setup = load_setup_module(setup_py)
    available = setup.get_available_packages()
    log(f"{len(available)} packages available as prebuilt wheels")

    # One task per repo is enough: dependency declarations are per-repo, and the
    # union across repos is what the notebook environment needs.
    tasks = [json.loads(l) for l in (data / "tasks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    first_per_repo: dict[str, str] = {}
    for t in tasks:
        first_per_repo.setdefault(t["repo"], t["instance_id"])
    log(f"repos: {', '.join(f'{r} ({i})' for r, i in first_per_repo.items())}")

    # Collect declared dependency NAMES, not just the subset that happens to
    # exist in /wheels. Run 2 showed the public wheel cache holds only 41
    # packages: fastapi declares 32 and 6 resolve, rich declares 4 and 0
    # resolve. The full prebaked cache lives in the private metric-data dataset
    # the grader mounts, so it is not available to us. Kaggle notebooks do have
    # internet, so we let pip fetch the rest from PyPI.
    wanted: set[str] = set()
    for repo, iid in first_per_repo.items():
        ws = extract_snapshot(data / "snapshots", iid, stage / repo.replace("/", "__"))
        if ws is None:
            log(f"  {repo}: no snapshot for {iid}, skipping")
            continue
        deps: list[str] = []
        pp = ws / "pyproject.toml"
        if pp.is_file():
            deps.extend(setup.collect_from_pyproject(pp))
        deps.extend(setup.collect_from_requirements_files(ws))
        names = {d for d in deps if d and not d.startswith("-")}
        have = {d for d in names if setup.normalize_pkg_name(d) in available}
        log(f"  {repo}: {len(names)} declared, {len(have)} in /wheels, rest from PyPI")
        wanted |= names

    # Never install the repo under test: the sandbox does its own editable
    # install of /workspace, and a copy here would shadow it, so the agent would
    # edit files nothing imports.
    repo_pkgs = {"fastapi", "requests", "rich", "httpx", "starlette"}
    wanted = {d for d in wanted if setup.normalize_pkg_name(d) not in repo_pkgs}

    if not wanted:
        log("FATAL resolved no dependencies; nothing would change")
        return 3

    # Run 2 broke the harness by installing pydantic with --no-deps, leaving
    # pydantic-core at an incompatible version: every swegemma import then died
    # with a SystemError. The declared set is NOT a closed dependency set, so
    # pip must resolve transitively -- and the packages the harness itself
    # depends on must be pinned to what is already working.
    protect = ["pydantic", "pydantic-core", "litellm", "google-adk", "pyyaml", "typing-extensions"]
    pins: list[str] = []
    for name in protect:
        v = installed_version(name)
        if v:
            pins.append(f"{name}=={v}")
    constraints = Path("/tmp/protect_constraints.txt")
    constraints.write_text(chr(10).join(pins) + chr(10), encoding="utf-8")
    log(f"pinning {len(pins)} harness package(s): {', '.join(pins)}")

    names = sorted(wanted | set(SUPPLEMENTARY))
    log(f"installing {len(names)} dependency name(s) into {sys.executable}")
    log(f"  including {len(SUPPLEMENTARY)} supplementary test-only package(s)")
    if args.dry_run:
        for n in names:
            print("   ", n)
        return 0

    cmd = [sys.executable, "-m", "pip", "install", "-q",
           f"--constraint={constraints}", f"--find-links={WHEELS_LINK}", *names]
    r = subprocess.run(cmd, capture_output=True, text=True)
    log(f"pip rc {r.returncode}")
    if r.returncode != 0:
        print((r.stderr or "")[-4000:])
        # Keep going: a partial install is still an improvement, and the
        # harness check below is the real gate.

    # The harness must still work. This is the check whose absence let run 2
    # proceed to a preflight failure instead of stopping here.
    log("harness integrity check:")
    probe = (
        "import pydantic, pydantic_core;"
        "from swegemma.config import EvalConfig;"
        "from swegemma.evaluate import Evaluator;"
        "print('harness ok', pydantic.VERSION, pydantic_core.__version__)"
    )
    h = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    print("   ", (h.stdout or h.stderr or "").strip()[:400])
    if h.returncode != 0:
        log("FATAL dependency staging broke the harness; refusing to continue")
        return 5

    log("repo test-dep import check:")
    missing = []
    for mod in ("pytest", "anyio", "httpx", "pydantic", "starlette",
                "dirty_equals", "inline_snapshot", "trio", "pytest_asyncio"):
        p2 = subprocess.run([sys.executable, "-c", f"import {mod}"], capture_output=True)
        if p2.returncode != 0:
            missing.append(mod)
        print(f"    {'ok' if p2.returncode == 0 else 'MISSING':8s} {mod}")
    log(f"staging complete; {len(missing)} still missing" if missing else "staging complete, all present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
