"""Resume correctness for the only script that spends GPU quota.

A bug here either re-runs work we already paid for, or skips a task and quietly
shrinks the denominator. Both corrupt the comparison the run exists to make.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location("session_runner", ROOT / "scripts" / "session_runner.py")
sr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sr)


def results_with(tmp_path: Path, rows: list[str]) -> Path:
    d = tmp_path / "run"
    d.mkdir(parents=True, exist_ok=True)
    (d / "task_results.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return d


def test_already_done_reads_harness_rows(tmp_path):
    d = results_with(
        tmp_path,
        [
            json.dumps({"instance_id": "t1", "resolved": True}),
            json.dumps({"instance_id": "t2", "resolved": False}),
        ],
    )
    assert sr.already_done(d) == {"t1", "t2"}


def test_already_done_accepts_the_id_alias(tmp_path):
    """submission.parquet-style rows use `id` rather than `instance_id`."""
    d = results_with(tmp_path, [json.dumps({"id": "t9", "resolved": True})])
    assert sr.already_done(d) == {"t9"}


def test_already_done_tolerates_a_torn_final_line(tmp_path):
    """A session killed at the Kaggle cap leaves a partial write."""
    d = results_with(
        tmp_path,
        [json.dumps({"instance_id": "t1", "resolved": True}), '{"instance_id": "t2", "resol'],
    )
    done = sr.already_done(d)
    assert done == {"t1"}  # t2 is retried rather than silently skipped


def test_already_done_on_a_fresh_dir_is_empty(tmp_path):
    assert sr.already_done(tmp_path / "nope") == set()


def test_already_done_ignores_rows_without_an_id(tmp_path):
    d = results_with(tmp_path, [json.dumps({"resolved": True}), json.dumps({"instance_id": "t1"})])
    assert sr.already_done(d) == {"t1"}


def test_runspec_defaults_are_the_measurement_budgets(tmp_path):
    """Measurement deliberately keeps the real 100-call ceiling but disables the
    wall clock, so concurrency contention cannot fail a task for reasons
    unrelated to the config under test."""
    spec = sr.load_runspec(None)
    assert spec["max_tool_calls"] == 100
    assert spec["max_time_minutes"] > 60
    # Off by default: vLLM 0.19.1 enables prefix caching itself, and an
    # unrecognised flag would cost a session to discover.
    assert spec["prefix_caching"] is False
    assert spec["reserve_minutes"] > 0


def test_runspec_file_overrides_defaults(tmp_path):
    p = tmp_path / "runspec.json"
    p.write_text(json.dumps({"variant": "v01_hygiene", "concurrency": 4}), encoding="utf-8")
    spec = sr.load_runspec(p)
    assert spec["variant"] == "v01_hygiene"
    assert spec["concurrency"] == 4
    assert spec["max_tool_calls"] == 100  # untouched default survives


def test_grader_compaction_settings_are_used():
    """The public starter ships compaction_interval=15; the grader uses 5. A
    measurement taken under different context management measures a different
    agent."""
    assert sr.COMPACTION["compaction_interval"] == 5
    assert sr.COMPACTION["token_threshold"] == 14336
    assert sr.COMPACTION["event_retention_size"] == 5


# --- The declared-model check is ours now ------------------------------------
#
# The competition replaced swegemma.models.discovery.validate_single_declared_model
# (which discovered the model AND enforced that there was exactly one) with
# adk_submission.discover_declared_models, which returns a set[str] and enforces
# nothing. P003 died on the missing import; this is the other half of the port,
# and the half that is easy to drop silently. Every agent and sub-agent in a
# submission must declare the same model, so losing this check would let a
# bundle with two models reach the GPU and fail there instead of here.


def test_single_declared_model_returns_the_one_model():
    assert sr._single_declared_model({"gemma-4-31b-it-qat-w4a16-ct"}) == "gemma-4-31b-it-qat-w4a16-ct"


def test_single_declared_model_rejects_an_empty_set():
    try:
        sr._single_declared_model(set())
    except SystemExit as exc:
        assert "no model" in str(exc).lower(), exc
    else:
        raise AssertionError("an empty declaration set must not be accepted")


def test_single_declared_model_rejects_more_than_one_and_names_them():
    try:
        sr._single_declared_model({"model-b", "model-a"})
    except SystemExit as exc:
        msg = str(exc)
        assert "model-a" in msg and "model-b" in msg, msg
    else:
        raise AssertionError("two declared models must not be accepted")


def test_single_declared_model_accepts_any_iterable_order():
    """discover_declared_models returns a set, whose iteration order is arbitrary."""
    assert sr._single_declared_model({"only"}) == "only"
    assert sr._single_declared_model(["only"]) == "only"


# --- startup-failure handling (P009, 2026-10-21) ---------------------------
# P009 lost a whole session to two defects that compounded. The weight load from
# /kaggle/input took 1059 s against a 90 s baseline on 2026-10-01, so the server
# missed its 1200 s readiness deadline; start_server then retried, because the
# retry's only guard was "were extra args passed". But a readiness timeout
# leaves the first vLLM's memory on the GPUs (15.1 of 22.03 GiB free, then 1.31),
# so every later attempt in that session failed instantly. Zero rows.


def test_retry_fires_for_a_fast_failure_with_extra_args():
    """A rejected CLI flag is the case the retry exists for: it fails in seconds."""
    assert sr._should_retry_without_extra_args(
        ["--enable-prefix-caching"], "unrecognized arguments: --enable-prefix-caching", 7.0
    )


def test_no_retry_when_no_extra_args_were_passed():
    assert not sr._should_retry_without_extra_args([], "boom", 5.0)


def test_no_retry_after_a_readiness_timeout():
    """The GPUs still hold the dead server's weights, so a retry cannot succeed."""
    assert not sr._should_retry_without_extra_args(
        ["--enable-prefix-caching"],
        "Inference server did not become healthy within 1200s.",
        1200.0,
    )


def test_no_retry_once_the_attempt_ran_long_enough_to_touch_the_gpus():
    """Arg parsing fails before any weight is read; a slow failure did not."""
    assert not sr._should_retry_without_extra_args(
        ["--enable-prefix-caching"], "some other error", 600.0
    )


def test_startup_timeout_default_accommodates_the_observed_slow_load():
    """1059 s of weight load + compile/profile overran the old 1200 s default."""
    assert sr._startup_timeout_s({}) >= 1059 + 600


def test_startup_timeout_is_overridable_from_the_runspec():
    assert sr._startup_timeout_s({"startup_timeout_s": 900}) == 900
