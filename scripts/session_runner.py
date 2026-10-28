"""Run one bundle over a task list on Kaggle, resumably, inside a session cap.

This is the only script that spends GPU quota, so it is built around three
constraints:

- **45 GPU-hours a week** on this account (not the 30 in Kaggle's public docs;
  `kaggle quota` is the source of truth). `Evaluator.run()` already has a semaphore worker
  pool, so concurrency is free to use; the wins come from vLLM prefix caching
  (every task shares the system prompt and every turn re-sends the growing
  conversation) and from not re-paying setup per task.
- **A 9-12 hour session cap with no warning.** The harness appends each finished
  task to `task_results.jsonl` as it lands, so resume is a set difference. We
  run in chunks and stop launching while there is still time for in-flight work
  to be written.
- **Comparisons must pool across runs.** Every row carries the `bundle_hash`, so
  repeated runs of one configuration accumulate and a candidate measured against
  an existing k=4 reference costs one run rather than five.

Driven by `runspec.json` from the lab dataset, so a new experiment is a dataset
version bump plus a re-run of the same kernel -- no notebook edits, no drift.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for cand in (REPO / "src", Path("/kaggle/input/datasets/ahmedsherif382/swegemma-lab/src")):
    if cand.is_dir():
        sys.path.insert(0, str(cand))

COMPETITION_MODEL = "gemma-4-31b-it-qat-w4a16-ct"

#: Context management the *grader* uses (HARNESS_README section 7.2). The public
#: starter notebook ships compaction_interval=15 instead; we match the grader,
#: because a measurement taken under different context management is measuring a
#: different agent.
COMPACTION = dict(compaction_interval=5, overlap_size=2, token_threshold=14336, event_retention_size=5)
CACHE = dict(min_tokens=2048, ttl_seconds=1800, cache_intervals=10)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


#: Prefix for a ledger row echoed to stdout.
#:
#: The log is the ONLY artifact that survives a cancelled Kaggle kernel --
#: /kaggle/working is discarded, so the ledger, the patches and the results all
#: go with it. We learned that by losing a run that had already served requests
#: and reached the agent loop. So every row is also printed here, unprefixed by
#: a timestamp so it parses as JSON, and `scripts/recover_from_log.py` rebuilds
#: a ledger from log text pasted out of the browser.
ROW_MARKER = "LEDGER_ROW "


def emit_row(row) -> None:
    print(ROW_MARKER + row.to_json(), flush=True)


def load_runspec(path: Path | None) -> dict:
    spec = {
        "variant": "v00_public_baseline",
        "seed": 1001,
        "concurrency": 12,
        "task_list": "all_ids.txt",
        "deadline_minutes": 480,
        "reserve_minutes": 45,
        "chunk_size": 12,
        "prefix_caching": False,
        "max_time_minutes": 180,
        "max_num_seqs": 32,
        "max_model_len": 32768,
        "max_tool_calls": 100,
        # --- surrogate mode ------------------------------------------------
        # A small model served under the competition's model name, so the whole
        # pipeline -- bundle, ADK agent graph, tool loop, patch extraction,
        # ledger -- can be exercised on hardware that cannot host a 31B.
        # start_server already aliases the declared name onto whatever is
        # served, so the BUNDLE STAYS BYTE-IDENTICAL and still validates; only
        # the weights behind the alias change.
        #
        # A surrogate run answers "does the agent produce a patch at all",
        # which is still unanswered. It answers NOTHING about score, and every
        # row it writes is marked so it can never pool with a real run.
        "surrogate": False,
        "tool_call_parser": "gemma4",
        "reasoning_parser": "gemma4",
        "enable_thinking": True,
    }
    if path and path.is_file():
        spec.update(json.loads(path.read_text(encoding="utf-8")))
    return spec


def already_done(results_dir: Path) -> set[str]:
    """instance_ids the harness has already written for this results dir."""
    f = results_dir / "task_results.jsonl"
    done: set[str] = set()
    if not f.is_file():
        return done
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # torn final line from a hard kill
        iid = row.get("instance_id") or row.get("id")
        if iid:
            done.add(iid)
    return done


def _single_declared_model(models) -> str:
    """Enforce that a submission declares exactly one model, and return it.

    This check used to belong to the harness. The competition republished the
    wheelhouse on 2026-10-09 and replaced
    `swegemma.models.discovery.validate_single_declared_model` -- which both
    discovered the model and asserted there was exactly one -- with
    `adk_submission.discover_declared_models`, which returns a `set[str]` and
    asserts nothing. Run P003 died on the missing import; this function is the
    other half of that port, and the half that is easy to drop silently.

    It matters because every agent and sub-agent must declare
    `gemma-4-31b-it-qat-w4a16-ct`. Without this, a bundle declaring two models
    would reach the GPU and fail there, after the allocation is committed,
    instead of failing here for free.
    """
    names = sorted(models)
    if not names:
        raise SystemExit(
            "bundle declares no model; every agent config needs a `model:` key "
            f"naming {COMPETITION_MODEL}"
        )
    if len(names) > 1:
        raise SystemExit(
            "bundle declares more than one model, which the competition forbids: "
            + ", ".join(repr(n) for n in names)
        )
    return names[0]


# vLLM rejects an unknown CLI flag during argument parsing, before it opens a
# single checkpoint shard, so a flag failure is always fast. Anything slower got
# far enough to claim GPU memory, and a killed server does not give it back:
# P009's retry saw 15.1 of 22.03 GiB free, then 1.31, and failed instantly four
# times over. Treat "slow" as disqualifying rather than trying to enumerate the
# failure modes.
_FLAG_FAILURE_MAX_SECONDS = 120.0


def _should_retry_without_extra_args(extra, message: str, elapsed_s: float) -> bool:
    """Is a second start attempt worth a slice of the session?

    Only when optional flags were passed AND the failure is consistent with one
    of them being rejected. A readiness timeout is never retried: the GPUs still
    hold the dead engine's weights, so the retry is guaranteed to fail and it
    costs the rest of the run.
    """
    if not extra:
        return False
    if "did not become healthy" in message:
        return False
    return elapsed_s <= _FLAG_FAILURE_MAX_SECONDS


def _startup_timeout_s(spec: dict) -> int:
    """Seconds to wait for vLLM to report healthy.

    The default was 20 min until P009, where reading the one safetensors shard
    out of /kaggle/input took 1059 s -- 11.8x the 89.78 s measured on
    2026-10-01 -- and the deadline expired mid-compile. The read rate is
    Kaggle's, not ours, and nothing pins it, so leave headroom: a start that
    waits is recoverable, a start that is killed poisons the session.
    """
    return int(spec.get("startup_timeout_s", 60 * 45))


def start_server(bundle: Path, model_path: Path, spec: dict):
    import torch
    from adk_submission import (
        VllmConfig,
        VllmServer,
        discover_adapters,
        discover_declared_models,
    )
    from swegemma.config import ALLOWED_ADAPTER_EXTENSIONS

    declared = _single_declared_model(discover_declared_models(str(bundle)))
    adapters = discover_adapters(str(bundle), adapter_extensions=ALLOWED_ADAPTER_EXTENSIONS)
    n_adapters = len(getattr(adapters, "adapters", None) or getattr(adapters, "entries", None) or [])
    log(f"declared model {declared!r}; {n_adapters} adapter(s) discovered")

    gpus = torch.cuda.device_count() if torch.cuda.is_available() else 1
    tp = 4 if gpus >= 4 else (2 if gpus >= 2 else 1)

    extra: list[str] = []

    # vLLM warms up the sampler with max_num_seqs dummy requests at startup. The
    # default (256) OOMs a 31B W4A16 model on 4xL4 even at 0.90 utilization:
    #   CUDA out of memory occurred when warming up sampler with 256 dummy requests
    # And 256 was never reachable anyway -- the engine reports a 55,616-token KV
    # cache, i.e. max concurrency 10.49x at 32k context. Cap it near the real
    # ceiling and a little above our task concurrency.
    extra += ["--max-num-seqs", str(spec.get("max_num_seqs", 32))]

    if spec.get("prefix_caching", False):
        # Prefix caching is what stops every turn re-prefilling the whole
        # conversation instead of just the new suffix. The wheelhouse ships vLLM
        # 0.19.1, where the V1 engine enables it by DEFAULT, so passing the flag
        # is probably redundant -- and if the flag has been retired it would fail
        # startup and cost quota. Hence: off by default, opt in via runspec, and
        # start_server falls back to no extra args if startup fails.
        extra.append("--enable-prefix-caching")
    extra += list(spec.get("vllm_extra_args") or [])

    cfg = VllmConfig(
        model=str(model_path),
        port=8000,
        host="127.0.0.1",
        # Overridable only so a surrogate model can be served: a non-Gemma
        # model emits tool calls in its own format and the gemma4 parser will
        # silently fail to extract any, which looks exactly like an agent that
        # never calls a tool.
        tool_call_parser=str(spec.get("tool_call_parser", "gemma4")),
        reasoning_parser=str(spec.get("reasoning_parser", "gemma4")),
        default_chat_template_kwargs={"enable_thinking": bool(spec.get("enable_thinking", True))},
        # 32768 matches the grader, but smaller hardware cannot hold that much KV
        # cache: 2xT4 fits only ~9k tokens. A reduced context makes the run a
        # pipeline test, NOT a measurement comparable to the leaderboard.
        max_model_len=int(spec.get("max_model_len", 32768)),
        dtype="bfloat16" if (torch.cuda.is_available() and torch.cuda.is_bf16_supported()) else "auto",
        gpu_memory_utilization=float(spec.get("gpu_memory_utilization", 0.90)),
        enable_auto_tool_choice=True,
        # LoRA serving costs throughput; only pay for it when an adapter exists.
        enable_lora=n_adapters > 0,
        max_loras=8,
        max_lora_rank=128,
        tensor_parallel_size=tp,
        startup_timeout=_startup_timeout_s(spec),
        extra_args=extra,
    )
    mml = int(spec.get("max_model_len", 32768))
    if mml != 32768:
        log(f"WARNING max_model_len={mml} != the grader's 32768; this run is a "
            "pipeline test, not a comparable measurement")
    if spec.get("surrogate"):
        log("=" * 72)
        log("SURROGATE RUN: the weights behind " + COMPETITION_MODEL + " are NOT")
        log(f"  the competition model. Serving: {model_path}")
        log("  Every ledger row is marked surrogate=True and is excluded from")
        log("  pooling. This run can show that the pipeline produces a patch.")
        log("  It can say NOTHING about resolution rate or localization.")
        log("=" * 72)
    log(f"starting vLLM tp={tp} gpus={gpus} max_model_len={mml} extra={extra}")
    server = VllmServer(cfg, adapter_manifest=adapters)
    t_start = time.time()
    try:
        server.start()
    except Exception as exc:
        elapsed = time.time() - t_start
        if not _should_retry_without_extra_args(extra, str(exc), elapsed):
            log(f"vLLM failed to start after {elapsed / 60:.1f} min and a retry would "
                f"inherit the dead engine's GPU memory; not retrying ({exc})")
            raise
        # An unrecognised CLI flag must not cost a whole session. Retry with only
        # --max-num-seqs, which is not optional: without it startup OOMs.
        log(f"vLLM failed to start in {elapsed:.0f}s with extra args ({exc}); "
            "retrying with only --max-num-seqs")
        from dataclasses import replace

        minimal = ["--max-num-seqs", str(spec.get("max_num_seqs", 32))]
        server = VllmServer(replace(cfg, extra_args=minimal), adapter_manifest=adapters)
        server.start()
    log(f"vLLM up at {server.base_url}")
    models = server.create_model_registry(
        aliases=[declared, COMPETITION_MODEL], model_prefix="openai/", api_key="EMPTY"
    )
    return server, models, adapters


def build_config(bundle: Path, data: Path, results: Path, models, adapters, spec: dict):
    from google.adk.agents.context_cache_config import ContextCacheConfig
    from google.adk.apps._configs import EventsCompactionConfig
    from swegemma.config import EvalConfig, build_submission_limits

    limits, gen = build_submission_limits()
    return EvalConfig(
        tasks_path=data / "tasks.jsonl",
        snapshots_dir=data / "snapshots",
        results_dir=results,
        submission_dir=bundle,
        models=models,
        sandbox="subprocess",  # no Docker daemon on Kaggle
        wheels_dir=data / "wheels",
        graph_dir=str(data / "graphs"),
        embeddings_dir=str(data / "embeddings"),
        limits=limits,
        generation_constraints=gen,
        adapter_manifest=adapters,
        context_cache_config=ContextCacheConfig(**CACHE),
        events_compaction_config=EventsCompactionConfig(**COMPACTION),
        # Measurement budgets, deliberately NOT the scored ones. Tool calls are
        # contention-independent so we keep the real ceiling of 100; wall-clock
        # is effectively disabled, because under concurrency a slow task would
        # otherwise fail for CPU contention rather than for anything about the
        # config under test, making runs non-comparable.
        max_tool_calls=int(spec.get("max_tool_calls", 100)),
        max_time_minutes=float(spec.get("max_time_minutes", 180)),
        timeout_seconds=300,
        concurrency=int(spec.get("concurrency", 12)),
        display_mode="quiet",
        verbose=False,
    )


def disk_free_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / 1024**3


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lab", default="/kaggle/input/datasets/ahmedsherif382/swegemma-lab")
    ap.add_argument("--data", default="/kaggle/input/competitions/gemma-4-developer-agent")
    ap.add_argument("--model-path", default="/kaggle/input/models/google/gemma-4/other/gemma-4-31b-it-qat-w4a16-ct/2")
    ap.add_argument("--results", default="/kaggle/working/results")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--variant", default=None, help="override runspec")
    ap.add_argument("--concurrency", type=int, default=None)
    ap.add_argument("--limit", type=int, default=None, help="first N tasks only (probes)")
    ap.add_argument("--max-time-minutes", type=float, default=None,
                    help="override the per-task wall budget; probes must cap this or one "
                         "task can occupy the whole session")
    ap.add_argument("--max-tool-calls", type=int, default=None, help="override the per-task call budget")
    ap.add_argument("--task-list", default=None, help="override runspec task_list")
    ap.add_argument("--max-model-len", type=int, default=None,
                    help="override vLLM max_model_len; must shrink on hardware that cannot "
                         "hold 32768 tokens of KV cache (e.g. 8192 on 2xT4)")
    ap.add_argument("--gpu-memory-utilization", type=float, default=None)
    ap.add_argument("--surrogate", action="store_true",
                    help="the model at --model-path is NOT the competition model. Marks every "
                         "ledger row so it can never pool with a real run. For exercising the "
                         "pipeline on hardware that cannot host a 31B.")
    ap.add_argument("--tool-call-parser", default=None,
                    help="vLLM tool-call parser; a non-Gemma surrogate needs its own (e.g. hermes)")
    ap.add_argument("--reasoning-parser", default=None)
    ap.add_argument("--allow-missing-test-deps", action="store_true",
                    help="run even though inline_snapshot/dirty_equals are absent. Accepts a "
                         "known under-report: probe_c12 lost 5 of 12 tasks to pytest collection "
                         "errors from exactly these two packages.")
    ap.add_argument("--dry-run", action="store_true", help="resolve everything, start no server")
    args = ap.parse_args(argv)

    lab, data = Path(args.lab), Path(args.data)
    spec = load_runspec(lab / "runspec.json")
    if args.variant:
        spec["variant"] = args.variant
    if args.concurrency:
        spec["concurrency"] = args.concurrency
    if args.max_time_minutes is not None:
        spec["max_time_minutes"] = args.max_time_minutes
    if args.max_tool_calls is not None:
        spec["max_tool_calls"] = args.max_tool_calls
    if args.task_list:
        spec["task_list"] = args.task_list
    if args.max_model_len is not None:
        spec["max_model_len"] = args.max_model_len
    if args.surrogate:
        spec["surrogate"] = True
    if args.tool_call_parser is not None:
        spec["tool_call_parser"] = args.tool_call_parser
    if args.reasoning_parser is not None:
        spec["reasoning_parser"] = args.reasoning_parser
    # A non-default parser without --surrogate means the competition model is
    # being served through a parser it does not speak, which produces zero tool
    # calls and looks like a model that refuses to act. Refuse instead.
    if spec.get("tool_call_parser") != "gemma4" and not spec.get("surrogate"):
        log(f"FATAL tool_call_parser={spec['tool_call_parser']!r} without --surrogate; "
            "the competition model speaks gemma4")
        return 2
    if args.gpu_memory_utilization is not None:
        spec["gpu_memory_utilization"] = args.gpu_memory_utilization

    run_id = args.run_id or f"{spec['variant']}_s{spec['seed']}_{time.strftime('%m%d_%H%M')}"
    results = Path(args.results) / run_id
    results.mkdir(parents=True, exist_ok=True)
    log(f"run_id {run_id}")
    log(f"runspec {json.dumps(spec, sort_keys=True)}")

    bundle = lab / "bundles" / spec["variant"]
    if not bundle.is_dir():
        log(f"FATAL no bundle at {bundle}")
        return 2
    if (bundle / "MANIFEST.yaml").is_file():
        # MANIFEST is lab metadata that the builder strips, so its presence means
        # this is an authoring directory, not a built bundle. Hashing it would
        # produce a bundle_hash that never matches the one we submit, and the
        # ledger pools on that hash -- so these runs would silently fail to
        # compare against anything. Point --lab at a push_dataset staging dir.
        log(f"FATAL {bundle} looks like a source bundle (MANIFEST.yaml present), not a built one")
        return 3

    # Validate before spending a single GPU-second.
    from swegemma_lab.build import compute_bundle_hash
    from swegemma_lab.validate import validate_bundle

    report = validate_bundle(bundle)
    log(report.render())
    if not report.ok:
        log("FATAL bundle has validator errors; refusing to spend quota")
        return 3
    bundle_hash = compute_bundle_hash(bundle)
    log(f"bundle_hash {bundle_hash}")
    expected = (spec.get("bundle_hashes") or {}).get(spec["variant"])
    if expected and expected != bundle_hash:
        log(f"FATAL hash mismatch: runspec says {expected}, bundle is {bundle_hash}")
        return 3

    # Refuse to spend quota on a run whose test environment will under-report.
    #
    # MEASURED, probe_c12: five of twelve tasks failed pytest collection with
    # `ModuleNotFoundError: No module named 'dirty_equals'` or
    # `'inline_snapshot'` -- the exact two packages the C004 calibration
    # identified, which moved clean-N from 71 to 102. One of them
    # (fastapi_14262) had touched the gold file, so it is a plausible false
    # negative: scored a failure for an environment reason.
    #
    # The sandbox cannot fix this itself. Its venv is built WITHOUT pip --
    # "ensurepip unavailable in sandbox, creating venv without pip" appeared
    # twelve times in that run, once per task -- so install_test_dependencies
    # has nothing to install with. The packages have to be present in the
    # interpreter the sandbox inherits, which means staging them BEFORE the
    # eval, exactly as the calibration notebook does. session_runner never did.
    missing = [m for m in ("inline_snapshot", "dirty_equals")
               if importlib.util.find_spec(m) is None]
    if missing and not args.allow_missing_test_deps:
        log(f"FATAL test-only packages not importable: {missing}")
        log("  Every task whose tests import them will fail COLLECTION, which")
        log("  scores as unresolved and is indistinguishable from a bad patch.")
        log("  Run scripts/stage_test_deps.py first, or pass")
        log("  --allow-missing-test-deps to measure anyway and accept the floor.")
        return 4
    if missing:
        log(f"WARNING proceeding without {missing}; resolution WILL be under-reported")

    task_file = lab / "tasks" / spec["task_list"]
    if not task_file.is_file():
        log(f"FATAL no task list at {task_file}")
        return 2
    want = [t.strip() for t in task_file.read_text(encoding="utf-8").splitlines() if t.strip()]
    if args.limit:
        want = want[: args.limit]
    done = already_done(results)
    todo = [t for t in want if t not in done]
    log(f"task list {spec['task_list']}: {len(want)} wanted, {len(done)} already done, {len(todo)} to run")
    if not todo:
        log("nothing to do")
        return 0
    if args.dry_run:
        log("--dry-run: stopping before vLLM")
        return 0

    server, models, adapters = start_server(bundle, Path(args.model_path), spec)
    try:
        from swegemma.evaluate import Evaluator

        config = build_config(bundle, data, results, models, adapters, spec)
        deadline = time.monotonic() + max(
            0.0, (spec["deadline_minutes"] - spec["reserve_minutes"]) * 60
        )
        chunk = max(1, int(spec.get("chunk_size", spec.get("concurrency", 12))))

        # Ledger opened BEFORE the first chunk, not after the last one. The
        # previous version wrote everything at the end, so a cancelled session
        # lost a run that had already reached the agent loop.
        from swegemma_lab.ledger import Ledger, Row
        from swegemma_lab.metrics import build_panel, budget_verdict, gold_overlap, load_outcomes
        from swegemma_lab.tasks import load_tasks

        led = Ledger(Path(args.results).parent / "ledger", run_id)
        led.write_runspec({**spec, "run_id": run_id, "bundle_hash": bundle_hash})
        tasks = {t.instance_id: t for t in load_tasks(data / "tasks.jsonl")}
        laddered: set[str] = set()

        def flush_ledger() -> int:
            """Bank every finished task not yet written. Safe to call repeatedly.

            Called after each chunk and again in `finally`, so the furthest a
            hard kill can set us back is one chunk rather than one session.
            """
            written = 0
            for o in load_outcomes(results):
                if o.instance_id in laddered:
                    continue
                hit, exact = gold_overlap(o, tasks.get(o.instance_id))
                row = Row(
                    run_id=run_id,
                    variant=spec["variant"],
                    bundle_hash=bundle_hash,
                    seed=int(spec["seed"]),
                    concurrency=int(spec["concurrency"]),
                    instance_id=o.instance_id,
                    resolved=o.resolved,
                    error=o.error,
                    tool_calls_used=o.tool_calls_used,
                    wall_seconds=o.wall_seconds,
                    patch_bytes=len(o.patch),
                    task_list=spec["task_list"],
                    gold_hit=hit,
                    gold_exact=exact,
                    files_touched=len(o.files),
                    surrogate=bool(spec.get("surrogate")),
                    model_served=str(args.model_path) if spec.get("surrogate") else "",
                    max_tool_calls=int(spec.get("max_tool_calls") or 0),
                    max_model_len=int(spec.get("max_model_len") or 0),
                )
                led.append(row)
                emit_row(row)
                laddered.add(o.instance_id)
                written += 1
            return written

        launched = 0
        try:
            for i in range(0, len(todo), chunk):
                if time.monotonic() >= deadline:
                    log(f"deadline guard: stopping with {len(todo) - launched} task(s) unrun; resume this run_id")
                    break
                free = disk_free_gb(Path("/kaggle/working"))
                if free < 10:
                    log(f"disk guard: only {free:.1f} GB free; stopping")
                    break
                batch = todo[i : i + chunk]
                config.task_ids = batch
                log(f"chunk {i // chunk + 1}: {len(batch)} tasks, {free:.0f} GB free")
                asyncio.run(Evaluator(config).run())
                launched += len(batch)
                n = flush_ledger()
                log(f"chunk {i // chunk + 1} banked {n} row(s); {len(laddered)} total")
        finally:
            # A crash mid-chunk still banks whatever the harness finished.
            flush_ledger()

        log(f"finished: {len(laddered)} task(s) banked from {results}")
        outcomes = load_outcomes(results)

        # Pass the ceiling the run ACTUALLY used. Rendering probe_c12 against
        # the default 100 while it ran at 30 inverted the budget verdict.
        ceiling = int(spec.get("max_tool_calls") or 100)
        panel = build_panel(run_id, outcomes, tasks, call_ceiling=ceiling)
        print()
        print(panel.render())
        print()
        print(budget_verdict(panel, call_ceiling=ceiling))
        return 0
    finally:
        try:
            server.stop()
            log("vLLM stopped")
        except Exception as exc:  # never mask a real failure with a teardown error
            log(f"server.stop() raised: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
