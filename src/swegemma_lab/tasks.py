"""Load the public task set and mine the gold patches for offline metrics.

The 129 public tasks ship their gold `patch`. That is the project's most
valuable offline asset, and it has exactly one sanctioned use: scoring how well
an agent *localized* a fix, which is a far less noisy readout than binary
resolution (p around 0.45 rather than 0.15).

It has one forbidden use. Gold patches must never inform prompt text. A human
who reads sixty gold patches and distils them into instructions has overfitted
to a dev set that is 90% fastapi+rich, against a private set believed to hold
different repos. That is the mistake that measured 0.05.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

#: Files the harness force-resets to baseline before applying the hidden tests.
#: An agent touching any of them is spending budget on something discarded.
PROTECTED_BASENAMES = frozenset(
    {
        "conftest.py",
        "pytest.ini",
        ".pytest.ini",
        "pyproject.toml",
        "tox.ini",
        "setup.cfg",
        "sitecustomize.py",
        "usercustomize.py",
        "_swegemma_stubs.py",
    }
)
PROTECTED_DIRS = ("tests/", "test/", "testing/")

#: Scratch files an agent leaves in /workspace get swept into the patch by
#: `git add -N . && git diff`.
#:
#: Matched on the whole stem, not as a prefix. A prefix match flagged
#: `fastapi/temp_pydantic_v1_params.py`, a real source file in three gold
#: patches -- so `temp_*` is a legitimate module naming style and only a bare
#: `temp.py` looks like scratch. Words that plausibly name real modules
#: (`check`, `example`, `issue`, `bug`) are left out entirely.
SCRATCH_STEMS = (
    "repro",
    "repro_test",
    "reproduce",
    "reproducer",
    "reproduction",
    "minimal_repro",
    "test_repro",
    "scratch",
    "debug",
    "tmp",
    "temp",
    "poc",
)
SCRATCH_RE = re.compile(r"^(?:" + "|".join(SCRATCH_STEMS) + r")[_-]?\d*$", re.IGNORECASE)

#: Both `diff --git a/x b/x` and bare `--- a/x` headers appear in this dataset;
#: counting only `diff --git` undercounts badly.
_DIFF_GIT_RE = re.compile(r"^diff --git a/(.+?) b/(.+?)$", re.MULTILINE)
_MINUS_RE = re.compile(r"^--- (?:a/)?(.+?)(?:\t.*)?$", re.MULTILINE)
_PLUS_RE = re.compile(r"^\+\+\+ (?:b/)?(.+?)(?:\t.*)?$", re.MULTILINE)
_HUNK_RE = re.compile(r"^@@ ", re.MULTILINE)
#: `@@ -start,count +start,count @@` -- the count is omitted when it is 1.
_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class Task:
    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    patch: str = ""
    test_patch: str = ""
    hints_text: str = ""
    created_at: str = ""

    @property
    def gold_files(self) -> frozenset[str]:
        return patch_files(self.patch)

    @property
    def test_files(self) -> frozenset[str]:
        return patch_files(self.test_patch)


def load_tasks(path: str | Path) -> list[Task]:
    out: list[Task] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        out.append(
            Task(
                instance_id=raw["instance_id"],
                repo=raw["repo"],
                base_commit=raw["base_commit"],
                problem_statement=raw.get("problem_statement") or "",
                patch=raw.get("patch") or "",
                test_patch=raw.get("test_patch") or "",
                hints_text=raw.get("hints_text") or "",
                created_at=raw.get("created_at") or "",
            )
        )
    return out


def patch_files(diff: str) -> frozenset[str]:
    """Every path a unified diff touches, tolerating both header styles."""
    if not diff:
        return frozenset()
    files: set[str] = set()
    for m in _DIFF_GIT_RE.finditer(diff):
        files.add(m.group(2))
    if not files:
        for regex in (_PLUS_RE, _MINUS_RE):
            for m in regex.finditer(diff):
                p = m.group(1).strip()
                if p and p != "/dev/null":
                    files.add(p)
    return frozenset(files)


def count_hunks(diff: str) -> int:
    return len(_HUNK_RE.findall(diff or ""))


def hunk_ranges(diff: str) -> dict[str, list[tuple[int, int]]]:
    """Per-file line ranges a unified diff touches, in the **pre-image**.

    `{path: [(first_line, last_line), ...]}`, inclusive, 1-based, read off the
    `-start,count` side of each `@@` header so two diffs of the same file can be
    compared without either file's text. Paths are spelled exactly as
    `patch_files` spells them, so the two can be intersected.

    Two deliberate choices:

    * The ranges **include the diff's context lines**, because that is what the
      header counts. So an overlap test on these ranges already tolerates a few
      lines of drift between two diffs of the same edit, and needs no extra
      slack to call "the same place" the same place.
    * A pure insertion (`-N,0`) has no pre-image lines at all. It is recorded as
      the degenerate range `(N, N)` -- the anchor it was inserted after --
      rather than dropped, since an inserted guard clause is the single
      commonest shape in this dataset's gold patches.
    """
    out: dict[str, list[tuple[int, int]]] = {}
    current: str | None = None
    pending_minus: str | None = None
    for line in (diff or "").splitlines():
        if line.startswith("diff --git "):
            m = _DIFF_GIT_RE.match(line)
            if m:
                current = m.group(2)
                out.setdefault(current, [])
            continue
        if line.startswith("--- "):
            p = line[4:].split("\t")[0].strip()
            pending_minus = None if p == "/dev/null" else _strip_ab(p)
            continue
        if line.startswith("+++ "):
            p = line[4:].split("\t")[0].strip()
            # A deletion has `+++ /dev/null`; fall back to the `---` side so the
            # file is still attributed.
            target = pending_minus if p == "/dev/null" else _strip_ab(p)
            if target:
                current = target
                out.setdefault(current, [])
            continue
        m = _HUNK_HEADER_RE.match(line)
        if m and current is not None:
            start = int(m.group(1))
            count = 1 if m.group(2) is None else int(m.group(2))
            end = start if count == 0 else start + count - 1
            out[current].append((start, end))
    return out


def edit_bodies(diff: str) -> dict[str, tuple[tuple[str, str], ...]]:
    """Per-file content changes, stripped of everything positional.

    `{path: (('+', 'stripped text'), ('-', 'stripped text'), ...)}` -- only the
    added and removed lines, in order, with leading and trailing whitespace
    removed and line numbers, hunk headers, `index` lines and context lines
    discarded. Two diffs with equal `edit_bodies` make the same change, even if
    one was generated at a different line offset or with different context.

    This exists to answer one question exactly: did the agent write *the gold
    fix*? `hunk_ranges` only shows it edited the same neighbourhood.
    """
    out: dict[str, list[tuple[str, str]]] = {}
    current: str | None = None
    for line in (diff or "").splitlines():
        if line.startswith("diff --git "):
            m = _DIFF_GIT_RE.match(line)
            if m:
                current = m.group(2)
            continue
        if line.startswith("+++ "):
            p = line[4:].split("\t")[0].strip()
            current = None if p == "/dev/null" else _strip_ab(p)
            continue
        if line.startswith(("--- ", "@@", "index ", "new file mode",
                            "deleted file mode", "similarity index",
                            "rename from", "rename to", "Binary files")):
            continue
        if current and line[:1] in "+-":
            out.setdefault(current, []).append((line[0], line[1:].strip()))
    return {k: tuple(v) for k, v in out.items()}


def _strip_ab(path: str) -> str:
    return path[2:] if path.startswith(("a/", "b/")) else path


def ranges_overlap(
    a: Iterable[tuple[int, int]], b: Iterable[tuple[int, int]], slack: int = 0
) -> bool:
    """True if any range in `a` touches any range in `b`, widened by `slack`."""
    bs = list(b)
    return any(
        a0 - slack <= b1 and b0 <= a1 + slack for a0, a1 in a for b0, b1 in bs
    )


def churn(diff: str) -> tuple[int, int]:
    """(added, removed) content lines, ignoring headers."""
    added = removed = 0
    for line in (diff or "").splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return added, removed


def is_protected(path: str) -> bool:
    """True if the harness resets this path before grading, making edits futile."""
    p = path.replace("\\", "/")
    base = p.rsplit("/", 1)[-1]
    if base in PROTECTED_BASENAMES or base.endswith(".pth"):
        return True
    if base.startswith("test_") and base.endswith(".py"):
        return True
    if base.endswith("_test.py"):
        return True
    return any(seg in f"/{p}" for seg in (f"/{d}" for d in PROTECTED_DIRS))


def is_scratch(path: str) -> bool:
    """True if the path looks like an agent's throwaway reproduction script.

    A refinement on top of the exact signal, which is simply that the patch
    creates a file at all -- no gold patch does. This only helps name the cause.
    """
    p = path.replace("\\", "/")
    base = p.rsplit("/", 1)[-1]
    if not base.endswith(".py"):
        return False
    return bool(SCRATCH_RE.match(base[: -len(".py")]))


# --- Repo splits --------------------------------------------------------------

#: Tune here. fastapi dominates the public set, so it is where iteration is cheap.
DEV_REPOS = ("fastapi/fastapi", "encode/httpx")
#: Confirm here. Terminal rendering is maximally unlike DI/ASGI/pydantic, so a
#: change that helps fastapi and not rich is fastapi-specific, not a real win.
CONFIRM_REPOS = ("Textualize/rich",)
#: Audit here, sparingly and late. Closest proxy for a small stdlib-adjacent
#: library, which is the likeliest shape of an unseen private repo.
AUDIT_REPOS = ("psf/requests",)


def split_of(repo: str) -> str:
    if repo in DEV_REPOS:
        return "dev"
    if repo in CONFIRM_REPOS:
        return "confirm"
    if repo in AUDIT_REPOS:
        return "audit"
    return "other"


@dataclass
class TaskSetSummary:
    n: int
    by_repo: Counter = field(default_factory=Counter)
    by_split: Counter = field(default_factory=Counter)
    single_file: int = 0
    single_hunk: int = 0
    creates_file: int = 0
    touches_protected: int = 0
    small_churn: int = 0  # <= 20 changed lines
    empty_gold: int = 0
    p50_churn: int = 0
    p90_churn: int = 0

    def render(self) -> str:
        pct = lambda k: f"{k / self.n:.0%}" if self.n else "n/a"  # noqa: E731
        lines = [
            f"{self.n} tasks",
            "  by repo:  " + ", ".join(f"{r} {c}" for r, c in self.by_repo.most_common()),
            "  by split: " + ", ".join(f"{s} {c}" for s, c in self.by_split.most_common()),
            f"  gold touches exactly 1 file: {self.single_file} ({pct(self.single_file)})",
            f"  gold is a single hunk:       {self.single_hunk} ({pct(self.single_hunk)})",
            f"  gold creates a new file:     {self.creates_file} ({pct(self.creates_file)})",
            f"  gold churn <= 20 lines:      {self.small_churn} ({pct(self.small_churn)})",
            f"  gold churn p50/p90:          {self.p50_churn} / {self.p90_churn} lines",
            f"  gold touches a protected path: {self.touches_protected}",
            f"  empty gold patch (broken):     {self.empty_gold}",
        ]
        return "\n".join(lines)


def summarize(tasks: Iterable[Task]) -> TaskSetSummary:
    tasks = list(tasks)
    s = TaskSetSummary(n=len(tasks))
    churns: list[int] = []
    for t in tasks:
        s.by_repo[t.repo] += 1
        s.by_split[split_of(t.repo)] += 1
        files = t.gold_files
        if not t.patch.strip():
            s.empty_gold += 1
            continue
        if len(files) == 1:
            s.single_file += 1
        if count_hunks(t.patch) == 1:
            s.single_hunk += 1
        if "\n--- /dev/null" in t.patch or "new file mode" in t.patch:
            s.creates_file += 1
        if any(is_protected(f) for f in files):
            s.touches_protected += 1
        added, removed = churn(t.patch)
        total = added + removed
        churns.append(total)
        if total <= 20:
            s.small_churn += 1
    if churns:
        churns.sort()
        s.p50_churn = churns[len(churns) // 2]
        s.p90_churn = churns[min(len(churns) - 1, int(len(churns) * 0.9))]
    return s


def iter_stratified(tasks: list[Task], strata: dict[str, str]) -> Iterator[tuple[str, Task]]:
    """Yield (stratum, task) for tasks present in a strata map."""
    for t in tasks:
        if t.instance_id in strata:
            yield strata[t.instance_id], t
