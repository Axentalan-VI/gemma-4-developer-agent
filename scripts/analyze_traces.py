"""Read agent traces and answer what the agent actually did, call by call.

    python -X utf8 scripts/analyze_traces.py --traces <dir>
    python -X utf8 scripts/analyze_traces.py --traces <dir> --task fastapi_14099

Needs no GPU: the traces are already on disk, and they are the only artifact that
records *behaviour* rather than outcome. The ledger says a task used 29 calls and
produced nothing; only the trace says whether it was looping on one failing edit,
reading files forever, or thrashing between hypotheses -- and those three call for
completely different fixes.

Read calls from the structured `tool_calls` field, never from message text. An
agent step that carries tool calls has no `message` key at all: the call is in
`tool_calls` and its result in `observation`. Only final-answer steps have
`message`, so a regex over message text finds almost nothing while looking like
it worked -- an empty tool column reads exactly like an agent that never called a
tool, which is one of the hypotheses this script exists to test.

Use `-X utf8` on Windows, not `PYTHONUTF8=1`: traces carry emoji from repository
issue text and the cp1252 default codec dies on them. `-I` implies `-E`, which
discards the environment variable, so the flag is the reliable form.

Schema actually observed (`schema_version: 1`):

    steps[i] = {step_id, source: system|user|agent, extra: {...},
                # agent steps that act:
                tool_calls: [{tool_call_id, function_name, arguments,
                              extra: {author, elapsed_s, usage}}],
                observation: {content}, metrics: {...}, llm_call_count,
                # system/user steps and final agent steps instead:
                message: str}
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

#: Writes to any path outside this prefix land in the diff as a leaked file.
#: probe_c12 leaked a scratch file in 4 of 12 tasks, which is why gold_exact was
#: 0/12: any extra path makes `files != gold_files`.
SCRATCH_PREFIX = "/tmp"

#: Argument keys that name a path. `filepath` is the one the harness's own
#: `write_file`/`edit_file` signatures use -- verified against probe_c12, where
#: it appears on 156 of 156 write/edit calls. The others are kept as a hedge
#: against a signature change, not because they were observed.
PATH_KEYS = ("filepath", "path", "file_path", "filename", "file")

#: Tools decorated `@budget_gated(count_tool_call=False)` in the harness
#: (`swegemma__execution.py:71,101`). They are free without limit: 13713 called
#: `submit_patch` 146 times after its budget was gone and nothing stopped it.
FREE_TOOLS = frozenset({"submit_patch", "get_status"})

#: Sub-agent names, for recognising an ADK AgentTool invocation. The wrapper is
#: not a budget_gated harness tool, so invoking it is free -- but every call the
#: sub-agent then makes spends the *root* agent's budget. Discovered from the
#: trace's authors; this literal is a hedge for a sub-agent that is invoked and
#: makes no call of its own, in which case it never appears as an author.
KNOWN_AGENT_TOOLS = frozenset({"code_analyzer"})


def step_disposition(step: dict) -> str:
    """How the harness answered a step: `ok`, `refused` or `malformed`.

    Read from the observation, because the three are indistinguishable from the
    call itself. `malformed` is ADK rejecting a call for a missing mandatory
    argument before the tool runs -- its payload carries `error` and no
    `status`, where every harness response carries `status`.
    """
    obs = step.get("observation")
    content = obs.get("content") if isinstance(obs, dict) else obs
    blob = content if isinstance(content, str) else json.dumps(content, default=str)
    try:
        payload = json.loads(blob)
    except Exception:
        return "ok"
    if not isinstance(payload, dict):
        return "ok"
    if "error" in payload and "status" not in payload:
        return "malformed"
    if payload.get("error_type") == "BudgetExceeded":
        return "refused"
    return "ok"


def sub_agent_names(trace: dict) -> frozenset[str]:
    """Every author that is not the root agent, plus the known hedge."""
    authors = {call_author(c) for _, c in iter_calls(trace)}
    return frozenset({a for a in authors if a and a != ROOT_AUTHOR} | KNOWN_AGENT_TOOLS)


def classify_calls(trace: dict):
    """Yield (call, disposition) for every emitted call, in order.

    `disposition` is one of `counted`, `free`, `agent_tool`, `malformed`,
    `refused` -- and only `counted` moves the harness's `tool_calls_used`.
    A step carrying several calls shares one observation, so `malformed` and
    `refused` are attributed to all of them; on P005 that affected 3 steps of
    1424 calls and cost nothing, since all three were answered `ok`.
    """
    subs = sub_agent_names(trace)
    for step in trace.get("steps", []):
        calls = step.get("tool_calls")
        if not calls:
            continue
        disp = step_disposition(step)
        for call in calls:
            if not isinstance(call, dict):
                continue
            name = call_name(call)
            if name in FREE_TOOLS:
                yield call, "free"
            elif name in subs:
                yield call, "agent_tool"
            elif disp != "ok":
                yield call, disp
            else:
                yield call, "counted"


def reconcile(trace: dict) -> Counter:
    """Split emitted calls into the harness's budget categories.

    `reconcile(trace)["counted"]` reproduces the ledger's `tool_calls_used`
    exactly, for all 12 tasks of P005 -- which is what settles the apparent
    100-vs-565 contradiction there. Both numbers were right: 565 calls were
    emitted, 100 of them consumed budget.
    """
    rec = Counter()
    for _, disp in classify_calls(trace):
        rec["emitted"] += 1
        rec[disp] += 1
    return rec


def load_trace(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def iter_calls(trace: dict):
    """Yield (step_id, call) for every tool call, in order.

    Steps without `tool_calls` are skipped rather than scanned for tool names:
    prose that says "I will now call edit_file" is not a call.
    """
    for s in trace.get("steps", []):
        calls = s.get("tool_calls")
        if not calls:
            continue
        for c in calls:
            if isinstance(c, dict):
                yield s.get("step_id"), c


def call_name(call: dict) -> str:
    return str(call.get("function_name") or "")


def call_author(call: dict) -> str:
    """Which agent spent the call. Sub-agent calls draw on the root agent's
    budget, so attribution is the question, not a detail."""
    ex = call.get("extra")
    return str((ex or {}).get("author") or "") if isinstance(ex, dict) else ""


def call_paths(call: dict) -> list[str]:
    args = call.get("arguments")
    if not isinstance(args, dict):
        return []
    return [str(args[k]) for k in PATH_KEYS if isinstance(args.get(k), str)]


def call_fingerprint(call: dict) -> str:
    """Name plus arguments, so an identical re-issue can be told from the same
    tool used on something new. The first is a loop; the second is progress."""
    args = call.get("arguments")
    try:
        blob = json.dumps(args, sort_keys=True, default=str)
    except Exception:
        blob = repr(args)
    return f"{call_name(call)}({blob})"


def longest_repeat_run(names: list[str]) -> tuple[int, str]:
    """Longest run of one repeated tool: the signature of a stuck loop."""
    best, best_tool, cur, cur_tool = 0, "", 0, ""
    for t in names:
        cur, cur_tool = (cur + 1, cur_tool) if t == cur_tool else (1, t)
        if cur > best:
            best, best_tool = cur, cur_tool
    return best, best_tool


def summarize(path: Path, verbose: bool = False) -> dict:
    trace = load_trace(path)
    classified = list(classify_calls(trace))
    calls = [c for c, _ in classified]
    names = [call_name(c) for c in calls]
    metrics = trace.get("final_metrics") or {}

    # Behaviour metrics read *counted* calls only. A call the harness refused
    # after exhaustion never ran, and a malformed call never reached the tool,
    # so neither can edit a file or constitute a re-issue of real work.
    counted = [c for c, d in classified if d == "counted"]
    fps = [call_fingerprint(c) for c in counted]

    workspace_writes = sum(
        1 for c in counted
        if call_name(c) in ("write_file", "edit_file")
        and any(not p.startswith(SCRATCH_PREFIX) for p in call_paths(c))
    )
    # Re-issues, not occurrences: 3 identical calls are 2 re-issues.
    repeat_args = sum(n - 1 for n in Counter(fps).values() if n > 1)

    # Position of the first charged edit, and how many edits were attempted at
    # all. An agent that never reaches an edit has a different disease from one
    # whose edits are wrong, and only the first number tells them apart.
    editing = ("write_file", "edit_file")
    first_edit = next(
        (n for n, c in enumerate(counted, start=1) if call_name(c) in editing), None)
    edit_attempts = sum(1 for c in calls if call_name(c) in editing)

    rec = reconcile(trace)
    info = {
        "first_edit": first_edit,
        "edit_attempts": edit_attempts,
        "task": path.stem.replace("trace_", ""),
        "steps": len(trace.get("steps", [])),
        "n_calls": len(calls),          # emitted, including the free and refused
        "n_counted": rec["counted"],    # == the ledger's tool_calls_used
        "n_free": rec["free"],
        "n_agent_tool": rec["agent_tool"],
        "n_malformed": rec["malformed"],
        "n_refused": rec["refused"],
        "tools": Counter(names),
        "by_author": Counter(a for a in (call_author(c) for c in calls) if a),
        "counted_by_author": Counter(a for a in (call_author(c) for c in counted) if a),
        "longest_run": longest_repeat_run(names),
        "repeat_args": repeat_args,
        "workspace_writes": workspace_writes,
        "prompt_tokens": metrics.get("total_prompt_tokens", 0),
        "submitted": names.count("submit_patch"),
    }

    if verbose:
        print(f"=== {info['task']}: {info['steps']} steps, {info['n_calls']} tool calls ===")
        for sid, c in iter_calls(trace):
            ex = c.get("extra") if isinstance(c.get("extra"), dict) else {}
            el = ex.get("elapsed_s")
            el_s = f"{el:8.1f}s" if isinstance(el, (int, float)) else " " * 9
            args = json.dumps(c.get("arguments"), default=str)[:160].replace("\n", " ")
            print(f"[{str(sid):>4}] {el_s} {call_author(c)[:13]:13s} {call_name(c):22s} {args}")
        print()
    return info


#: Per-task continuous metrics that a paired comparison can move. Deliberately
#: NOT resolution: 12 tasks at k=1 cannot separate a +0.05 effect from noise, so
#: comparing resolution here would invite reading noise as a result. These two are
#: what `v03_budget_guard` targets directly, and both had large measured baselines
#: in probe_c12 (coder share 47%, re-issue rate 235/491).
#: `counted_calls` replaced an earlier `n_calls` that counted *emitted* calls.
#: The rename is deliberate: the three rates below now denominate on calls that
#: actually spent budget, so figures recorded before 2026-10-12 (probe_c12's
#: coder_call_share 0.289 / reissue_rate 0.399) are not comparable to new ones.
COMPARED = ("coder_call_share", "reissue_rate", "counted_calls", "workspace_writes")

#: The root agent's author name in the harness's traces. Everything else is a
#: sub-agent spending the root agent's budget.
ROOT_AUTHOR = "swe_coder"


def task_metrics(path: Path) -> dict[str, float]:
    """The comparable per-task numbers, from one trace."""
    info = summarize(path)
    n = info["n_counted"]
    coder = info["counted_by_author"].get(ROOT_AUTHOR, 0)
    return {
        "coder_call_share": (coder / n) if n else 0.0,
        "reissue_rate": (info["repeat_args"] / n) if n else 0.0,
        "counted_calls": float(n),
        "workspace_writes": float(info["workspace_writes"]),
    }


def arm_metrics(d: Path | str) -> dict[str, dict[str, float]]:
    """{task: metrics} for one trace directory."""
    return {f.stem.replace("trace_", ""): task_metrics(f)
            for f in sorted(Path(d).glob("trace_*.json"))}


def paired_tasks(dir_a: Path | str, dir_b: Path | str) -> tuple[list[str], list[str]]:
    """(tasks in both arms, tasks in only one) -- the second is reported, not used."""
    ma, mb = arm_metrics(dir_a), arm_metrics(dir_b)
    return sorted(set(ma) & set(mb)), sorted(set(ma) ^ set(mb))


def compare_arms(dir_a: Path | str, dir_b: Path | str,
                 label_a: str = "A", label_b: str = "B") -> list:
    """Paired comparison of two trace directories, task by task.

    Only tasks present in BOTH arms are used. A task missing from one arm almost
    always means that arm failed on it, which is informative on its own and must
    not be imputed or averaged across two different task sets.
    """
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from swegemma_lab.stats import paired_delta

    ma, mb = arm_metrics(dir_a), arm_metrics(dir_b)
    shared = sorted(set(ma) & set(mb))
    return [paired_delta(m, [(ma[t][m], mb[t][m]) for t in shared]) for m in COMPARED]


def render_comparison(deltas, label_a: str, label_b: str,
                      shared: list[str], unpaired: list[str]) -> str:
    lines = [f"paired comparison: {label_a} -> {label_b}",
             f"  {len(shared)} task(s) in both arms"]
    if unpaired:
        lines.append(f"  {len(unpaired)} task(s) in only one arm, DROPPED: "
                     f"{', '.join(unpaired)}")
        lines.append("    A task missing from an arm usually means that arm failed on it.")
    lines.append("")
    for d in deltas:
        lines.append(d.render())
    lines.append("")
    lines.append("  Resolution rate is deliberately absent: 12 tasks at k=1 cannot")
    lines.append("  separate a +0.05 effect from noise. Read the ledger for that, and")
    lines.append("  only against the k=4 reference.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--traces", required=True)
    ap.add_argument("--task", help="dump one task's full call sequence")
    ap.add_argument("--compare", metavar="OTHER_TRACES",
                    help="paired comparison against a second arm's trace directory")
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    args = ap.parse_args(argv)

    tdir = Path(args.traces)
    files = sorted(tdir.glob("trace_*.json"))
    if not files:
        raise SystemExit(f"no trace_*.json in {tdir}")

    if args.compare:
        other = Path(args.compare)
        if not sorted(other.glob("trace_*.json")):
            raise SystemExit(f"no trace_*.json in {other}")
        shared, unpaired = paired_tasks(tdir, other)
        deltas = compare_arms(tdir, other, args.label_a, args.label_b)
        print(render_comparison(deltas, args.label_a, args.label_b, shared, unpaired))
        return 0

    if args.task:
        match = [f for f in files if args.task in f.stem]
        if not match:
            raise SystemExit(f"no trace for {args.task}")
        summarize(match[0], verbose=True)
        return 0

    infos = [summarize(f) for f in files]
    head = (f"{'task':18s} {'emit':>5s} {'count':>6s} {'free':>5s} {'refus':>6s} "
            f"{'malf':>5s} {'reissue':>8s} {'1edit':>6s} {'wr!tmp':>7s} {'sub':>5s} "
            f"{'loop':>16s}")
    print(head)
    print("-" * len(head))
    for i in sorted(infos, key=lambda d: -d["n_calls"]):
        rl, rt = i["longest_run"]
        loop = f"{rl}x {rt}" if rl >= 3 else ""
        sub = sum(n for a, n in i["counted_by_author"].items() if a != ROOT_AUTHOR)
        fe = "never" if i["first_edit"] is None else str(i["first_edit"])
        print(f"{i['task']:18s} {i['n_calls']:5d} {i['n_counted']:6d} {i['n_free']:5d} "
              f"{i['n_refused']:6d} {i['n_malformed']:5d} {i['repeat_args']:8d} "
              f"{fe:>6s} {i['workspace_writes']:7d} {sub:5d} {loop:>16s}")
    print()
    print("  count == the ledger's tool_calls_used. free = submit_patch/get_status")
    print("  (never charged). refus = emitted after the cap, refused and uncounted:")
    print("  budget exhaustion does NOT end the episode. malf = rejected by ADK for a")
    print("  missing mandatory argument, so it never reached the tool.")
    print("  1edit = which charged call first tried to change source. `never` is the")
    print("  signature of a task that spent its whole budget without attempting a fix.")

    agg, auth = Counter(), Counter()
    for i in infos:
        agg.update(i["tools"])
        auth.update(i["by_author"])
    print()
    print(f"Tool use across {len(infos)} traces ({sum(agg.values())} calls):")
    for t, n in agg.most_common():
        print(f"  {n:5d}  {t}")
    print("Calls by author:")
    for a, n in auth.most_common():
        print(f"  {n:5d}  {a}")
    no_patch = [i["task"] for i in infos if not i["submitted"]]
    if no_patch:
        print(f"\nNever called submit_patch ({len(no_patch)}/{len(infos)}): "
              f"{', '.join(no_patch)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
