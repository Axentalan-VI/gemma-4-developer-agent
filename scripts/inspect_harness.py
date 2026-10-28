"""Answer the load-bearing unknowns by reading the harness source. No GPU.

Every question below would otherwise cost GPU-hours of black-box probing at one
submission per day. The trick that makes this free is to never *import* the
harness: vLLM needs CUDA, so we locate the installed packages and read their
`.py` files as text.

Run inside a Kaggle notebook with the wheelhouse installed, accelerator None.
Writes findings to `--out` and prints the excerpts that matter.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from pathlib import Path

PACKAGES = ("swegemma", "adk_submission", "adk_eval_core", "google.adk")

#: (question id, human question, regex patterns to hunt for). Each pattern is
#: matched per line with a few lines of context, so we read the real code rather
#: than trusting the README's prose.
QUESTIONS: list[tuple[str, str, list[str]]] = [
    (
        "max_turns",
        "What is the DEFAULT max_turns / max_llm_calls, and is it lower than max_tool_calls=100? "
        "If turns are the real ceiling, raising them in eval_config.yaml is the cheapest win available.",
        [r"max_turns", r"max_llm_calls", r"max_loop_iterations", r"SWE_MAX_TURNS"],
    ),
    (
        "budget_ceiling",
        "Can eval_config.yaml RAISE max_time_minutes / max_tool_calls above 60/100, or are they clamped down?",
        [r"load_submission_eval_config", r"min\(.*max_tool_calls", r"min\(.*time_minutes", r"clamp", r"\bcap\b"],
    ),
    (
        "subagent_tool_accounting",
        "Do sub-agent tool calls consume the parent's 100-call budget? Decides whether a multi-specialist "
        "topology is affordable.",
        [r"budget_gated", r"count_tool_call", r"tool_calls_used", r"def _consume", r"increment"],
    ),
    (
        "wall_clock_accounting",
        "Does run_command execution time count against the 60-minute wall budget? If yes, a verify-repair "
        "loop is far more expensive than it looks.",
        [r"remaining_time_seconds", r"agent_start_time", r"start_agent_session", r"elapsed"],
    ),
    (
        "skills_loaded",
        "Does the harness actually compile and load skills/ from the submission?",
        [r"SkillRegistry", r"SKILL\.md", r"\bskills\b"],
    ),
    (
        "hints_injection",
        "Is hints_text injected into the prompt? Empty in all 129 public tasks, but possibly present privately.",
        [r"hints_text", r"\bhints\b"],
    ),
    (
        "seed_plumbing",
        "Is `seed` passed through ADK to vLLM? If not, nothing may depend on run-to-run determinism.",
        [r"\bseed\b"],
    ),
    (
        "include_traversal",
        "Does the !include loader reject '..' outright, or only escapes from the bundle root? The public "
        "bundle that scored 0.15 uses '../prompts/analyzer.md', so the README's prose looks wrong.",
        [r"PathTraversalError", r"\.\.", r"resolve\(\)", r"relative_to"],
    ),
    (
        "loop_exit",
        "Does the declarative YAML support a loop exit / escalate so a LoopAgent can stop early?",
        [r"escalate", r"exit_loop", r"max_iterations", r"LoopAgent"],
    ),
    (
        "nudge_and_termination",
        "Exact nudge text and termination conditions, including the 3-turns-without-a-tool-call rule.",
        [r"max_nudges", r"consecutive_nudges", r"nudge_prompt"],
    ),
    (
        "required_tests",
        "With FAIL_TO_PASS absent from the public tasks, how are required test nodes derived from test_patch?",
        [r"FAIL_TO_PASS", r"PASS_TO_PASS", r"_validate_junit", r"required", r"junit"],
    ),
    (
        "sandbox_reuse",
        "Can the sandbox reuse a pre-extracted snapshot or a shared per-repo venv? Decides whether a full "
        "129-task run costs 3 GPU-hours or 25.",
        [r"reuse_containers", r"extract_snapshot", r"venv", r"--system-site-packages", r"find_links"],
    ),
]


def find_package_dirs() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for name in PACKAGES:
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ModuleNotFoundError, ValueError):
            continue
        if spec is None:
            continue
        paths = list(spec.submodule_search_locations or [])
        if paths:
            found[name] = Path(paths[0])
        elif spec.origin:
            found[name] = Path(spec.origin).parent
    return found


def iter_sources(dirs: dict[str, Path]):
    for pkg, d in dirs.items():
        for p in sorted(d.rglob("*.py")):
            try:
                yield pkg, p, p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue


def saved_name(pkg: str, path: Path, base: Path) -> str:
    """Flatten a package path into a unique filename.

    The first version used `f'{pkg}__{path.name}'`, which silently lost 129 of
    642 files to basename collisions -- google.adk alone has dozens of
    `__init__.py` and `base_agent.py` under different subpackages. Encoding the
    whole relative path keeps every file.
    """
    try:
        rel = path.relative_to(base)
    except ValueError:
        rel = Path(path.name)
    return f"{pkg}__" + "__".join(rel.parts)


def hunt(sources, patterns: list[str], context: int = 3, limit: int = 40):
    """Return (relpath, lineno, excerpt) for lines matching any pattern."""
    compiled = [re.compile(p) for p in patterns]
    hits = []
    for pkg, path, text in sources:
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if any(c.search(line) for c in compiled):
                lo = max(0, i - context)
                hi = min(len(lines), i + context + 1)
                excerpt = "\n".join(f"{n + 1:5d}| {lines[n]}" for n in range(lo, hi))
                hits.append((f"{pkg}/{path.name}", i + 1, excerpt))
                if len(hits) >= limit:
                    return hits
    return hits


def dump_defaults(dirs: dict[str, Path]) -> dict[str, list[str]]:
    """Pull out assignment lines that look like budget/limit defaults."""
    wanted = re.compile(
        r"^\s*(max_\w+|timeout\w*|\w*_timeout\w*|\w*budget\w*|command_timeout\w*|"
        r"compaction\w*|token_threshold|event_retention\w*)\s*[:=]\s*(.+)$"
    )
    out: dict[str, list[str]] = {}
    for pkg, path, text in iter_sources(dirs):
        for i, line in enumerate(text.splitlines(), 1):
            m = wanted.match(line)
            if m and "def " not in line:
                out.setdefault(f"{pkg}/{path.name}", []).append(f"{i:5d}| {line.strip()}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="harness_facts", help="directory for the full dumps")
    ap.add_argument("--context", type=int, default=3)
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    dirs = find_package_dirs()
    if not dirs:
        print("FAIL: none of the harness packages are importable. Install the wheelhouse first.")
        print("Expected any of: " + ", ".join(PACKAGES))
        return 1

    print("=" * 78)
    print("HARNESS PACKAGES")
    print("=" * 78)
    for name, d in dirs.items():
        n = len(list(d.rglob("*.py")))
        print(f"  {name:18s} {n:4d} .py files  {d}")

    # Full source archive, so later questions never need another Kaggle session.
    src_dir = out / "source"
    src_dir.mkdir(exist_ok=True)
    manifest = []
    for pkg, path, text in iter_sources(dirs):
        rel = saved_name(pkg, path, dirs[pkg])
        (src_dir / rel).write_text(text, encoding="utf-8", newline="\n")
        manifest.append({"package": pkg, "file": str(path), "saved_as": rel, "lines": text.count("\n") + 1})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="\n")
    written = len(list(src_dir.glob("*.py")))
    print(f"\nsaved {written} source files to {src_dir} ({len(manifest)} manifest entries)")
    if written != len(manifest):
        print(f"  WARNING: {len(manifest) - written} files lost to filename collisions")

    print("\n" + "=" * 78)
    print("CANDIDATE DEFAULTS (budgets, timeouts, limits)")
    print("=" * 78)
    defaults = dump_defaults(dirs)
    for file, lines in sorted(defaults.items()):
        print(f"\n-- {file}")
        for line in lines[:25]:
            print("   " + line)
    (out / "defaults.json").write_text(json.dumps(defaults, indent=2), encoding="utf-8", newline="\n")

    answers: dict[str, object] = {}
    for qid, question, patterns in QUESTIONS:
        print("\n" + "=" * 78)
        print(f"Q[{qid}] {question}")
        print("=" * 78)
        hits = hunt(iter_sources(dirs), patterns, context=args.context)
        answers[qid] = {"question": question, "patterns": patterns, "hits": hits}
        if not hits:
            print("  NO MATCHES -- treat as unanswered, do not assume either way.")
        for file, lineno, excerpt in hits[:6]:
            print(f"\n-- {file}:{lineno}")
            print(excerpt)
        if len(hits) > 6:
            print(f"\n  ... {len(hits) - 6} more hits in {out / 'answers.json'}")

    (out / "answers.json").write_text(json.dumps(answers, indent=2), encoding="utf-8", newline="\n")
    print(f"\n\nwrote {out / 'answers.json'} and {out / 'defaults.json'}")
    print("\nNEXT: transcribe each answer into README.md 'Verified harness facts'.")
    print("An unanswered question stays unanswered -- it does not become an assumption.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
