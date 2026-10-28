"""Append-only run ledger, and the resume logic built on it.

Two constraints shape this. Kaggle sessions die at a 9-12 hour cap, and 30
GPU-hours a week means a lost run is a lost week. So every finished task is
fsync'd to disk the moment it completes, and resuming is a set difference rather
than an index into a shard.

Sharding is deliberately not used for resumption: `--shard-index k --num-shards M`
partitions by `task_idx % M`, which is fine for splitting work across sessions
but silently wrong the moment one shard dies mid-task. A set difference over
completed instance_ids cannot get that wrong.

The ledger is also what makes the statistics affordable. Runs are never
discarded; comparisons pool every run of a configuration by `bundle_hash`, so a
k=2 candidate measured against an existing k=4 reference costs one run rather
than five.
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

LEDGER_NAME = "task_results.jsonl"
RUNSPEC_NAME = "runspec.json"


@dataclass
class Row:
    """One task, one run. Flat on purpose so the file stays greppable."""

    run_id: str
    variant: str
    bundle_hash: str
    seed: int
    concurrency: int
    instance_id: str
    resolved: bool
    error: str = ""
    tool_calls_used: int = 0
    turns: int = 0
    wall_seconds: float = 0.0
    patch_sha: str = ""
    patch_bytes: int = 0
    #: Gold-file localization, computed at write time by metrics.gold_overlap.
    #: Stored rather than recomputed because the patches live in the results
    #: directory, which does not always survive the trip back from Kaggle,
    #: whereas the ledger always does. Without these the co-primary metric
    #: would be unavailable for every past run.
    gold_hit: bool = False
    gold_exact: bool = False
    files_touched: int = 0
    #: True when the weights behind the declared model name were NOT the
    #: competition model -- a pipeline test on hardware that cannot host a 31B.
    #: Load-bearing: a surrogate run uses a byte-identical bundle and therefore
    #: the SAME bundle_hash as a real run, so without this flag it would pool
    #: straight into the reference arm and quietly corrupt it. `pool_by_bundle`
    #: drops these rows unless asked for them explicitly.
    surrogate: bool = False
    #: What actually answered the requests, when surrogate is True.
    model_served: str = ""
    #: The budgets this row was produced under. A probe at max_tool_calls=30 is
    #: not comparable to a scored run at 100, and a reduced max_model_len
    #: changes when compaction fires -- but both carry the same bundle_hash, so
    #: nothing else would stop them pooling into the reference arm. 0 means
    #: "not recorded" (rows written before these fields existed).
    max_tool_calls: int = 0
    max_model_len: int = 0
    task_list: str = ""
    finished_at: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


class Ledger:
    """Append-only JSONL, one directory per run.

    Opened in line-buffered append mode and fsync'd per row. That costs a
    millisecond and buys the guarantee that a SIGKILL at the session cap loses
    at most the task currently in flight.
    """

    def __init__(self, root: str | Path, run_id: str):
        self.root = Path(root)
        self.run_id = run_id
        self.dir = self.root / "runs" / run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / LEDGER_NAME

    def append(self, row: Row) -> None:
        with self.path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(row.to_json() + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def write_runspec(self, spec: dict) -> None:
        (self.dir / RUNSPEC_NAME).write_text(
            json.dumps(spec, indent=2, sort_keys=True), encoding="utf-8", newline="\n"
        )

    def completed(self) -> set[str]:
        """instance_ids already finished in THIS run, for resumption."""
        return {r.instance_id for r in read_rows(self.path)}

    def remaining(self, task_ids: Iterable[str]) -> list[str]:
        done = self.completed()
        return [t for t in task_ids if t not in done]


def read_rows(path: str | Path) -> list[Row]:
    """Parse a ledger file, skipping any torn final line.

    A session killed mid-write leaves a partial line. Dropping it is correct;
    refusing to parse the file would throw away a whole run's work.
    """
    path = Path(path)
    out: list[Row] = []
    if not path.is_file():
        return out
    known = set(Row.__dataclass_fields__)
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict) or "instance_id" not in raw:
            continue
        out.append(Row(**{k: v for k, v in raw.items() if k in known}))
    return out


def read_all(root: str | Path) -> list[Row]:
    """Every row across every run under *root*."""
    root = Path(root)
    runs = root / "runs"
    if not runs.is_dir():
        return []
    rows: list[Row] = []
    for d in sorted(runs.iterdir()):
        if d.is_dir():
            rows.extend(read_rows(d / LEDGER_NAME))
    return rows


#: Boolean Row fields that can be pooled into an `ArmStats`. `resolved` is the
#: competition metric; `gold_hit` and `gold_exact` are the lower-variance
#: localization surrogates, which sit near p=0.45 rather than p=0.15 and so
#: detect a change 2 to 3 times smaller for the same GPU spend.
POOLABLE = ("resolved", "gold_hit", "gold_exact")

#: The grader's budgets. A row produced under anything else is a probe.
GRADER_MAX_TOOL_CALLS = 100
GRADER_MAX_MODEL_LEN = 32768


def is_comparable(row: Row) -> bool:
    """Can this row sit in an arm that gets compared to another arm?

    Three ways a row can carry a real `bundle_hash` and still be incomparable:
    different weights (surrogate), a reduced tool-call budget, or a reduced
    context window -- which moves when compaction fires and so changes the
    agent's behaviour, not just its ceiling.

    Rows predating these fields have 0 and are accepted, because the runs that
    produced them were full-budget. New runs always record them.
    """
    if row.surrogate:
        return False
    if row.max_tool_calls and row.max_tool_calls != GRADER_MAX_TOOL_CALLS:
        return False
    if row.max_model_len and row.max_model_len != GRADER_MAX_MODEL_LEN:
        return False
    return True


def pool_by_bundle(
    rows: Iterable[Row], metric: str = "resolved", include_surrogate: bool = False
) -> dict[str, dict[str, tuple[int, int]]]:
    """bundle_hash -> {instance_id: (hit_count, run_count)} for one metric.

    Feeds `stats.ArmStats` directly. Pooling by hash rather than by variant name
    is what keeps an accidental prompt edit from being averaged together with
    the runs it was supposed to be compared against.

    *metric* selects which boolean outcome is pooled, so the same paired
    estimator serves both the headline rate and the localization surrogates.

    Incomparable rows are dropped by default -- see `is_comparable`. They carry
    a real bundle_hash, because the bundle was byte-identical and only the
    weights or the budgets differed, so nothing else would stop them pooling
    into the arm they appear to belong to. Opt in with *include_surrogate* only
    to inspect a probe on its own.
    """
    if metric not in POOLABLE:
        raise ValueError(f"metric must be one of {POOLABLE}, got {metric!r}")
    acc: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for r in rows:
        if not include_surrogate and not is_comparable(r):
            continue
        cell = acc[r.bundle_hash][r.instance_id]
        cell[0] += int(bool(getattr(r, metric)))
        cell[1] += 1
    return {h: {i: (c[0], c[1]) for i, c in tasks.items()} for h, tasks in acc.items()}


def runs_per_bundle(rows: Iterable[Row]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        out[r.bundle_hash].add(r.run_id)
    return dict(out)


def iter_with_deadline(
    task_ids: list[str],
    deadline_minutes: float,
    stop_launching_before_end: float = 45.0,
) -> Iterator[str]:
    """Yield task ids until the session deadline is close enough to stop.

    Kaggle kills the session at its cap with no warning, so we stop *launching*
    while there is still time for in-flight tasks to land in the ledger. A run
    that loses its last hour of work to a hard kill has wasted a whole session.
    """
    start = time.monotonic()
    budget = max(0.0, deadline_minutes - stop_launching_before_end) * 60
    for t in task_ids:
        if time.monotonic() - start >= budget:
            return
        yield t


def load_task_ids(path: str | Path) -> list[str]:
    return [ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]
