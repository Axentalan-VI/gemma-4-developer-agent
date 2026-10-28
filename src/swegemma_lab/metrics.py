"""The diagnostic panel: what a run tells us beyond resolved/not-resolved.

Binary resolution is the noisiest readout available. At p around 0.15 it takes
24 to 48 GPU-hours to resolve a +0.03 change, which on a 30 h/week quota is one
decision a week. Every metric here is computed from artifacts a run already
produces, costs no extra GPU, and is less noisy than the headline number.

The most useful is gold-file hit rate. We hold all 129 gold patches, localization
sits near p=0.45 rather than 0.15, and it is far more deterministic than whether
a fix happens to be exactly right -- so it detects changes 2 to 3 times smaller.

Two of these are exact rather than heuristic, because of what the gold patches
measure (scripts/analyze_tasks.py): no gold patch creates a new file, and none
touches a protected path. So any created file, and any protected-path edit, is
unambiguously wasted work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from .tasks import Task, is_protected, is_scratch, patch_files


@dataclass
class TaskOutcome:
    """One task in one run, as reconstructed from the ledger and patches/."""

    instance_id: str
    resolved: bool
    patch: str = ""
    error: str = ""
    tool_calls_used: int = 0
    wall_seconds: float = 0.0
    turns: int = 0

    @property
    def files(self) -> frozenset[str]:
        return patch_files(self.patch)

    @property
    def empty(self) -> bool:
        return not self.patch.strip()


@dataclass
class Panel:
    """Aggregate diagnostics for one run, or one arm pooled over runs."""

    name: str
    n: int = 0
    resolved: int = 0
    non_empty: int = 0
    gold_file_hit: int = 0
    gold_file_exact: int = 0
    created_file: int = 0
    touched_protected: int = 0
    scratch_leak: int = 0
    errored: int = 0
    exhausted_calls: int = 0
    tool_calls: list[int] = field(default_factory=list)
    wall_seconds: list[float] = field(default_factory=list)
    errors: dict[str, int] = field(default_factory=dict)
    #: False when this panel was built without patch text, which makes
    #: created_file / touched_protected / scratch_leak structurally
    #: uncomputable. They then render as "n/a" rather than as a clean 0.0%.
    #: P005 printed "leaked scratch file 0.0%" while 6 of 7 of that run's
    #: patches were contaminated, on the metric that dominated its failures.
    hygiene_known: bool = True

    def _rate(self, k: int) -> float:
        return k / self.n if self.n else 0.0

    @property
    def resolution_rate(self) -> float:
        return self._rate(self.resolved)

    @property
    def localization_rate(self) -> float:
        """Share of tasks whose patch touches at least one file the gold patch touches."""
        return self._rate(self.gold_file_hit)

    @property
    def waste_rate(self) -> float | None:
        """Share of tasks with a created file, protected-path edit or scratch leak.

        Exact, not heuristic: no gold patch does any of these. **None** when the
        panel had no patch text, so a caller cannot mistake "not measured" for
        "no waste".
        """
        if not self.hygiene_known:
            return None
        return self._rate(self.created_file + self.touched_protected + self.scratch_leak)

    def median_tool_calls(self) -> float:
        if not self.tool_calls:
            return 0.0
        s = sorted(self.tool_calls)
        return float(s[len(s) // 2])

    def render(self) -> str:
        pct = lambda k: f"{self._rate(k):6.1%}"  # noqa: E731
        med_wall = 0.0
        if self.wall_seconds:
            w = sorted(self.wall_seconds)
            med_wall = w[len(w) // 2]
        lines = [
            # "task-runs", not "tasks": a panel pooled over k runs counts each
            # task k times. The rates are still per-task rates, but calling the
            # denominator "tasks" would invite reading 408 as a task count.
            f"{self.name}: {self.n} task-runs",
            f"  resolution rate      {pct(self.resolved)}   ({self.resolved}/{self.n})",
            f"  gold-file hit        {pct(self.gold_file_hit)}   <- lower variance, use this to triage",
            f"  gold-file exact set  {pct(self.gold_file_exact)}",
            f"  produced a patch     {pct(self.non_empty)}",
            f"  harness error        {pct(self.errored)}",
            "  -- waste (no gold patch ever does these) --",
        ]
        if self.hygiene_known:
            lines += [
                f"  created a new file   {pct(self.created_file)}",
                f"  edited a test/config {pct(self.touched_protected)}",
                f"  leaked scratch file  {pct(self.scratch_leak)}",
            ]
        else:
            lines += [
                "  created a new file      n/a  (needs patches)",
                "  edited a test/config    n/a  (needs patches)",
                "  leaked scratch file     n/a  (needs patches)",
            ]
        lines += [
            "  -- budget use --",
            f"  tool calls median    {self.median_tool_calls():.0f} of 100",
            f"  hit the call ceiling {pct(self.exhausted_calls)}",
            f"  wall median          {med_wall / 60:.1f} min of 60",
        ]
        if self.errors:
            lines.append("  -- error taxonomy --")
            for kind, count in sorted(self.errors.items(), key=lambda kv: -kv[1])[:6]:
                lines.append(f"    {count:4d}  {kind}")
        return "\n".join(lines)


def gold_overlap(outcome: TaskOutcome, task: Task | None) -> tuple[bool, bool]:
    """(touched a gold file, touched exactly the gold set) for one outcome.

    Extracted so `build_panel` and the ledger writer cannot disagree: the stored
    flag and the rendered panel are the same computation. An empty patch counts
    as neither, and an unknown task counts as neither -- absence of a gold
    reference is not a miss.
    """
    if task is None:
        return (False, False)
    files = outcome.files
    if not files:
        return (False, False)
    gold = task.gold_files
    return (bool(files & gold), files == gold)


def build_panel(
    name: str,
    outcomes: Sequence[TaskOutcome],
    tasks: Mapping[str, Task],
    call_ceiling: int = 100,
) -> Panel:
    p = Panel(name=name)
    for o in outcomes:
        task = tasks.get(o.instance_id)
        p.n += 1
        if o.resolved:
            p.resolved += 1
        if not o.empty:
            p.non_empty += 1
        if o.error:
            p.errored += 1
            p.errors[classify_error(o.error)] = p.errors.get(classify_error(o.error), 0) + 1
        if o.tool_calls_used:
            p.tool_calls.append(o.tool_calls_used)
            if o.tool_calls_used >= call_ceiling:
                p.exhausted_calls += 1
        if o.wall_seconds:
            p.wall_seconds.append(o.wall_seconds)

        files = o.files
        hit, exact = gold_overlap(o, task)
        if hit:
            p.gold_file_hit += 1
        if exact:
            p.gold_file_exact += 1

        for f in files:
            if is_protected(f):
                p.touched_protected += 1
                break
        for f in files:
            if is_scratch(f):
                p.scratch_leak += 1
                break
        if _creates_file(o.patch):
            p.created_file += 1
    return p


def _creates_file(diff: str) -> bool:
    return "new file mode" in diff or "\n--- /dev/null" in diff


#: Coarse buckets, ordered most specific first. Refine from real traces rather
#: than from guesses about what the failures will look like.
_ERROR_RULES = (
    ("patch_apply_failed", ("failed to apply agent patch", "git apply", "patch does not apply")),
    ("empty_patch", ("empty patch", "no changes", "patch_size 0")),
    ("agent_timeout", ("timeout", "timed out", "deadline")),
    ("budget_exhausted", ("budget", "tool_calls exhausted", "max_turns")),
    ("model_error", ("ratelimit", "apiconnection", "apitimeout", "502", "503", "504")),
    ("tool_call_malformed", ("tool_call", "malformed", "parse")),
    ("sandbox_error", ("container", "sandbox", "oom", "137", "sigkill")),
    ("test_failure", ("assert", "failed", "exit_code")),
)


def classify_error(message: str) -> str:
    low = (message or "").lower()
    for label, needles in _ERROR_RULES:
        if any(n in low for n in needles):
            return label
    return "other"


def load_outcomes(results_dir: str | Path) -> list[TaskOutcome]:
    """Read a swegemma results directory into outcomes.

    Tolerates partial runs: `task_results.jsonl` is append-only, so a session
    killed at the 9-hour cap still yields every task it finished.
    """
    import json

    results_dir = Path(results_dir)
    jsonl = results_dir / "task_results.jsonl"
    out: list[TaskOutcome] = []
    if not jsonl.is_file():
        return out
    patches = results_dir / "patches"
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # a torn final line from a killed session
        iid = row.get("instance_id") or row.get("id")
        if not iid:
            continue
        patch = row.get("prediction") or row.get("agent_patch") or ""
        if not patch:
            pf = patches / f"{iid}.patch"
            if pf.is_file():
                patch = pf.read_text(encoding="utf-8", errors="replace")
        out.append(
            TaskOutcome(
                instance_id=iid,
                resolved=bool(row.get("resolved")),
                patch=patch,
                error=row.get("error") or "",
                tool_calls_used=int(row.get("tool_calls") or row.get("tool_calls_used") or 0),
                wall_seconds=float(
                    row.get("duration_seconds")
                    or row.get("wall_seconds")
                    or row.get("wall_s")
                    or 0.0
                ),
                turns=int(row.get("turns") or 0),
            )
        )
    return out


#: The grader's per-task tool-call budget. A verdict drawn at any other ceiling
#: does not transfer: an agent cut off at 30 calls looks identical to an agent
#: that chose to stop at 30, and only the second one tells you the budget is
#: slack.
GRADER_CALL_CEILING = 100


def budget_verdict(panel: Panel, call_ceiling: int = GRADER_CALL_CEILING) -> str:
    """Does the tool-call budget actually bind? Answerable from a single k=1 run.

    Worth stating separately because it is the one question where n=1 suffices,
    and answering it early can save tens of GPU-hours of pointless budget
    experiments.

    *call_ceiling* MUST be the ceiling the run actually used. Run probe_c12 was
    rendered against the default 100 while running at 30, which inverted the
    conclusion from "binds" to "slack" -- and would have retired a whole line of
    work on the strength of a reporting bug. The caller passes the real number
    and this refuses to generalize from a probe.
    """
    if not panel.tool_calls:
        return "no tool-call data recorded; fix the ledger before drawing conclusions"
    if call_ceiling != GRADER_CALL_CEILING:
        med = panel.median_tool_calls()
        at_ceiling = sum(1 for c in panel.tool_calls if c >= call_ceiling)
        share = at_ceiling / len(panel.tool_calls)
        return (
            f"NO VERDICT: this run used a {call_ceiling}-call ceiling, not the grader's "
            f"{GRADER_CALL_CEILING}. Median {med:.0f} of {call_ceiling} "
            f"({med / call_ceiling:.0%} of the budget it was given), {share:.0%} at the ceiling. "
            "A truncated agent and a satisfied agent look the same from here, so this says "
            "nothing about whether 100 binds. Re-run at 100 to answer it."
        )
    med = panel.median_tool_calls()
    share = panel.exhausted_calls / panel.n if panel.n else 0.0
    if share > 0.25:
        return (
            f"BUDGET BINDS: {share:.0%} of tasks hit the {call_ceiling}-call ceiling "
            f"(median {med:.0f}). Raising the ceiling, or spending calls more cheaply, is the lever."
        )
    if med < call_ceiling * 0.4:
        return (
            f"BUDGET IS SLACK: median {med:.0f} of {call_ceiling} calls used, only {share:.0%} "
            "exhausted. More budget cannot help; the lever is using what is already there -- "
            "verify-repair cycles, a second localization attempt."
        )
    return f"budget partly used: median {med:.0f} of {call_ceiling}, {share:.0%} exhausted"
