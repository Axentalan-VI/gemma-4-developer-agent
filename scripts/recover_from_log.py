"""Rebuild ledger rows from a kernel log, for runs whose output was lost.

    python scripts/recover_from_log.py --log ledger/incoming/probe.log --run-id probe_c12

A cancelled Kaggle kernel discards `/kaggle/working` entirely: the ledger, the
patches and the harness results all go with it. We learned that the expensive
way -- a run that had already started vLLM and reached the agent loop was
cancelled after ~47 GPU-minutes, and the only surviving record was the log text
visible in the browser.

So `session_runner.py` now echoes every ledger row to stdout behind
`LEDGER_ROW `, and this reads them back. The log is the backup ledger.

It also extracts what the *failures* say, which for a lost run is often the
whole value: the first real run produced no ledger at all but its traceback
identified a bug in the public bundle.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swegemma_lab.ledger import LEDGER_NAME, Row  # noqa: E402

ROW_MARKER = "LEDGER_ROW "

#: Failure signatures worth counting even when no row was written. Each is a
#: mechanism, not a symptom, so the count answers "how often does this happen".
SIGNATURES = (
    (
        "context_window_exceeded",
        re.compile(r"ContextWindowExceededError|maximum context length is"),
        "input + max_output_tokens exceeded max_model_len. NON-RETRYABLE: the "
        "task is lost outright. Check the sampling config's output budget "
        "against the worst-case prompt, not the typical one.",
    ),
    (
        "sandbox_no_pip",
        re.compile(r"ensurepip unavailable in sandbox"),
        "the per-task venv has no pip, so nothing can install into it at "
        "runtime. Any prompt text suggesting `pip install` is dead weight.",
    ),
    (
        "rate_or_conn",
        re.compile(r"RateLimitError|APIConnectionError|APITimeoutError"),
        "transport-level; these are retryable and usually benign.",
    ),
    (
        "tool_parse",
        re.compile(r"tool_call_parser|Failed to parse tool call"),
        "the served parser did not recognise the model's tool-call format.",
    ),
    (
        "oom",
        re.compile(r"CUDA out of memory|torch\.OutOfMemoryError"),
        "vLLM ran out of VRAM; reduce max_num_seqs or max_model_len.",
    ),
)

TASK_ERROR = re.compile(r"Error during sandbox execution for task (\S+)")


def parse_rows(text: str) -> list[Row]:
    known = set(Row.__dataclass_fields__)
    out: list[Row] = []
    for line in text.splitlines():
        idx = line.find(ROW_MARKER)
        if idx < 0:
            continue
        try:
            raw = json.loads(line[idx + len(ROW_MARKER):])
        except json.JSONDecodeError:
            continue
        if isinstance(raw, dict) and "instance_id" in raw:
            out.append(Row(**{k: v for k, v in raw.items() if k in known}))
    return out


def diagnose(text: str) -> str:
    lines: list[str] = []
    failed = TASK_ERROR.findall(text)
    if failed:
        uniq = sorted(set(failed))
        lines.append(f"Tasks that raised in the sandbox: {len(uniq)}")
        for t in uniq[:20]:
            lines.append(f"    {t}")
        if len(uniq) > 20:
            lines.append(f"    ... and {len(uniq) - 20} more")
        lines.append("")

    counts = Counter()
    for name, pattern, _ in SIGNATURES:
        n = len(pattern.findall(text))
        if n:
            counts[name] = n
    if counts:
        lines.append("Failure signatures:")
        for name, pattern, explain in SIGNATURES:
            if name in counts:
                lines.append(f"  {counts[name]:4d}x  {name}")
                lines.append(f"          {explain}")
    if not lines:
        lines.append("No known failure signatures found.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--log", required=True, help="kernel log text (saved or pasted)")
    ap.add_argument("--run-id", help="run_id to file the rows under; default from the rows")
    ap.add_argument("--ledger", default=str(ROOT / "ledger"))
    ap.add_argument("--write", action="store_true", help="actually write the ledger file")
    args = ap.parse_args(argv)

    text = Path(args.log).read_text(encoding="utf-8", errors="replace")
    rows = parse_rows(text)

    print(f"{len(rows)} ledger row(s) recovered from {args.log}")
    print()
    print(diagnose(text))

    if not rows:
        print()
        print("No LEDGER_ROW lines. Either the run predates row echoing, or it")
        print("died before finishing a single task. The diagnosis above is then")
        print("the only thing the run produced -- which can still be the most")
        print("valuable part of it.")
        return 0

    run_id = args.run_id or rows[0].run_id
    dest = Path(args.ledger) / "runs" / run_id / LEDGER_NAME
    print()
    print(f"-> {dest}")
    for r in rows[:5]:
        print(f"   {r.instance_id:24s} resolved={r.resolved} calls={r.tool_calls_used} "
              f"patch={r.patch_bytes}B gold_hit={r.gold_hit}")
    if len(rows) > 5:
        print(f"   ... {len(rows) - 5} more")

    if not args.write:
        print()
        print("Dry run. Pass --write to create the ledger file.")
        return 0

    if dest.exists():
        print(f"refusing to overwrite an existing ledger at {dest}")
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(r.to_json() + "\n")
    print(f"wrote {len(rows)} row(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
