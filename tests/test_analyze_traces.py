"""Tests for trace mining.

The trace is the only artifact that records *behaviour* rather than outcome, and
it is the only one we have for the four probe_c12 tasks that burned 28-30 of 30
calls and emitted nothing. So the thing worth protecting is that tool calls are
read from the structured `tool_calls` field on agent steps.

The first version of `analyze_traces.py` matched tool names with a regex over
`step["message"]`. Agent steps that carry tool calls have **no `message` key at
all** -- the call lives in `tool_calls` and the result in `observation` -- so it
reported 2 calls across 12 traces while the ledger recorded 28-30 per task. A
silent undercount is worse than a crash here, because an empty tool column reads
exactly like an agent that never called a tool, which is one of the hypotheses
the script exists to test. The fixtures below are therefore built to the schema
the real traces use, keyed off `schema_version`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import analyze_traces as at  # noqa: E402


def _call(name: str, cid: str, author: str = "swe_coder", **args) -> dict:
    return {
        "tool_call_id": cid,
        "function_name": name,
        "arguments": args,
        "extra": {"elapsed_s": 1.0, "timestamp": 0.0, "author": author},
    }


def _agent_step(sid: int, calls: list[dict], tokens: int = 5000) -> dict:
    """An agent step as the harness really writes one: tool_calls, no message."""
    return {
        "step_id": sid,
        "source": "agent",
        "tool_calls": calls,
        "observation": {"content": '{"status": "ok", "stdout": ""}'},
        "metrics": {"prompt_tokens": tokens, "completion_tokens": 100,
                    "cached_tokens": 0, "total_tokens": tokens + 100},
        "model_name": "gemma-4",
        "llm_call_count": 1,
        "extra": {"elapsed_s": float(sid), "timestamp": 0.0, "author": "swe_coder"},
    }


def _write_trace(d: Path, task: str, steps: list[dict], prompt_tokens: int = 200000) -> Path:
    trace = {
        "schema_version": 1,
        "agent": "swe_coder",
        "steps": steps,
        "final_metrics": {
            "total_prompt_tokens": prompt_tokens,
            "total_completion_tokens": 5000,
            "total_cached_tokens": 0,
            "total_tokens": prompt_tokens + 5000,
            "total_steps": len(steps),
        },
    }
    p = d / f"trace_{task}.json"
    p.write_text(json.dumps(trace), encoding="utf-8")
    return p


def test_counts_structured_tool_calls(tmp_path):
    """The regression: calls live in tool_calls, not in message text."""
    p = _write_trace(tmp_path, "repo_1", [
        {"step_id": 0, "source": "system", "message": "You are an engineer.",
         "extra": {"event_type": "system_instruction"}},
        _agent_step(1, [_call("read_file", "call_1", path="a.py")]),
        _agent_step(2, [_call("run_command", "call_2", command="pytest"),
                        _call("edit_file", "call_3", path="a.py")]),
    ])
    info = at.summarize(p)
    assert info["n_calls"] == 3, "three tool calls across two agent steps"
    assert info["tools"]["read_file"] == 1
    assert info["tools"]["run_command"] == 1
    assert info["tools"]["edit_file"] == 1


def test_a_step_without_tool_calls_is_not_a_call(tmp_path):
    """Final-answer agent steps carry `message` and must not be counted."""
    p = _write_trace(tmp_path, "repo_2", [
        _agent_step(1, [_call("read_file", "call_1", path="a.py")]),
        {"step_id": 2, "source": "agent", "message": "I will now call edit_file.",
         "metrics": {"prompt_tokens": 100, "completion_tokens": 10,
                     "cached_tokens": 0, "total_tokens": 110},
         "model_name": "gemma-4", "llm_call_count": 1,
         "extra": {"event_type": "final", "author": "swe_coder"}},
    ])
    info = at.summarize(p)
    assert info["n_calls"] == 1, "prose naming a tool is not a tool call"
    assert "edit_file" not in info["tools"]


def test_longest_repeat_run_finds_a_stuck_loop(tmp_path):
    """Four identical edit_file calls in a row is the signature we are hunting."""
    calls = [_call("edit_file", f"call_{i}", path="a.py") for i in range(4)]
    p = _write_trace(tmp_path, "repo_3", [_agent_step(i + 1, [c]) for i, c in enumerate(calls)])
    info = at.summarize(p)
    assert info["longest_run"] == (4, "edit_file")


def test_identical_arguments_are_reported_separately_from_tool_repeats(tmp_path):
    """Re-running the same command verbatim is a tighter loop signal than
    re-using the same tool with new arguments."""
    same = [_call("run_command", f"call_{i}", command="pytest -x") for i in range(3)]
    varied = [_call("read_file", f"call_{i}", path=f"f{i}.py") for i in range(3)]
    p = _write_trace(tmp_path, "repo_4",
                     [_agent_step(i + 1, [c]) for i, c in enumerate(same + varied)])
    info = at.summarize(p)
    assert info["repeat_args"] == 2, "two re-issues of an identical call"


def test_scratch_write_inside_workspace_is_flagged(tmp_path):
    """A write outside /tmp leaks a file into the diff; a /tmp write does not.

    The argument key is `filepath`. It was `path` in the first draft of this
    test, which made the column read 0 against real traces that leaked a file
    in 4 of 12 tasks -- a wrong answer rather than an error.
    """
    p = _write_trace(tmp_path, "repo_5", [
        _agent_step(1, [_call("write_file", "call_1", filepath="repro.py", content="x")]),
        _agent_step(2, [_call("write_file", "call_2", filepath="/tmp/scratch.py", content="x")]),
    ])
    info = at.summarize(p)
    assert info["workspace_writes"] == 1


def test_edit_file_counts_as_a_workspace_write(tmp_path):
    """`edit_file` is how the agent changes tracked source; it was 143 of the
    156 write/edit calls in probe_c12, so omitting it would hide most of them."""
    p = _write_trace(tmp_path, "repo_5b", [
        _agent_step(1, [_call("edit_file", "call_1", filepath="pkg/core.py",
                              old_string="a", new_string="b")]),
    ])
    assert at.summarize(p)["workspace_writes"] == 1


def test_subagent_calls_are_attributed_to_their_author(tmp_path):
    """Sub-agent calls spend the root budget, so who spent it is the question."""
    p = _write_trace(tmp_path, "repo_6", [
        _agent_step(1, [_call("code_analyzer", "call_1", author="swe_coder", request="r")]),
        _agent_step(2, [_call("search_similar_code", "call_2", author="code_analyzer", q="x"),
                        _call("get_code_neighbors", "call_3", author="code_analyzer", sym="y")]),
    ])
    info = at.summarize(p)
    assert info["by_author"]["code_analyzer"] == 2
    assert info["by_author"]["swe_coder"] == 1


def test_unknown_tool_names_are_kept_not_dropped(tmp_path):
    """The tool list is the harness's, not ours; a new tool must still count."""
    p = _write_trace(tmp_path, "repo_7", [
        _agent_step(1, [_call("some_future_tool", "call_1", x=1)]),
    ])
    info = at.summarize(p)
    assert info["n_calls"] == 1
    assert info["tools"]["some_future_tool"] == 1


def test_cli_runs_over_a_directory(tmp_path):
    _write_trace(tmp_path, "repo_8", [_agent_step(1, [_call("read_file", "call_1", path="a.py")])])
    r = subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "analyze_traces.py"),
         "--traces", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "repo_8" in r.stdout
    assert "read_file" in r.stdout


def test_cli_fails_loudly_on_an_empty_directory(tmp_path):
    r = subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "analyze_traces.py"),
         "--traces", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert r.returncode != 0


# --- paired comparison of two arms ------------------------------------------
#
# What the paired run has to answer is NOT the resolution rate (12 tasks at k=1
# cannot separate a +0.05 effect from noise). It is whether v03 moved the two
# quantities it targets: the coder's share of tool calls, and the fraction of
# calls that are byte-identical re-issues. Both are per-task continuous values,
# so they are compared within task.


def _arm_dir(tmp_path, name, specs):
    """specs: {task: [(tool, author, args_key), ...]} -> a trace dir."""
    d = tmp_path / name
    d.mkdir()
    for task, calls in specs.items():
        steps = []
        for i, (tool, author, key) in enumerate(calls):
            steps.append(_agent_step(i + 1, [_call(tool, f"call_{i}", author=author, q=key)]))
        _write_trace(d, task, steps)
    return d


def test_compare_reports_coder_share_and_reissue_rate(tmp_path):
    # arm a: analyzer spends 3 of 4 calls, and repeats one verbatim.
    a = _arm_dir(tmp_path, "a", {
        "repo_1": [("run_command", "code_analyzer", "x"),
                   ("run_command", "code_analyzer", "x"),
                   ("run_command", "code_analyzer", "y"),
                   ("edit_file", "swe_coder", "z")],
    })
    # arm b: the coder makes 3 of 4 calls, but `submit_patch` is free
    # (`count_tool_call=False`), so it spends 2 of the 3 calls that are
    # actually charged. The share denominates on budget, not on keystrokes --
    # this expectation was 0.75 while free calls were still counted.
    b = _arm_dir(tmp_path, "b", {
        "repo_1": [("run_command", "code_analyzer", "x"),
                   ("read_file", "swe_coder", "p"),
                   ("edit_file", "swe_coder", "q"),
                   ("submit_patch", "swe_coder", "r")],
    })
    cmp_ = at.compare_arms(a, b, label_a="v00", label_b="v03")
    shares = {d.name: d for d in cmp_}
    assert "coder_call_share" in shares
    assert shares["coder_call_share"].mean_a == pytest.approx(0.25)
    assert shares["coder_call_share"].mean_b == pytest.approx(2 / 3)
    assert shares["coder_call_share"].delta == pytest.approx(2 / 3 - 0.25)
    assert shares["reissue_rate"].mean_a == pytest.approx(0.25)
    assert shares["reissue_rate"].mean_b == pytest.approx(0.0)


def test_compare_uses_only_tasks_present_in_both(tmp_path):
    """A task missing from one arm usually means that arm crashed on it. Dropping
    it is right; imputing it would invent data, and silently averaging over
    different task sets would break the pairing."""
    a = _arm_dir(tmp_path, "a2", {
        "shared": [("read_file", "swe_coder", "x")],
        "only_a": [("read_file", "swe_coder", "x")],
    })
    b = _arm_dir(tmp_path, "b2", {
        "shared": [("read_file", "swe_coder", "x")],
    })
    cmp_ = at.compare_arms(a, b)
    assert all(d.n == 1 for d in cmp_), "only the shared task is paired"


def test_compare_with_no_overlap_reports_nothing_measured(tmp_path):
    a = _arm_dir(tmp_path, "a3", {"p": [("read_file", "swe_coder", "x")]})
    b = _arm_dir(tmp_path, "b3", {"q": [("read_file", "swe_coder", "x")]})
    cmp_ = at.compare_arms(a, b)
    assert all(d.n == 0 for d in cmp_)
    assert all(not d.significant for d in cmp_)


def test_compare_cli(tmp_path):
    a = _arm_dir(tmp_path, "a4", {"t1": [("read_file", "swe_coder", "x")]})
    b = _arm_dir(tmp_path, "b4", {"t1": [("read_file", "code_analyzer", "x")]})
    r = subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "analyze_traces.py"),
         "--traces", str(a), "--compare", str(b)],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "coder_call_share" in r.stdout


# --------------------------------------------------------------------------
# Call accounting: emitted calls are not budget-consuming calls
#
# P005 looked like two trusted sources contradicting each other: the ledger
# recorded `tool_calls_used=100` for fastapi_13713 while the trace carried 565
# tool calls. Neither was wrong. The harness increments its counter only in
# `check_budget(count_tool_call=True)` (`swegemma__context.py:542`), and four
# classes of emitted call never reach that increment:
#
#   * `submit_patch` and `get_status` are `@budget_gated(count_tool_call=False)`
#     (`swegemma__execution.py:71,101`) -- free, forever, without limit;
#   * an ADK AgentTool invocation (our `code_analyzer`) is not a budget_gated
#     harness tool at all, though the sub-agent's own calls do count;
#   * a call ADK rejects for a missing mandatory argument never reaches the
#     tool, so the harness never sees it;
#   * once the cap is hit, `check_budget` returns a BudgetExceeded error string
#     and **returns before incrementing** -- so the counter freezes at the cap
#     while the agent stays free to emit calls until wall-clock death.
#
# The last one matters most: budget exhaustion does not end the episode.
# --------------------------------------------------------------------------

def _obs_step(sid: int, calls: list[dict], content: str) -> dict:
    """An agent step whose observation is given verbatim."""
    step = _agent_step(sid, calls)
    step["observation"] = {"content": content}
    return step


REFUSAL = json.dumps({"status": "error", "error_type": "BudgetExceeded",
                      "error_message": "Tool call budget exhausted (100 calls)"})
MALFORMED = json.dumps({"error": "Invoking `edit_file()` failed as the following "
                                 "mandatory input parameters are not present:\nold_string"})


def test_free_tools_do_not_consume_budget(tmp_path):
    """`submit_patch` and `get_status` are gated with count_tool_call=False."""
    p = _write_trace(tmp_path, "repo_free", [
        _agent_step(1, [_call("read_file", "c1", path="a.py")]),
        _agent_step(2, [_call("submit_patch", "c2")]),
        _agent_step(3, [_call("get_status", "c3")]),
    ])
    rec = at.reconcile(at.load_trace(p))
    assert rec["emitted"] == 3
    assert rec["free"] == 2
    assert rec["counted"] == 1, "only read_file touched the budget"


def test_agent_tool_invocation_does_not_consume_budget(tmp_path):
    """The AgentTool wrapper is not a harness tool; the sub-agent's calls are."""
    p = _write_trace(tmp_path, "repo_sub", [
        _agent_step(1, [_call("code_analyzer", "c1", request="where is the bug")]),
        _agent_step(2, [_call("read_file", "c2", author="code_analyzer", path="a.py")]),
    ])
    rec = at.reconcile(at.load_trace(p))
    assert rec["agent_tool"] == 1, "the code_analyzer invocation itself is free"
    assert rec["counted"] == 1, "but the sub-agent's read_file spends root budget"


def test_malformed_call_rejected_by_adk_does_not_consume_budget(tmp_path):
    """ADK rejects a call missing a mandatory argument before the tool runs.

    13207 emitted 26 of these -- the same `edit_file` without `old_string`, over
    and over. Free of budget, but they burn wall clock and context, and they
    inflated that task's `workspace_writes` to 29 when only 3 writes happened.
    """
    p = _write_trace(tmp_path, "repo_malformed", [
        _obs_step(1, [_call("edit_file", "c1", filepath="/workspace/a.py")], MALFORMED),
        _agent_step(2, [_call("edit_file", "c2", filepath="/workspace/a.py",
                              old_string="x", new_string="y")]),
    ])
    rec = at.reconcile(at.load_trace(p))
    assert rec["malformed"] == 1
    assert rec["counted"] == 1, "the well-formed edit is the only one that ran"
    assert at.summarize(p)["workspace_writes"] == 1, "a rejected edit wrote nothing"


def test_calls_after_budget_exhaustion_are_refused_and_uncounted(tmp_path):
    """The counter freezes at the cap; the agent keeps emitting regardless."""
    p = _write_trace(tmp_path, "repo_spin", [
        _agent_step(1, [_call("run_command", "c1", command="pytest")]),
        _obs_step(2, [_call("run_command", "c2", command="pytest")], REFUSAL),
        _obs_step(3, [_call("run_command", "c3", command="pytest")], REFUSAL),
    ])
    rec = at.reconcile(at.load_trace(p))
    assert rec["refused"] == 2
    assert rec["counted"] == 1
    assert rec["emitted"] == 3, "refused calls are still real calls the agent made"


def test_comparison_metrics_denominate_on_counted_calls(tmp_path):
    """Post-exhaustion spinning must not drive the metrics that rank bundles.

    fastapi_13713 scored reissue_rate 0.837 on emitted calls, almost all of it
    310 refused calls and 145 duplicate `submit_patch` calls made after its
    budget was already gone. A bundle that happens to spin longer after
    exhaustion would look worse at identical in-budget behaviour.
    """
    steps = [_agent_step(1, [_call("read_file", "c1", path="a.py")])]
    steps += [_obs_step(i + 2, [_call("run_command", f"r{i}", command="pytest")], REFUSAL)
              for i in range(20)]
    steps += [_agent_step(40 + i, [_call("submit_patch", f"s{i}")]) for i in range(10)]
    p = _write_trace(tmp_path, "repo_denom", steps)

    m = at.task_metrics(p)
    assert m["counted_calls"] == 1, "one call actually spent budget"
    assert m["reissue_rate"] == 0.0, "identical refused calls are not re-issues"
    assert m["coder_call_share"] == 1.0


def test_reconcile_reproduces_the_real_ledger_for_every_p005_task():
    """The golden test: the model must predict `tool_calls_used` exactly.

    Any change to the accounting rules has to keep reproducing all 12 rows of a
    real run. This is what turns the rules from a plausible story into a
    measurement -- it is the whole reason P005's 100-vs-565 is settled.
    """
    traces = ROOT / "results/eval_v10/extracted/resolve60_v00/traces"
    ledger = ROOT / "ledger/runs/resolve60_v00/task_results.jsonl"
    if not traces.is_dir() or not ledger.is_file():
        pytest.skip("P005 artifacts not present in this checkout")

    expected = {}
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            expected[r["instance_id"]] = r["tool_calls_used"]

    checked = 0
    for f in sorted(traces.glob("trace_*.json")):
        task = f.stem.replace("trace_", "")
        if task not in expected:
            continue
        rec = at.reconcile(at.load_trace(f))
        assert rec["counted"] == expected[task], (
            f"{task}: predicted {rec['counted']} counted calls, "
            f"ledger recorded {expected[task]} (emitted {rec['emitted']})")
        checked += 1
    assert checked == 12, f"expected all 12 P005 tasks, reconciled {checked}"


def test_first_edit_index_counts_only_charged_calls(tmp_path):
    """When the agent first tried to change source, in budget-spending calls.

    The sharpest single number from P005: in 4 of the 5 tasks that produced no
    patch, the agent never called `write_file` or `edit_file` even once in 100
    charged calls, and the fifth tried exactly once -- after its budget was
    already exhausted, so the call was refused. Those tasks did not edit badly;
    they never attempted an edit.
    """
    p = _write_trace(tmp_path, "repo_edit", [
        _agent_step(1, [_call("read_file", "c1", path="a.py")]),
        _agent_step(2, [_call("submit_patch", "c2")]),            # free, not an index
        _agent_step(3, [_call("edit_file", "c3", filepath="/workspace/a.py",
                              old_string="x", new_string="y")]),
    ])
    assert at.summarize(p)["first_edit"] == 2, "second charged call, not third emitted"

    q = _write_trace(tmp_path, "repo_noedit", [
        _agent_step(1, [_call("read_file", "c1", path="a.py")]),
        _obs_step(2, [_call("edit_file", "c2", filepath="/workspace/a.py",
                            old_string="x", new_string="y")], REFUSAL),
    ])
    assert at.summarize(q)["first_edit"] is None, "a refused edit never ran"
    assert at.summarize(q)["edit_attempts"] == 1, "but it was still attempted"
