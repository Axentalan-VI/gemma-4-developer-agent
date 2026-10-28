"""Offline validation of a swegemma submission bundle.

Runs entirely on CPU with no model and no Kaggle access. Its whole purpose is to
catch the class of mistake that costs a whole submission day: a bundle that the
grader refuses to load, and therefore scores 0.00, for a reason a five-second
local check would have found.

Every rule here is traceable to `reference/HARNESS_README.md` or to an observed
community failure. See `docs/checks.md` for the mapping.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import yaml

# --- Constants taken from the harness spec -----------------------------------

#: `SubmissionLimits.allowed_file_extensions`. Pickle-based weights are rejected
#: by the harness, so anything outside this set fails validation upstream.
ALLOWED_EXTENSIONS = {".yaml", ".yml", ".md", ".txt", ".py", ".json", ".safetensors"}

#: Exactly one of these must exist at the bundle root. Verified against
#: adk_submission/discovery.py:24 `_ROOT_CONFIG_NAMES = ["agent.yaml",
#: "root_agent.yaml"]`. HARNESS_README also lists `agent.yml` / `root_agent.yml`,
#: but the loader never looks for them -- shipping `agent.yml` raises
#: MissingRootConfigError and scores 0.00.
ROOT_CONFIG_NAMES = ("agent.yaml", "root_agent.yaml")
#: Names that look like a root config but are never discovered.
ROOT_CONFIG_DECOYS = ("agent.yml", "root_agent.yml")

#: `ALLOWED_MODEL_NAMES` in scripts/inference.py.
COMPETITION_MODEL = "gemma-4-31b-it-qat-w4a16-ct"

#: The served context window, and the ADK compaction threshold inside it.
MODEL_WINDOW = 32768
COMPACTION_THRESHOLD = 14336

#: Largest input prompt actually observed, from run probe_c12 on 2026-10-06.
#: Not a guess: the analyzer sub-agent hit exactly this and the task was lost to
#: a non-retryable ContextWindowExceededError. Raise it only from measurement.
OBSERVED_PROMPT_PEAK = 24577

#: The nine tools registered by `SwegemmaContext.create_tools()`.
ALLOWED_TOOLS = frozenset(
    {
        "run_command",
        "submit_patch",
        "get_status",
        "read_file",
        "edit_file",
        "write_file",
        "get_code_neighbors",
        "search_similar_code",
        "get_code_subgraph",
    }
)

MAX_TOTAL_SIZE_BYTES = 3 * 1024**3
SIZE_WARN_BYTES = 100 * 1024**2
MAX_ADAPTERS = 8
MAX_LORA_RANK = 128
MAX_INCLUDE_DEPTH = 10

#: Session state keys the harness populates in `run_agent_sandbox`. Any other
#: single-brace token in an instruction is an ADK `.format()` KeyError waiting
#: to happen at run time.
STATE_KEYS = frozenset({"problem_description", "hints"})

#: Keys the harness sets ONLY when the task supplies them. agent_runner.py:395
#: puts `hints` in session_state just when `task.hints_text` is non-empty -- and
#: it is empty in all 129 public tasks. So a bare `{hints}` is a guaranteed
#: KeyError; it must be written `{hints?}`.
CONDITIONAL_STATE_KEYS = frozenset({"hints"})

AGENT_CLASSES = frozenset({"LlmAgent", "SequentialAgent", "ParallelAgent", "LoopAgent"})

#: Library and repo names from the four public repos. Mentioning any of them in a
#: shipped prompt is tuning on a 90%-fastapi+rich dev set against a private set
#: believed to hold different repos -- the mistake that scored 0.05.
REPO_TOKENS = (
    "fastapi",
    "starlette",
    "pydantic",
    "uvicorn",
    "anyio",
    "textualize",
    "textual",
    "renderable",
    "urllib3",
    "httpx",
    "docs_src",
)

#: Tokens for things the sandbox does not have. `rich`, `requests` and `console`
#: are ordinary English words, so they are matched only as import-like or
#: path-like usages rather than blanket substrings.
REPO_TOKENS_STRICT = (
    r"\bimport\s+rich\b",
    r"\bfrom\s+rich\b",
    r"\brich\.[a-z_]+\b",
    r"\bimport\s+requests\b",
    r"\bfrom\s+requests\b",
    r"\brequests\.[a-z_]+\b",
)

GENERIC_OK = "# generic-ok:"

#: Things the prompt must not tell the agent to do, because the sandbox cannot.
#: Matched only in command position -- backtick-quoted, at line start, or
#: followed by a flag. A blanket word match flags ordinary prose like "the
#: working tree is graded as it stands", which is a harness fact we want said.
UNREAL_PATTERNS = (
    (r"(?:`|^|\$\s)rg(?:`|\s)|\brg\s+-", "ripgrep (`rg`) is not installed in the sandbox; use `git grep -n`"),
    (r"(?:`|^|\$\s)tree(?:`|\s)|\btree\s+-", "`tree` is not installed in the sandbox"),
    (r"pip\s+install", "the sandbox is offline; pip install always fails"),
    (
        r"write_file\s*\(\s*['\"]?/tmp",
        "write_file resolves paths under /workspace and rejects /tmp; use a run_command heredoc",
    ),
    (
        r"(?:write|save|create)\s+(?:a\s+)?(?:scratch|repro\w*|temp\w*)[^\n]{0,40}?/workspace",
        "scratch files in /workspace are captured by `git diff` and ship inside the patch",
    ),
)


# --- Result model -------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    level: str  # "error" | "warn"
    check: str
    message: str
    where: str = ""

    def __str__(self) -> str:
        tag = "ERROR" if self.level == "error" else "warn "
        loc = f" [{self.where}]" if self.where else ""
        return f"{tag} {self.check}:{loc} {self.message}"


@dataclass
class Report:
    bundle: Path
    findings: list[Finding] = field(default_factory=list)
    reached: set[Path] = field(default_factory=set)
    agents: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add(self, level: str, check: str, message: str, where: str = "") -> None:
        self.findings.append(Finding(level, check, message, where))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "warn"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def render(self) -> str:
        if not self.findings:
            return f"{self.bundle.name}: PASS (no findings)"
        head = (
            f"{self.bundle.name}: {'PASS' if self.ok else 'FAIL'} "
            f"({len(self.errors)} error(s), {len(self.warnings)} warning(s))"
        )
        return "\n".join([head, *(f"  {f}" for f in self.findings)])


# --- Sandboxed !include loader ------------------------------------------------


class IncludeError(Exception):
    pass


_MISSING = object()


def _make_loader(base_dir: Path, root: Path, report: Report, depth: int, stack: tuple[Path, ...]):
    """Build a SafeLoader that resolves `!include` relative to *base_dir*.

    Path traversal, absolute paths and symlinks escaping the bundle are the
    harness's `PathTraversalError` cases; we reproduce them as findings so the
    whole bundle still gets checked instead of aborting on the first bad path.
    """

    class _Loader(yaml.SafeLoader):
        pass

    def _include(loader: yaml.SafeLoader, node: yaml.Node):
        rel = str(loader.construct_scalar(node))  # type: ignore[arg-type]
        where = f"{_rel(base_dir, root)}/<!include>" if base_dir != root else "<!include>"

        if depth >= MAX_INCLUDE_DEPTH:
            report.add("error", "include-depth", f"!include nesting exceeds {MAX_INCLUDE_DEPTH}: {rel}", where)
            return _MISSING
        if "\x00" in rel:
            report.add("error", "include-path", f"!include target contains a null byte: {rel!r}", where)
            return _MISSING
        p = PurePosixPath(rel.replace("\\", "/"))
        if p.is_absolute():
            report.add("error", "include-path", f"!include must be a relative path: {rel}", where)
            return _MISSING
        # HARNESS_README says '..' components are blocked outright, but the
        # public bundle that scored 0.12-0.15 includes `../prompts/analyzer.md`
        # from sub_agents/, and a PathTraversalError would have failed the whole
        # submission to 0.00. So the real rule is escape-from-root, which is what
        # we enforce below. Confirm against the source in the W1 harness recon.
        target = (base_dir / rel).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            report.add("error", "include-path", f"!include escapes the bundle root: {rel}", where)
            return _MISSING
        if not target.is_file():
            report.add("error", "include-missing", f"!include target does not exist: {rel}", where)
            return _MISSING
        if target in stack:
            report.add("error", "include-cycle", f"!include cycle through {rel}", where)
            return _MISSING

        report.reached.add(target)
        suffix = target.suffix.lower()
        text = target.read_text(encoding="utf-8")
        if suffix in (".md", ".txt"):
            return text
        if suffix in (".yaml", ".yml"):
            return _load_yaml(target, root, report, depth + 1, stack + (target,))
        report.add(
            "error",
            "include-type",
            f"!include only accepts .md/.txt/.yaml/.yml, got {suffix}: {rel}",
            where,
        )
        return _MISSING

    _Loader.add_constructor("!include", _include)
    return _Loader


def _load_yaml(path: Path, root: Path, report: Report, depth: int = 0, stack: tuple[Path, ...] = ()) -> Any:
    loader = _make_loader(path.parent, root, report, depth, stack or (path,))
    try:
        with path.open("r", encoding="utf-8") as fh:
            return yaml.load(fh, Loader=loader)
    except yaml.YAMLError as exc:
        report.add("error", "yaml-parse", f"unparseable YAML: {exc}", _rel(path, root))
        return _MISSING
    except UnicodeDecodeError as exc:
        report.add("error", "encoding", f"file is not valid UTF-8: {exc}", _rel(path, root))
        return _MISSING


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


# --- Individual checks --------------------------------------------------------


def _check_extensions(root: Path, report: Report) -> None:
    for p in sorted(root.rglob("*")):
        if p.is_dir():
            continue
        rel = _rel(p, root)
        if p.name == "MANIFEST.yaml" and p.parent == root:
            continue  # lab metadata, excluded by the builder
        suffix = p.suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            report.add(
                "error",
                "extension",
                f"disallowed extension {suffix or '(none)'}; the harness rejects it",
                rel,
            )
        if suffix == ".py":
            report.add(
                "warn",
                "extension",
                "a .py file is only legitimate as an ADK skill script; submissions may not ship entrypoints",
                rel,
            )
        if p.is_symlink():
            report.add("error", "symlink", "symlinks are rejected by the harness", rel)


def _check_root_config(root: Path, report: Report) -> Path | None:
    present = [n for n in ROOT_CONFIG_NAMES if (root / n).is_file()]
    for decoy in ROOT_CONFIG_DECOYS:
        if (root / decoy).is_file():
            report.add(
                "error",
                "root-config",
                f"{decoy} is never discovered by the harness (it looks only for "
                f"{', '.join(ROOT_CONFIG_NAMES)}), despite what HARNESS_README says. Rename it.",
                decoy,
            )
    if not present:
        report.add(
            "error",
            "root-config",
            f"no root config at the bundle root; expected one of {', '.join(ROOT_CONFIG_NAMES)} "
            "(MissingRootConfigError)",
        )
        return None
    if len(present) > 1:
        report.add(
            "error",
            "root-config",
            f"multiple root configs: {', '.join(present)} (MultipleRootConfigsError)",
        )
        return None
    # The classic 0.00 bug: everything nested one level down inside the zip.
    top_level_files = [p for p in root.iterdir() if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS]
    if not top_level_files:
        report.add("error", "root-config", "no files at the bundle root; did you zip the parent folder?")
    return root / present[0]


def _check_size(root: Path, report: Report) -> None:
    total = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
    if total > MAX_TOTAL_SIZE_BYTES:
        report.add("error", "size", f"unpacked size {total:,} B exceeds the 3 GiB limit")
    elif total > SIZE_WARN_BYTES:
        report.add("warn", "size", f"unpacked size {total:,} B is over 100 MiB; extraction will be slow")


def _iter_agent_nodes(cfg: Any) -> Iterable[dict[str, Any]]:
    """Yield every mapping that looks like an agent config."""
    if isinstance(cfg, dict):
        if "name" in cfg and ("model" in cfg or "agent_class" in cfg or "sub_agents" in cfg):
            yield cfg
        for v in cfg.values():
            yield from _iter_agent_nodes(v)
    elif isinstance(cfg, list):
        for v in cfg:
            yield from _iter_agent_nodes(v)


def _check_model(cfg: Any, report: Report, where: str) -> set[str]:
    models: set[str] = set()
    for node in _iter_agent_nodes(cfg):
        raw = node.get("model")
        if raw is None:
            continue
        if not isinstance(raw, str):
            report.add("error", "model", f"`model` must be a string, got {type(raw).__name__}", where)
            continue
        # normalize_model_name strips provider prefixes before comparison.
        name = raw.split("/")[-1]
        models.add(name)
        if name != COMPETITION_MODEL:
            report.add(
                "error",
                "model",
                f"agent {node.get('name')!r} declares {raw!r}; competition scoring requires {COMPETITION_MODEL!r}",
                where,
            )
    return models


def _check_tools(cfg: Any, report: Report, where: str) -> None:
    for node in _iter_agent_nodes(cfg):
        for entry in node.get("tools") or []:
            if isinstance(entry, str):
                if entry not in ALLOWED_TOOLS:
                    close = _nearest(entry, ALLOWED_TOOLS)
                    hint = f"; did you mean {close!r}?" if close else ""
                    report.add(
                        "error",
                        "tool-name",
                        f"agent {node.get('name')!r} requests unknown tool {entry!r}{hint}",
                        where,
                    )
            elif isinstance(entry, dict):
                if set(entry) - {"agent_tool"}:
                    unknown = sorted(set(entry) - {"agent_tool"})
                    report.add(
                        "error",
                        "tool-name",
                        f"agent {node.get('name')!r} has an unrecognised tool entry key(s) {unknown}",
                        where,
                    )
            else:
                report.add(
                    "error",
                    "tool-name",
                    f"agent {node.get('name')!r} has a tool entry of type {type(entry).__name__}",
                    where,
                )


def _nearest(word: str, candidates: Iterable[str]) -> str | None:
    import difflib

    hit = difflib.get_close_matches(word, list(candidates), n=1, cutoff=0.7)
    return hit[0] if hit else None


def _collect_config_paths(cfg: Any) -> list[str]:
    """Every `config_path` referenced by sub_agents or agent_tool entries.

    `config_path` resolves against the bundle root, unlike `!include`, which
    resolves against the including file.
    """
    out: list[str] = []
    if isinstance(cfg, dict):
        for key, val in cfg.items():
            if key == "config_path" and isinstance(val, str):
                out.append(val)
            else:
                out.extend(_collect_config_paths(val))
    elif isinstance(cfg, list):
        for v in cfg:
            out.extend(_collect_config_paths(v))
    return out


def _walk_agent_graph(root: Path, root_cfg_path: Path, report: Report) -> None:
    """DFS the agent graph, resolving config_path against the bundle root."""
    seen: set[Path] = set()
    on_stack: set[Path] = set()

    def visit(path: Path, trail: list[str]) -> None:
        if path in on_stack:
            report.add(
                "error",
                "agent-cycle",
                f"agent graph is cyclic: {' -> '.join(trail)}; an AgentTool cycle recurses forever",
            )
            return
        if path in seen:
            return
        seen.add(path)
        on_stack.add(path)
        report.reached.add(path)

        cfg = _load_yaml(path, root, report)
        if cfg is not _MISSING and cfg is not None:
            where = _rel(path, root)
            report.agents[where] = cfg if isinstance(cfg, dict) else {}
            _check_model(cfg, report, where)
            _check_tools(cfg, report, where)
            _check_agent_class(cfg, report, where)
            _check_placeholders_in_cfg(cfg, report, where)
            for ref in _collect_config_paths(cfg):
                p = PurePosixPath(ref.replace("\\", "/"))
                if p.is_absolute() or ".." in p.parts:
                    report.add("error", "agent-ref", f"config_path must be relative without '..': {ref}", where)
                    continue
                target = (root / ref).resolve()
                if not target.is_file():
                    report.add(
                        "error",
                        "agent-ref",
                        f"config_path target missing: {ref} "
                        "(config_path resolves against the bundle root, not the including file)",
                        where,
                    )
                    continue
                visit(target, trail + [ref])
        on_stack.discard(path)

    visit(root_cfg_path.resolve(), [root_cfg_path.name])


def _check_agent_class(cfg: Any, report: Report, where: str) -> None:
    for node in _iter_agent_nodes(cfg):
        cls = node.get("agent_class")
        if cls is not None and cls not in AGENT_CLASSES:
            report.add(
                "error",
                "agent-class",
                f"agent {node.get('name')!r} has agent_class {cls!r}; allowed: {sorted(AGENT_CLASSES)}",
                where,
            )
        if cls == "LoopAgent":
            it = node.get("max_iterations")
            if it is None:
                report.add(
                    "warn",
                    "agent-class",
                    f"LoopAgent {node.get('name')!r} has no max_iterations; it defaults to 500, "
                    "which will burn the whole tool-call budget",
                    where,
                )
            elif not isinstance(it, int) or not 1 <= it <= 500:
                report.add(
                    "error",
                    "agent-class",
                    f"LoopAgent {node.get('name')!r} max_iterations={it!r} outside 1..500",
                    where,
                )


def _check_adapters(root: Path, report: Report) -> None:
    declared: set[str] = set()
    for where, cfg in report.agents.items():
        for node in _iter_agent_nodes(cfg):
            name = node.get("adapter")
            if not name:
                continue
            declared.add(name)
            d = root / "adapters" / name
            if not d.is_dir():
                report.add(
                    "error",
                    "adapter",
                    f"agent {node.get('name')!r} references adapter {name!r} but adapters/{name}/ does not exist "
                    "(this is the bug shipped in the official sample_submission)",
                    where,
                )
                continue
            cfg_file = d / "adapter_config.json"
            weights = d / "adapter_model.safetensors"
            if not cfg_file.is_file():
                report.add("error", "adapter", f"adapters/{name}/adapter_config.json is missing", where)
            if not weights.is_file():
                report.add("error", "adapter", f"adapters/{name}/adapter_model.safetensors is missing", where)
            if cfg_file.is_file():
                try:
                    meta = json.loads(cfg_file.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    report.add("error", "adapter", f"adapters/{name}/adapter_config.json is invalid: {exc}", where)
                else:
                    for key in ("r", "lora_alpha"):
                        val = meta.get(key)
                        if isinstance(val, int) and val > MAX_LORA_RANK:
                            report.add(
                                "error",
                                "adapter",
                                f"adapters/{name} has {key}={val} > max_lora_rank {MAX_LORA_RANK}",
                                where,
                            )
    if len(declared) > MAX_ADAPTERS:
        report.add("error", "adapter", f"{len(declared)} adapters declared; vLLM serves at most {MAX_ADAPTERS}")

    adapters_dir = root / "adapters"
    if adapters_dir.is_dir():
        for d in sorted(p for p in adapters_dir.iterdir() if p.is_dir()):
            if d.name not in declared:
                report.add(
                    "warn",
                    "adapter",
                    f"adapters/{d.name}/ is never referenced by any agent; it is dead weight in the 3 GiB budget",
                )


# --- Placeholder / prompt-text checks ----------------------------------------

_BRACE_RE = re.compile(r"(?<!\{)\{([^{}]*)\}(?!\})")


def _placeholder_findings(text: str, report: Report, where: str, kind: str) -> None:
    """ADK interpolates {name} from session.state and raises KeyError otherwise."""
    for m in _BRACE_RE.finditer(text):
        token = m.group(1).strip()
        base = token.rstrip("?")
        if not token:
            continue
        line = text.count("\n", 0, m.start()) + 1
        if base in CONDITIONAL_STATE_KEYS and not token.endswith("?"):
            report.add(
                "error",
                "placeholder",
                f"{kind} line {line}: {{{token}}} must be written {{{base}?}}. The harness only puts "
                f"{base!r} in session state when the task supplies it, and it is absent from all 129 "
                "public tasks, so a bare reference raises KeyError.",
                where,
            )
            continue
        if base in STATE_KEYS:
            continue
        report.add(
            "error",
            "placeholder",
            f"{kind} line {line}: single-brace token {{{token}}} is not a known state key "
            f"({', '.join(sorted(STATE_KEYS))}); ADK will raise KeyError at run time. "
            "Double the braces if it is literal JSON.",
            where,
        )


def _check_placeholders_in_cfg(cfg: Any, report: Report, where: str) -> None:
    for node in _iter_agent_nodes(cfg):
        for key in ("instruction", "global_instruction", "description"):
            val = node.get(key)
            if isinstance(val, str):
                _placeholder_findings(val, report, where, f"{node.get('name')}.{key}")


def _check_prompt_texts(root: Path, report: Report) -> None:
    """Lint every shipped prose file: placeholders, sandbox reality, generalization."""
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in (".md", ".txt"):
            continue
        rel = _rel(p, root)
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            report.add("error", "encoding", f"not valid UTF-8: {exc}", rel)
            continue

        _placeholder_findings(text, report, rel, "prompt")

        lines = text.splitlines()
        for pattern, why in UNREAL_PATTERNS:
            for i, line in enumerate(lines, 1):
                if GENERIC_OK in line:
                    continue
                if re.search(pattern, line, re.IGNORECASE):
                    report.add("error", "prompt-reality", f"line {i}: {why}", rel)

        low = text.lower()
        for token in REPO_TOKENS:
            if token not in low:
                continue
            for i, line in enumerate(lines, 1):
                if token in line.lower() and GENERIC_OK not in line:
                    report.add(
                        "error",
                        "generalization",
                        f"line {i}: mentions {token!r}. The dev set is 90% fastapi+rich but the private set is "
                        f"believed to hold different repos; repo-specific prompt rules measured 0.05. "
                        f"Append '{GENERIC_OK} <reason>' to override.",
                        rel,
                    )
        for pattern in REPO_TOKENS_STRICT:
            for i, line in enumerate(lines, 1):
                if GENERIC_OK in line:
                    continue
                if re.search(pattern, line, re.IGNORECASE):
                    report.add(
                        "error",
                        "generalization",
                        f"line {i}: library-specific usage {pattern!r}; keep prompts framework-agnostic",
                        rel,
                    )


def _check_reachability(root: Path, report: Report) -> None:
    """Files present but unreachable from the root config are dead -- or are the
    file you thought you were editing."""
    reached = {p.resolve() for p in report.reached}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = _rel(p, root)
        if p.parent == root and p.name in ("MANIFEST.yaml", "eval_config.yaml"):
            continue
        if p.suffix.lower() == ".safetensors" or p.name == "adapter_config.json":
            continue
        if p.name == "SKILL.md" or "skills" in PurePosixPath(rel).parts:
            continue
        if p.resolve() not in reached:
            report.add(
                "warn",
                "unreachable",
                "not reachable from the root config via !include or config_path; "
                "it ships but is never read",
                rel,
            )


def _check_eval_config(root: Path, report: Report) -> None:
    p = root / "eval_config.yaml"
    if not p.is_file():
        return  # absent is correct: the grader defaults are 60 min / 100 tool calls
    raw = _load_yaml(p, root, report)
    if raw is _MISSING:
        return
    if not isinstance(raw, dict) or "evaluation" not in raw:
        report.add(
            "error",
            "eval-config",
            "eval_config.yaml must nest its keys under an `evaluation:` key, or the harness ignores it",
            "eval_config.yaml",
        )
        return
    sec = raw["evaluation"] or {}
    mt = sec.get("max_time_minutes")
    if isinstance(mt, (int, float)) and mt > 60:
        report.add(
            "error",
            "eval-config",
            f"max_time_minutes={mt} exceeds the grader ceiling of 60; this looks like a local "
            "measurement value that must not be shipped",
            "eval_config.yaml",
        )
    tc = sec.get("max_tool_calls")
    if isinstance(tc, int) and tc > 100:
        report.add(
            "error",
            "eval-config",
            f"max_tool_calls={tc} exceeds the grader ceiling of 100",
            "eval_config.yaml",
        )
    if isinstance(tc, int) and tc < 100:
        report.add(
            "warn",
            "eval-config",
            f"max_tool_calls={tc} throws away part of the 100-call budget the grader would otherwise give you",
            "eval_config.yaml",
        )
    if isinstance(mt, (int, float)) and mt < 60:
        report.add(
            "warn",
            "eval-config",
            f"max_time_minutes={mt} throws away part of the 60-minute budget",
            "eval_config.yaml",
        )


def _check_sampling(root: Path, report: Report) -> None:
    for where, cfg in report.agents.items():
        for node in _iter_agent_nodes(cfg):
            gcc = node.get("generate_content_config")
            if not isinstance(gcc, dict):
                continue
            name = node.get("name")
            banned = {"tools", "system_instruction", "http_options", "safety_settings", "response_schema"}
            for key in sorted(banned & set(gcc)):
                report.add(
                    "error",
                    "sampling",
                    f"agent {name!r}: {key!r} inside generate_content_config bypasses the sandbox and is "
                    "rejected by the schema",
                    where,
                )
            mot = gcc.get("max_output_tokens")
            if isinstance(mot, int) and not 1 <= mot <= 32768:
                report.add("error", "sampling", f"agent {name!r}: max_output_tokens={mot} outside 1..32768", where)
            think = gcc.get("thinking_config") or {}
            tb = think.get("thinking_budget") if isinstance(think, dict) else None
            if isinstance(tb, int) and not 0 <= tb <= 32768:
                report.add("error", "sampling", f"agent {name!r}: thinking_budget={tb} outside 0..32768", where)
            if isinstance(think, dict) and "thinking_level" in think:
                report.add(
                    "warn",
                    "sampling",
                    f"agent {name!r}: thinking_level maps to OpenAI reasoning_effort and is dropped by "
                    "litellm under vLLM; use thinking_budget instead",
                    where,
                )
            if isinstance(mot, int) and isinstance(tb, int) and mot + tb > 32768:
                report.add(
                    "error",
                    "sampling",
                    f"agent {name!r}: max_output_tokens + thinking_budget = {mot + tb} exceeds "
                    "max_model_len 32768, leaving no room for the prompt",
                    where,
                )
            # max_output_tokens is a RESERVATION, not a cap. litellm sends it on
            # every request and vLLM rejects the call when
            # input + max_output_tokens > max_model_len, so the real input
            # ceiling is 32768 - max_output_tokens. Measured 2026-10-06 in run
            # probe_c12: the analyzer reached 24,577 input tokens against
            # v00's 8192 reservation and died with a NON-RETRYABLE
            # ContextWindowExceededError -- the task was lost outright, one
            # token over. This check is the one that would have caught it.
            if isinstance(mot, int):
                ceiling = MODEL_WINDOW - mot
                if ceiling <= COMPACTION_THRESHOLD:
                    report.add(
                        "error",
                        "sampling",
                        f"agent {name!r}: max_output_tokens={mot} leaves an input ceiling of "
                        f"{ceiling}, at or below the {COMPACTION_THRESHOLD}-token compaction "
                        "threshold. The agent would die before compaction could ever relieve it",
                        where,
                    )
                elif ceiling < OBSERVED_PROMPT_PEAK:
                    report.add(
                        "warn",
                        "sampling",
                        f"agent {name!r}: max_output_tokens={mot} leaves an input ceiling of "
                        f"{ceiling}, below the {OBSERVED_PROMPT_PEAK} tokens actually observed "
                        "in run probe_c12. A prompt that big is non-retryable: the task is lost, "
                        "not degraded. Prefer the smallest output budget the agent's job needs",
                        where,
                    )
            temp = gcc.get("temperature")
            if isinstance(temp, (int, float)) and temp == 0:
                report.add(
                    "warn",
                    "sampling",
                    f"agent {name!r}: temperature 0 can trap the agent re-issuing one failing edit forever; "
                    "because it keeps calling tools the 3-nudge rule never fires and the budget drains",
                    where,
                )


def _check_skills(root: Path, report: Report) -> None:
    declared: set[str] = set()
    for where, cfg in report.agents.items():
        for node in _iter_agent_nodes(cfg):
            for s in node.get("skills") or []:
                if not isinstance(s, str):
                    continue
                declared.add(s)
                d = (root / s).resolve()
                if not d.is_dir():
                    report.add("error", "skill", f"skill directory missing: {s}", where)
                elif not (d / "SKILL.md").is_file():
                    report.add("error", "skill", f"{s}/SKILL.md is missing; ADK skills require it", where)
    skills_dir = root / "skills"
    if skills_dir.is_dir():
        for d in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
            rel = _rel(d, root)
            if rel not in declared and not any(rel in s for s in declared):
                report.add("warn", "skill", f"{rel}/ is not declared by any agent's `skills:` list")


# --- Entry point --------------------------------------------------------------


def validate_bundle(bundle: str | Path) -> Report:
    """Run every offline check against a materialized bundle directory."""
    root = Path(bundle)
    report = Report(bundle=root)
    if not root.is_dir():
        report.add("error", "bundle", f"not a directory: {root}")
        return report

    _check_extensions(root, report)
    _check_size(root, report)
    root_cfg = _check_root_config(root, report)
    if root_cfg is None:
        return report

    _walk_agent_graph(root, root_cfg, report)

    models = {m for cfg in report.agents.values() for m in _check_model(cfg, Report(bundle=root), "")}
    if len(models) > 1:
        report.add(
            "error",
            "single-model",
            f"{len(models)} distinct base models declared ({sorted(models)}); "
            "validate_single_declared_model requires exactly one",
        )

    _check_adapters(root, report)
    _check_skills(root, report)
    _check_sampling(root, report)
    _check_prompt_texts(root, report)
    _check_eval_config(root, report)
    _check_reachability(root, report)
    return report


def adk_dry_load(bundle: str | Path) -> Finding | None:
    """Strongest no-GPU check: ask ADK itself to compile the config.

    Returns a Finding on a genuine schema/parse failure, or None. A missing
    google-adk install, or a failure to reach the model server, is not a bundle
    defect and yields None.
    """
    try:
        from google.adk.agents import config_agent_utils  # type: ignore
    except Exception:
        return None
    try:
        config_agent_utils.from_config(str(Path(bundle) / "agent.yaml"))
    except Exception as exc:  # noqa: BLE001 - we classify by message
        msg = str(exc)
        benign = ("api_key", "api key", "connection", "not found: model", "unreachable", "credential")
        if any(b in msg.lower() for b in benign):
            return None
        return Finding("error", "adk-dry-load", f"ADK refused to compile the config: {type(exc).__name__}: {msg}")
    return None
