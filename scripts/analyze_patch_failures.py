"""How are the patches that *apply* still wrong? An offline taxonomy.

    export PYTHONUTF8=1   # tasks.jsonl carries emoji; cp1252 crashes on it
    python scripts/analyze_patch_failures.py \
        --arm clamp_v00 --arm clamp_v08 \
        --results <dir containing results/<arm>/patches>

Deterministic, CPU-only, 0 GPU-h. Everything it reads is already on disk: the
129 gold patches in `data/tasks/tasks.jsonl`, the agent patches the run wrote to
`results/<arm>/patches/`, and the ledger rows in `ledger/runs/<arm>/`.

Why this exists. Nine bundles have failed to beat the published baseline, and
the hypothesis that fits all nine nulls is that the W4A16 31B is already at its
quality ceiling. Resolution rate cannot separate that from "the scaffold can
still help", because it collapses six different failure mechanisms into one bit.
This script separates them. It is the only reading in the project that says
*how* a patch is wrong rather than *that* it is wrong.

**Gold patches are an offline metric oracle only.** Nothing this script prints
may be distilled into prompt text: the dev set is 90% fastapi+rich against a
private set believed to hold other repos, and the one competitor who shipped
repo-specific rules scored 0.05. Diff *shapes* are the output; diff *text* is
not. The script prints no gold-patch content for that reason.

What it found on P008, so the next reader starts from the answer
---------------------------------------------------------------
The headline is not about patch quality. **Only 44 of 103 applied patches were
ever graded** -- on the other 59 pytest aborted during collection, so no test
ran and the outcome could not depend on the patch. 75 of 103 logs carry a
starlette/fastapi version mismatch (`Router.__init__() got an unexpected
keyword argument 'on_startup'`) raised from fastapi's own source. It fires on
tasks where the agent produced **no patch at all**, so it is not the agent's
doing. **8 patches reproduced the gold fix line for line and all 8 were scored
unresolved**, every one of them with that mismatch in its log.

After removing the ungraded and the env-flagged runs, 13 of the original 98
failures remain as genuine patch failures, and the modal one (5 of 13) is
`right_hunk_wrong_logic`: right file, right lines, wrong content. The same shape
holds in the unfiltered table (37 of 98). So localization is largely solved and
content is not -- but at n=13 that is a direction, not a measurement.

What "applied" means here, and why it is a proxy
------------------------------------------------
The ledger has **no `applied` column**. The signal used instead is structural:
the harness writes `results/<arm>/test_outputs/<id>.log` only after it has
applied the agent patch and the hidden `test_patch` and actually run pytest. So
a task counts as applied-but-failed when it has (a) a non-empty patch file,
(b) a test-output log, and (c) `resolved == False`. In P008 **every** non-empty
patch had a log and no log mentions a failed apply, so apply failure is not a
measurable failure class in this run -- which is itself a finding, and also the
reason this proxy costs nothing. Pass `--no-require-log` to drop (b).

Readings that would be misleading
---------------------------------
* **The buckets are a partition of a run, not a ranking of causes.** They are
  assigned by the precedence order below, so a patch that is *both* overreaching
  and incomplete is counted once, as `overreach`. Bucket counts therefore answer
  "what is the most actionable thing wrong with this patch", not "how often does
  mechanism X occur". The non-exclusive incidence block exists for that second
  question, and the two must not be quoted as if they were the same table.
* **A scratch leak is NOT fatal here, so pass A alone would mislead.** Giving
  `scratch_pollution` top precedence is what the brief asked for, and on P008 it
  swallows half of every arm -- while **3 of the 5 tasks that RESOLVED also left
  a `repro.py` behind.** The leak is therefore not sufficient to break the
  grade, at least in this subprocess harness, and ranking it first hides the
  reasoning defect underneath it. The report prints a **second pass** with
  scratch paths removed from the comparison; that pass is the one to read when
  asking how the agent's *thinking* is wrong.
* **Region overlap is computed from `@@` headers alone**, never from the file's
  text, so it proves two diffs edit the same *neighbourhood* -- within the
  diffs' own context lines -- not that they edit the same statement. The
  fallback bucket is consequently generous: everything in it reached the right
  neighbourhood and still failed.
* **Many P008 patches are truncated by the 30-minute cap** (`error` set on the
  ledger row). Those patches are whatever happened to be in the workspace when
  the agent was killed, so their bucket describes an interrupted attempt rather
  than a finished wrong answer. The report splits each arm's buckets by whether
  the row errored; read the clean half when asking about patch *quality*.
* **The env-clean resolution rate is biased upward, not corrected.** 5 of 18
  graded env-clean tasks resolved, against the grader's 0.138 -- but a task that
  hits the mismatch can never resolve, and the flag is read from the same log
  that decides the outcome, so conditioning on it selects toward resolvable
  tasks. Use the number to say "the local metric understates", never as an
  estimate of anything.
* **n is small.** A full arm here is 60 task-runs, the resolved sets are 2 and 3,
  and the graded env-clean failure set is 13 pooled. Any bucket under 5 is
  printed with an `(n<5)` marker and must not be reported as a rate.

The buckets, in precedence order
--------------------------------
Each failing patch lands in exactly the first bucket that matches.

1. ``scratch_pollution`` -- the patch carries a throwaway artefact: a path whose
   stem is a reproduction/debug name (`swegemma_lab.tasks.is_scratch`), a
   `.orig`/`.rej`/`.bak`/`.patch`/`.diff` file, anything under a `tmp/` segment
   or an absolute `/tmp` path, or **any file the patch creates at the repository
   root**. That last test is exact rather than heuristic: **0 of the 129 gold
   patches touch a top-level path at all**, in any of the four repos, so a
   created top-level file is unambiguously the agent's own litter. (The weaker
   claim "no gold patch creates a file" is false -- 11 of 129 do, always inside
   a package or `docs_src/` -- so creation alone is not the signal; creation *at
   the root* is.) Highest precedence because it is the one bucket that is a
   *process* defect rather than a reasoning defect -- but see the warning above:
   on P008 it is not fatal.
2. ``test_edit`` -- the patch modifies the test suite, test config, CI or
   packaging (`swegemma_lab.tasks.is_protected`, plus `.github/`, `setup.py`,
   `noxfile.py`, `Makefile`, `requirements*.txt`, `MANIFEST.in`). The prompt
   forbids it and the harness resets these paths before grading, so the edit is
   discarded and any fix that depended on it fails. Automatic failure.
3. ``wrong_file`` -- none of the paths the patch touches is a path the gold
   patch touches. The agent never found the code.
4. ``right_file_wrong_hunk`` -- at least one gold file is touched, but on no
   shared file does any agent hunk range meet any gold hunk range. Right file,
   wrong place in it.
5. ``overreach`` -- the patch meets a gold region *and* touches at least one
   path outside the gold file set. The extra edit is a live risk: the grader
   runs the repo's existing tests as well as the new ones.
6. ``incomplete_fix`` -- the patch meets a gold region, adds no extra paths, but
   misses at least one gold file or at least one gold hunk region. Gold edits
   more than the agent did.
7. ``right_hunk_wrong_logic`` -- **the fallback.** Every gold file is touched,
   every gold hunk region is met, nothing extra is touched, and the task still
   failed. Localization was correct and the *content* of the edit was not. This
   is the bucket that supports the model-ceiling hypothesis, and it is the only
   bucket the scaffold cannot plausibly fix.

Buckets 1-6 are the named classes requested; 7 exists because 1-6 are not
exhaustive -- a patch can hit every gold file and every gold line region and
still fail -- and mislabelling that case as one of the six would hide exactly
the finding the exercise is looking for.

**Pass B** (`scratch discounted`) drops every scratch path from the agent's file
and range sets, then applies buckets 2-7 with one addition:

0. ``no_source_edit`` -- after discounting, the patch edits no source file at
   all. The agent's entire output was a reproduction script.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swegemma_lab.tasks import (  # noqa: E402
    edit_bodies,
    hunk_ranges,
    is_protected,
    is_scratch,
    load_tasks,
    patch_files,
    ranges_overlap,
)

#: pytest prints this when collection failed, and it means **no test ran at
#: all**: the outcome is then independent of the agent's patch.
COLLECTION_ABORT = "Interrupted:"

#: Known environment-mismatch signatures: a traceback the agent cannot cause and
#: cannot fix. Each is paired with a guard token -- if the *task's own* gold or
#: test patch mentions the token, the error is the task's subject matter rather
#: than drift, and the flag is withheld.
#:
#: The one entry here is the installed **starlette being newer than the fastapi
#: snapshot**: `fastapi/routing.py` passes `on_startup=` to `starlette
#: Router.__init__`, which no longer accepts it, so every module that builds a
#: `FastAPI()` explodes. It is raised from fastapi's own source, in a file the
#: agent usually never touches, and it fires even on tasks where the agent
#: produced no patch at all. Extend this list when a new signature appears; it
#: was read off the P008 logs and is not claimed to be complete.
ENV_SIGNATURES = (("unexpected keyword argument 'on_startup'", "on_startup"),)

#: Precedence order for pass A. `classify` returns the first match; the last
#: entry is the fallback and must stay last.
BUCKETS = (
    "scratch_pollution",
    "test_edit",
    "wrong_file",
    "right_file_wrong_hunk",
    "overreach",
    "incomplete_fix",
    "right_hunk_wrong_logic",
)
#: Pass B: scratch paths are removed from the comparison instead of deciding it.
BUCKETS_DISCOUNTED = ("test_edit", "no_source_edit") + BUCKETS[2:]

#: Paths the harness discards or that are off-limits by prompt, beyond the
#: `is_protected` set (which already covers tests/, conftest.py, pytest.ini,
#: pyproject.toml, tox.ini, setup.cfg, test_*.py and *_test.py).
_CI_PACKAGING_BASENAMES = frozenset(
    {"setup.py", "noxfile.py", "Makefile", "MANIFEST.in", "requirements.txt"}
)
_SCRATCH_SUFFIXES = (".orig", ".rej", ".bak", ".patch", ".diff")


def looks_like_scratch(path: str, created: bool) -> bool:
    """Throwaway-artefact test. `created` = the patch adds this file from nothing.

    The last clause is the load-bearing one and it is exact, not heuristic: no
    gold patch in this task set touches a repository-root path, so a file the
    agent creates there is its own litter. `is_scratch` alone misses most of the
    real leakage, because it matches whole stems only (to avoid flagging
    `fastapi/temp_pydantic_v1_params.py`, a genuine module) and the agent's
    second and third attempts are named `repro_v2.py`, `reproduce_issue.py`,
    `verify_fix.py`, `simple_repro.py`, `check_origin.py`.
    """
    p = path.replace("\\", "/")
    if is_scratch(p) or p.endswith(_SCRATCH_SUFFIXES):
        return True
    if p.startswith("/tmp/") or "/tmp/" in p or p.split("/", 1)[0] in {"tmp", ".tmp"}:
        return True
    return created and "/" not in p


def is_test_or_build(path: str) -> bool:
    p = path.replace("\\", "/")
    base = p.rsplit("/", 1)[-1]
    if is_protected(p):
        return True
    if base in _CI_PACKAGING_BASENAMES or (
        base.startswith("requirements") and base.endswith(".txt")
    ):
        return True
    return p.startswith(".github/") or "/.github/" in p


def created_files(diff: str) -> set[str]:
    """Paths the diff adds from nothing.

    Three spellings all occur in this corpus and only taking all three gets the
    right answer: `--- /dev/null`, `new file mode`, and -- the one the gold
    patches use, with no `/dev/null` anywhere -- a `@@ -0,0 +1,N @@` header
    under an ordinary `--- a/path`.
    """
    out: set[str] = set()
    current: str | None = None
    marked = False
    for line in (diff or "").splitlines():
        if line.startswith("diff --git "):
            marked = False
        elif line.startswith("new file mode"):
            marked = True
        elif line.startswith("--- "):
            marked = marked or line[4:].split("\t")[0].strip() == "/dev/null"
        elif line.startswith("+++ "):
            p = line[4:].split("\t")[0].strip()
            current = None if p == "/dev/null" else (
                p[2:] if p.startswith(("a/", "b/")) else p
            )
            if current and marked:
                out.add(current)
            marked = False
        elif line.startswith("@@ -0,0 ") and current:
            out.add(current)
    return out


def env_mismatch(log_text: str, task) -> str:
    """The first environment signature in this log, or "" -- see ENV_SIGNATURES."""
    for signature, guard in ENV_SIGNATURES:
        if signature in log_text and guard not in task.patch and guard not in task.test_patch:
            return signature
    return ""


def reproduced_gold(agent_patch: str, gold_patch: str) -> bool:
    """True if the agent's diff contains every gold hunk body, verbatim.

    Exact and positional-free (see `tasks.edit_bodies`): if this is True the
    agent wrote the gold fix, whatever else it also wrote. A task that is True
    here and `resolved == False` is a **false negative of the local metric**,
    not a patch-quality failure, and must not be counted as one.
    """
    gold = edit_bodies(gold_patch)
    if not gold:
        return False
    agent = edit_bodies(agent_patch)
    return all(agent.get(f) == body for f, body in gold.items())


def classify(
    agent_patch: str, gold_patch: str, discount_scratch: bool = False
) -> tuple[str, dict]:
    """Assign one bucket, and return the facts the decision was made on.

    With `discount_scratch`, scratch paths are removed from the agent's side
    before any comparison (pass B) instead of deciding the bucket (pass A).
    """
    agent_ranges = hunk_ranges(agent_patch)
    gold_ranges = hunk_ranges(gold_patch)
    agent_files = set(patch_files(agent_patch))
    gold = set(patch_files(gold_patch))
    created = created_files(agent_patch)
    scratch = sorted(p for p in agent_files if looks_like_scratch(p, p in created))
    if discount_scratch:
        agent_files -= set(scratch)
        agent_ranges = {f: r for f, r in agent_ranges.items() if f not in set(scratch)}
    shared = agent_files & gold
    overlapping = {
        f
        for f in shared
        if ranges_overlap(agent_ranges.get(f, []), gold_ranges.get(f, []))
    }
    extras = agent_files - gold
    missed_regions = sum(
        1
        for f, rs in gold_ranges.items()
        for r in rs
        if not ranges_overlap([r], agent_ranges.get(f, []))
    )
    facts = dict(
        agent_files=len(agent_files),
        gold_files=len(gold),
        shared=len(shared),
        overlapping=len(overlapping),
        extras=sorted(extras),
        missed_gold_files=len(gold - agent_files),
        missed_gold_regions=missed_regions,
        created=sorted(created),
        scratch=scratch,
    )

    if scratch and not discount_scratch:
        return "scratch_pollution", facts
    tests = sorted(p for p in agent_files if is_test_or_build(p))
    if tests:
        facts["test_paths"] = tests
        return "test_edit", facts
    if not agent_files:
        return "no_source_edit", facts
    if not shared:
        return "wrong_file", facts
    if not overlapping:
        return "right_file_wrong_hunk", facts
    if extras:
        return "overreach", facts
    if facts["missed_gold_files"] or missed_regions:
        return "incomplete_fix", facts
    return "right_hunk_wrong_logic", facts


def collect(arm: str, results: Path, tasks: dict, require_log: bool) -> dict:
    """Every ledger row for one arm, annotated with its bucket where applicable."""
    ledger = ROOT / "ledger" / "runs" / arm / "task_results.jsonl"
    rows = [json.loads(line) for line in ledger.open(encoding="utf-8") if line.strip()]
    patches = results / arm / "patches"
    logs = results / arm / "test_outputs"
    recs: list[dict] = []
    skipped = Counter()
    for row in rows:
        iid = row["instance_id"]
        task = tasks.get(iid)
        if task is None:
            skipped["task not in tasks.jsonl"] += 1
            continue
        pf = patches / f"{iid}.patch"
        text = pf.read_text(encoding="utf-8", errors="replace") if pf.is_file() else ""
        if not text.strip():
            skipped["no patch produced"] += 1
            continue
        log = logs / f"{iid}.log"
        if require_log and not log.is_file():
            skipped["patch but no test log (apply unverified)"] += 1
            continue
        log_text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
        graded = bool(log_text) and COLLECTION_ABORT not in log_text
        bucket, facts = classify(text, task.patch)
        bucket_b, facts_b = classify(text, task.patch, discount_scratch=True)
        recs.append(
            dict(
                instance_id=iid,
                resolved=bool(row["resolved"]),
                errored=bool(row.get("error")),
                error=row.get("error") or "",
                files_touched=int(row.get("files_touched") or facts["agent_files"]),
                patch_bytes=int(row.get("patch_bytes") or len(text)),
                gold_bytes=len(task.patch),
                gold_hit=bool(row.get("gold_hit")),
                graded=graded,
                env_error=env_mismatch(log_text, task),
                reproduced_gold=reproduced_gold(text, task.patch),
                bucket=bucket,
                bucket_b=bucket_b,
                src_files=facts_b["agent_files"],
                src_extras=facts_b["extras"],
                src_overlapping=facts_b["overlapping"],
                **facts,
            )
        )
    return dict(arm=arm, n_rows=len(rows), recs=recs, skipped=skipped)


def _bucket_line(label: str, recs: list[dict], key: str = "bucket") -> str:
    counts = Counter(r[key] for r in recs)
    buckets = BUCKETS if key == "bucket" else BUCKETS_DISCOUNTED
    parts = []
    for b in buckets:
        k = counts[b]
        parts.append(f"{b}={k}" + ("(n<5)" if 0 < k < 5 else ""))
    return f"   {label:26s} n={len(recs):3d} | " + "  ".join(parts)


def _taxonomy(recs: list[dict], key: str) -> None:
    failed = [r for r in recs if not r["resolved"]]
    print(_bucket_line("APPLIED AND FAILED", failed, key))
    print(_bucket_line("  no harness error", [r for r in failed if not r["errored"]], key))
    print(_bucket_line("  cut off by the cap", [r for r in failed if r["errored"]], key))
    print(_bucket_line("RESOLVED (contrast only)",
                       [r for r in recs if r["resolved"]], key))


def report(block: dict) -> None:
    arm, recs = block["arm"], block["recs"]
    failed = [r for r in recs if not r["resolved"]]
    won = [r for r in recs if r["resolved"]]
    print(f"\n== {arm}: {block['n_rows']} ledger rows, {len(recs)} applied")
    for reason, k in sorted(block["skipped"].items()):
        print(f"   excluded: {k:3d}  {reason}")

    graded = [r for r in recs if r["graded"]]
    print("\n   -- was the patch even graded? (read this before any bucket) --")
    print(f"     tests actually ran          {len(graded):3d} / {len(recs)}")
    print(f"     collection aborted          {len(recs) - len(graded):3d} / {len(recs)}"
          "   <- zero tests ran; the outcome cannot depend on the patch")
    if graded:
        print(f"     resolution among graded     {sum(r['resolved'] for r in graded)}"
              f"/{len(graded)}")
    print(f"     known env mismatch in log   {sum(1 for r in recs if r['env_error']):3d}"
          f" / {len(recs)}   <- a traceback the agent cannot cause or fix")
    clean = [r for r in recs if r["graded"] and not r["env_error"]]
    print(f"     graded AND no env signature {len(clean):3d} / {len(recs)}"
          "   <- the only subset where a failure means a bad patch")
    rg = [r for r in recs if r["reproduced_gold"]]
    print(f"     wrote the gold fix verbatim {len(rg):3d} / {len(recs)}"
          f"  of which resolved {sum(r['resolved'] for r in rg)},"
          f" never graded {sum(1 for r in rg if not r['graded'])},"
          f" env mismatch {sum(1 for r in rg if r['env_error'])}")

    print("\n   -- PASS A: hygiene first, as specified (one bucket per patch) --")
    _taxonomy(recs, "bucket")
    print("\n   -- PASS B: scratch paths discounted, so the reasoning shows --")
    _taxonomy(recs, "bucket_b")
    if clean:
        print("\n   -- PASS B on graded + env-clean tasks only: the honest table --")
        _taxonomy(clean, "bucket_b")

    print("\n   -- mechanism incidence, NOT exclusive, among applied-and-failed --")
    n = len(failed)
    def inc(label: str, pred) -> None:
        k = sum(1 for r in failed if pred(r))
        print(f"     {label:34s} {k:3d} / {n}" + ("   (n<5)" if 0 < k < 5 else ""))
    inc("leaked a scratch path", lambda r: r["scratch"])
    inc("created a file anywhere", lambda r: r["created"])
    inc("touched a test/CI/packaging path", lambda r: r.get("test_paths"))
    inc("touched >=1 non-gold path (any)", lambda r: r["extras"])
    inc("touched >=1 non-gold source path", lambda r: r["src_extras"])
    inc("missed >=1 gold hunk region", lambda r: r["missed_gold_regions"])
    inc("missed >=1 gold file", lambda r: r["missed_gold_files"])
    inc("met a gold region after discount", lambda r: r["src_overlapping"])
    if won:
        k = sum(1 for r in won if r["scratch"])
        print(f"     RESOLVED anyway with a scratch leak {k:3d} / {len(won)}"
              "   <- a leak is not sufficient to fail (n<5)")

    print("\n   -- scope vs gold, among applied-and-failed --")
    scope = Counter()
    for r in failed:
        scope["fewer than gold" if r["src_files"] < r["gold_files"]
              else "same count" if r["src_files"] == r["gold_files"]
              else "more than gold"] += 1
    for k in ("fewer than gold", "same count", "more than gold"):
        print(f"     source files {k:16s} {scope[k]:3d} / {n}")
    med = lambda key: st.median(r[key] for r in failed)  # noqa: E731
    print(f"     median files touched   all {med('agent_files'):.1f}"
          f"  source-only {med('src_files'):.1f}  gold {med('gold_files'):.1f}")
    print(f"     median patch bytes     agent {med('patch_bytes'):,.0f}"
          f"  gold {med('gold_bytes'):,.0f}")
    print(f"     ledger files_touched agrees with the diff: "
          f"{sum(1 for r in failed if r['files_touched'] == r['agent_files'])} / {n}")


def pooled(blocks: list[dict]) -> None:
    recs = [r for b in blocks for r in b["recs"]]
    graded = [r for r in recs if r["graded"]]
    clean = [r for r in recs if r["graded"] and not r["env_error"]]
    print(f"\n== POOLED over {len(blocks)} arm(s)")
    print(f"   {len(recs)} applied | graded {len(graded)} | graded+env-clean {len(clean)}"
          f" | wrote the gold fix verbatim {sum(1 for r in recs if r['reproduced_gold'])}"
          f" ({sum(1 for r in recs if r['reproduced_gold'] and not r['resolved'])}"
          " of them scored unresolved)")
    print("   -- PASS A --")
    _taxonomy(recs, "bucket")
    print("   -- PASS B --")
    _taxonomy(recs, "bucket_b")
    print("   -- PASS B, graded + env-clean only --")
    _taxonomy(clean, "bucket_b")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--arm", action="append",
                    help="ledger run_id, repeatable; defaults to the P008 pair")
    ap.add_argument("--results", type=Path, default=ROOT / "results",
                    help="directory holding results/<arm>/patches (default: ./results)")
    ap.add_argument("--tasks", type=Path, default=ROOT / "data" / "tasks" / "tasks.jsonl")
    ap.add_argument("--no-require-log", action="store_true",
                    help="count a non-empty patch as applied without a test-output log")
    ap.add_argument("--show", action="append", default=[],
                    help="print the per-task detail for this bucket, repeatable")
    ap.add_argument("--show-pass", choices=("a", "b"), default="a",
                    help="which pass --show refers to (default: a)")
    args = ap.parse_args()

    arms = args.arm or ["clamp_v00", "clamp_v08"]
    tasks = {t.instance_id: t for t in load_tasks(args.tasks)}

    blocks = []
    for arm in arms:
        if not (args.results / arm / "patches").is_dir():
            print(f"no patches dir for {arm} under {args.results}", file=sys.stderr)
            continue
        block = collect(arm, args.results, tasks, not args.no_require_log)
        if not block["recs"]:
            print(f"no applied patches matched for {arm}", file=sys.stderr)
            continue
        report(block)
        blocks.append(block)

    if not blocks:
        return 1
    if len(blocks) > 1:
        pooled(blocks)

    key = "bucket" if args.show_pass == "a" else "bucket_b"
    for bucket in args.show:
        print(f"\n== detail: {bucket} (pass {args.show_pass})")
        for block in blocks:
            for r in block["recs"]:
                if r[key] != bucket or r["resolved"]:
                    continue
                print(f"   {block['arm']:10s} {r['instance_id']:16s}"
                      f" files {r['agent_files']}/{r['gold_files']}"
                      f" shared {r['shared']} overlap {r['overlapping']}"
                      f" missed_regions {r['missed_gold_regions']}"
                      f" extras {r['extras'] or '-'}"
                      f" created {r['created'] or '-'}"
                      f"{'  [errored]' if r['errored'] else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
