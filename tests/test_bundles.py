"""Every bundle must validate clean, and the validator must actually catch things.

The second half matters more than the first. A validator that passes everything
is worse than no validator, because it creates false confidence in a submission
we only get to make once a day.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swegemma_lab.build import build_bundle, compute_bundle_hash, package_bundle, roundtrip_check
from swegemma_lab.validate import COMPETITION_MODEL, validate_bundle

BUNDLES = ROOT / "bundles"
VARIANTS = sorted(p.name for p in BUNDLES.iterdir() if p.is_dir() and not p.name.startswith("_"))


# --- Real bundles -------------------------------------------------------------



def _ships_eval_config(variant: str) -> bool:
    """Does this variant's MANIFEST declare that eval_config.yaml is the point?

    Such a variant cannot be built without the flag -- build_bundle refuses,
    because dropping the file would package the parent's bytes.
    """
    man = BUNDLES / variant / "MANIFEST.yaml"
    return man.is_file() and "ships_eval_config: true" in man.read_text(encoding="utf-8")


@pytest.mark.parametrize("variant", VARIANTS)
def test_variant_builds_and_validates(variant, tmp_path):
    result = build_bundle(variant, bundles_dir=BUNDLES, out_root=tmp_path,
                          ship_eval_config=_ships_eval_config(variant))
    report = validate_bundle(result.out_dir)
    assert report.ok, "\n" + report.render()


@pytest.mark.parametrize("variant", VARIANTS)
def test_variant_survives_zip_roundtrip(variant, tmp_path):
    """The grader sees the extracted zip, not our directory."""
    result = build_bundle(variant, bundles_dir=BUNDLES, out_root=tmp_path / "dist",
                          ship_eval_config=_ships_eval_config(variant))
    zip_path = package_bundle(result.out_dir, tmp_path / f"{variant}.zip")
    extracted = roundtrip_check(zip_path, tmp_path / "rt")
    report = validate_bundle(extracted)
    assert report.ok, "\n" + report.render()
    assert compute_bundle_hash(extracted) == result.bundle_hash


@pytest.mark.parametrize("variant", VARIANTS)
def test_build_is_deterministic(variant, tmp_path):
    ship = _ships_eval_config(variant)
    a = build_bundle(variant, bundles_dir=BUNDLES, out_root=tmp_path / "a", ship_eval_config=ship)
    b = build_bundle(variant, bundles_dir=BUNDLES, out_root=tmp_path / "b", ship_eval_config=ship)
    assert a.bundle_hash == b.bundle_hash
    za = package_bundle(a.out_dir, tmp_path / "a.zip").read_bytes()
    zb = package_bundle(b.out_dir, tmp_path / "b.zip").read_bytes()
    assert za == zb, "zip bytes must be reproducible for ledger pooling to work"


@pytest.mark.parametrize("variant", VARIANTS)
def test_no_eval_config_unless_requested(variant, tmp_path):
    if _ships_eval_config(variant):
        pytest.skip("declares ships_eval_config; covered by the refusal test below")
    result = build_bundle(variant, bundles_dir=BUNDLES, out_root=tmp_path)
    assert not (result.out_dir / "eval_config.yaml").exists()


def test_baseline_topology_is_the_public_bundle(tmp_path):
    """Guards the reference config against accidental edits.

    Six tools on the coder, the three code-intelligence tools quarantined in the
    read-only analyzer, and no eval_config.yaml so the grader defaults apply.
    """
    import yaml

    result = build_bundle("v00_public_baseline", bundles_dir=BUNDLES, out_root=tmp_path)
    raw = (result.out_dir / "agent.yaml").read_text(encoding="utf-8")
    cfg = yaml.safe_load(raw.replace("!include ", ""))

    assert cfg["name"] == "swe_coder"
    assert cfg["model"] == COMPETITION_MODEL
    str_tools = [t for t in cfg["tools"] if isinstance(t, str)]
    assert str_tools == ["run_command", "read_file", "edit_file", "write_file", "get_status", "submit_patch"]
    agent_tools = [t for t in cfg["tools"] if isinstance(t, dict)]
    assert len(agent_tools) == 1
    assert agent_tools[0]["agent_tool"]["config_path"] == "sub_agents/code_analyzer.yaml"
    assert agent_tools[0]["agent_tool"]["skip_summarization"] is True

    sub = yaml.safe_load((result.out_dir / "sub_agents" / "code_analyzer.yaml").read_text(encoding="utf-8")
                         .replace("!include ", ""))
    assert set(sub["tools"]) == {
        "run_command", "read_file", "search_similar_code", "get_code_neighbors", "get_code_subgraph",
    }


# --- The validator must catch these ------------------------------------------


@pytest.fixture
def bundle(tmp_path):
    """A minimal valid bundle that individual tests then break in one way."""
    root = tmp_path / "b"
    (root / "prompts").mkdir(parents=True)
    (root / "configs").mkdir()
    (root / "sub_agents").mkdir()
    (root / "agent.yaml").write_text(
        "name: coder\n"
        f"model: {COMPETITION_MODEL}\n"
        "instruction: !include prompts/system.md\n"
        "generate_content_config: !include configs/sampling.yaml\n"
        "tools:\n"
        "  - run_command\n"
        "  - submit_patch\n",
        encoding="utf-8",
    )
    (root / "prompts" / "system.md").write_text("Fix the issue, then call submit_patch.\n", encoding="utf-8")
    (root / "configs" / "sampling.yaml").write_text(
        "temperature: 0.2\nmax_output_tokens: 8192\nthinking_config:\n  thinking_budget: 4096\n", encoding="utf-8"
    )
    return root


def _codes(root):
    return {f.check for f in validate_bundle(root).findings if f.level == "error"}


def test_baseline_fixture_is_clean(bundle):
    report = validate_bundle(bundle)
    assert report.ok, "\n" + report.render()


def test_catches_missing_root_config(bundle):
    (bundle / "agent.yaml").unlink()
    assert "root-config" in _codes(bundle)


def test_catches_two_root_configs(bundle):
    shutil.copy(bundle / "agent.yaml", bundle / "root_agent.yaml")
    assert "root-config" in _codes(bundle)


def test_catches_disallowed_extension(bundle):
    (bundle / "notes.docx").write_text("x", encoding="utf-8")
    assert "extension" in _codes(bundle)


def test_catches_missing_include(bundle):
    (bundle / "prompts" / "system.md").unlink()
    assert "include-missing" in _codes(bundle)


def test_catches_include_escaping_bundle(bundle):
    (bundle / "agent.yaml").write_text(
        f"name: coder\nmodel: {COMPETITION_MODEL}\ninstruction: !include ../../secret.md\ntools:\n  - run_command\n",
        encoding="utf-8",
    )
    assert _codes(bundle) & {"include-path", "include-missing"}


def test_catches_wrong_model(bundle):
    text = (bundle / "agent.yaml").read_text(encoding="utf-8").replace(COMPETITION_MODEL, "gemma-4-12b-it")
    (bundle / "agent.yaml").write_text(text, encoding="utf-8")
    assert "model" in _codes(bundle)


def test_accepts_provider_prefixed_model(bundle):
    text = (bundle / "agent.yaml").read_text(encoding="utf-8").replace(
        f"model: {COMPETITION_MODEL}", f"model: openai/{COMPETITION_MODEL}"
    )
    (bundle / "agent.yaml").write_text(text, encoding="utf-8")
    assert "model" not in _codes(bundle)


def test_catches_unknown_tool(bundle):
    text = (bundle / "agent.yaml").read_text(encoding="utf-8").replace("  - run_command", "  - run_commands")
    (bundle / "agent.yaml").write_text(text, encoding="utf-8")
    assert "tool-name" in _codes(bundle)


def test_catches_missing_sub_agent_config(bundle):
    text = (bundle / "agent.yaml").read_text(encoding="utf-8") + (
        "  - agent_tool:\n      config_path: sub_agents/nope.yaml\n"
    )
    (bundle / "agent.yaml").write_text(text, encoding="utf-8")
    assert "agent-ref" in _codes(bundle)


def test_catches_agent_tool_cycle(bundle):
    (bundle / "agent.yaml").write_text(
        f"name: coder\nmodel: {COMPETITION_MODEL}\ninstruction: hi\ntools:\n"
        "  - agent_tool:\n      config_path: sub_agents/a.yaml\n",
        encoding="utf-8",
    )
    (bundle / "sub_agents" / "a.yaml").write_text(
        f"name: a\nmodel: {COMPETITION_MODEL}\ninstruction: hi\ntools:\n"
        "  - agent_tool:\n      config_path: agent.yaml\n",
        encoding="utf-8",
    )
    assert "agent-cycle" in _codes(bundle)


def test_catches_dangling_adapter_reference(bundle):
    """Exactly the bug shipped in the official sample_submission."""
    text = (bundle / "agent.yaml").read_text(encoding="utf-8").replace(
        "instruction:", "adapter: main_lora\ninstruction:"
    )
    (bundle / "agent.yaml").write_text(text, encoding="utf-8")
    assert "adapter" in _codes(bundle)


def test_accepts_well_formed_adapter(bundle):
    d = bundle / "adapters" / "main_lora"
    d.mkdir(parents=True)
    (d / "adapter_config.json").write_text(json.dumps({"r": 16, "lora_alpha": 32}), encoding="utf-8")
    (d / "adapter_model.safetensors").write_bytes(b"\x00")
    text = (bundle / "agent.yaml").read_text(encoding="utf-8").replace(
        "instruction:", "adapter: main_lora\ninstruction:"
    )
    (bundle / "agent.yaml").write_text(text, encoding="utf-8")
    assert "adapter" not in _codes(bundle)


def test_catches_oversized_lora_rank(bundle):
    d = bundle / "adapters" / "main_lora"
    d.mkdir(parents=True)
    (d / "adapter_config.json").write_text(json.dumps({"r": 256}), encoding="utf-8")
    (d / "adapter_model.safetensors").write_bytes(b"\x00")
    text = (bundle / "agent.yaml").read_text(encoding="utf-8").replace(
        "instruction:", "adapter: main_lora\ninstruction:"
    )
    (bundle / "agent.yaml").write_text(text, encoding="utf-8")
    assert "adapter" in _codes(bundle)


def test_catches_unknown_placeholder_in_prompt(bundle):
    (bundle / "prompts" / "system.md").write_text(
        'Return JSON like {"status": "ok"} when done.\n', encoding="utf-8"
    )
    assert "placeholder" in _codes(bundle)


def test_allows_known_state_keys_and_doubled_braces(bundle):
    (bundle / "prompts" / "system.md").write_text(
        'Issue: {problem_description}\nHints: {hints?}\nReturn {{"status": "ok"}}.\n', encoding="utf-8"
    )
    assert "placeholder" not in _codes(bundle)


def test_bare_hints_placeholder_is_rejected(bundle):
    """agent_runner only sets `hints` when the task has hints_text, and all 129
    public tasks have none, so a bare {hints} is a guaranteed KeyError."""
    (bundle / "prompts" / "system.md").write_text("Hints: {hints}\n", encoding="utf-8")
    assert "placeholder" in _codes(bundle)


def test_yml_root_config_is_rejected(bundle):
    """HARNESS_README lists agent.yml, but discovery.py never looks for it."""
    (bundle / "agent.yaml").rename(bundle / "agent.yml")
    codes = _codes(bundle)
    assert "root-config" in codes


def test_catches_ripgrep_and_pip_in_prompt(bundle):
    (bundle / "prompts" / "system.md").write_text(
        "Search with rg -n foo.\nIf a module is missing, pip install it.\n", encoding="utf-8"
    )
    assert "prompt-reality" in _codes(bundle)


def test_prompt_reality_does_not_flag_ordinary_prose(bundle):
    """'the working tree is graded' is a harness fact we want stated, not a `tree` call.

    A blanket word match flagged it, which would have pushed us toward not
    explaining the single highest-consequence rule in the prompt.
    """
    (bundle / "prompts" / "system.md").write_text(
        "If you run out of time the working tree is graded as it stands.\n"
        "Large inputs degrade the whole tree of choices.\n",
        encoding="utf-8",
    )
    assert "prompt-reality" not in _codes(bundle)


def test_prompt_reality_still_flags_real_tree_invocation(bundle):
    (bundle / "prompts" / "system.md").write_text("Survey the repo with tree -L 2.\n", encoding="utf-8")
    assert "prompt-reality" in _codes(bundle)


def test_catches_repo_specific_prompt_text(bundle):
    (bundle / "prompts" / "system.md").write_text(
        "For fastapi tasks, edit executable code under docs_src/.\n", encoding="utf-8"
    )
    assert "generalization" in _codes(bundle)


def test_generic_ok_override_suppresses_generalization_error(bundle):
    (bundle / "prompts" / "system.md").write_text(
        "Prefer git grep over fastapi-specific paths.  # generic-ok: naming the antipattern, not relying on it\n",
        encoding="utf-8",
    )
    assert "generalization" not in _codes(bundle)


def test_catches_shipped_local_measurement_budget(bundle):
    (bundle / "eval_config.yaml").write_text(
        "evaluation:\n  max_time_minutes: 180\n  max_tool_calls: 100\n", encoding="utf-8"
    )
    assert "eval-config" in _codes(bundle)


def test_catches_eval_config_missing_evaluation_key(bundle):
    (bundle / "eval_config.yaml").write_text("max_tool_calls: 100\n", encoding="utf-8")
    assert "eval-config" in _codes(bundle)


def test_catches_context_budget_overflow(bundle):
    (bundle / "configs" / "sampling.yaml").write_text(
        "max_output_tokens: 30000\nthinking_config:\n  thinking_budget: 8192\n", encoding="utf-8"
    )
    assert "sampling" in _codes(bundle)


def test_catches_sandbox_bypassing_generation_field(bundle):
    (bundle / "configs" / "sampling.yaml").write_text(
        "temperature: 0.2\nsafety_settings:\n  - category: HARM\n", encoding="utf-8"
    )
    assert "sampling" in _codes(bundle)


def test_warns_on_unreachable_file(bundle):
    (bundle / "prompts" / "orphan.md").write_text("never read\n", encoding="utf-8")
    report = validate_bundle(bundle)
    assert any(f.check == "unreachable" for f in report.warnings)


def test_warns_on_loop_agent_without_max_iterations(bundle):
    (bundle / "agent.yaml").write_text(
        "name: outer\nagent_class: LoopAgent\nsub_agents:\n  - config_path: sub_agents/a.yaml\n",
        encoding="utf-8",
    )
    (bundle / "sub_agents" / "a.yaml").write_text(
        f"name: a\nmodel: {COMPETITION_MODEL}\ninstruction: hi\ntools:\n  - run_command\n", encoding="utf-8"
    )
    report = validate_bundle(bundle)
    assert any(f.check == "agent-class" for f in report.warnings)


def test_every_notebook_cell_compiles():
    """A syntax error in a notebook cell is only discovered when Kaggle runs it.

    Papermill fails at `In [1]`, the run is wasted, and the cause is always a
    mangled escape from whatever wrote the cell. Three such errors reached Kaggle
    before this test existed; one of them cost a GPU allocation.
    """
    import ast
    import json as _json

    bad = []
    for nb_path in sorted((ROOT / "notebooks").glob("*.ipynb")) + sorted(
        (ROOT / "kernels").rglob("*.ipynb")
    ):
        nb = _json.loads(nb_path.read_text(encoding="utf-8"))
        for n, cell in enumerate(nb.get("cells", [])):
            if cell.get("cell_type") != "code":
                continue
            src = "".join(cell.get("source", []))
            if not src.strip():
                continue
            try:
                ast.parse(src)
            except SyntaxError as exc:
                bad.append(f"{nb_path.name} cell {cell.get('id', n)!r} line {exc.lineno}: {exc.msg}")
    assert not bad, "notebook cells with syntax errors:\n" + "\n".join(bad)


# --- the declaration must be load-bearing (2026-10-21) -------------------
# A bundle whose MANIFEST says `ships_eval_config: true` exists ONLY to carry
# that file. Building it without the flag silently deletes it and produces the
# parent's hash: v10_clamp_timecap built without --ship-eval-config packages to
# 26354b2d0153378d, v08's exact hash, and would read on the leaderboard as "the
# cap does not work" when the cap was never shipped. The near-miss happened once
# with v09 (E016) and the field was decorative, so it happened again.


def _variants_declaring_eval_config():
    out = []
    for name in VARIANTS:
        man = BUNDLES / name / "MANIFEST.yaml"
        if man.is_file() and "ships_eval_config: true" in man.read_text(encoding="utf-8"):
            out.append(name)
    return out


def test_some_variant_declares_it_so_this_guard_is_live():
    assert _variants_declaring_eval_config(), "no variant declares ships_eval_config: true"


@pytest.mark.parametrize("variant", _variants_declaring_eval_config())
def test_declaring_variant_refuses_to_build_without_the_flag(tmp_path, variant):
    with pytest.raises(ValueError) as exc:
        build_bundle(variant, BUNDLES, tmp_path, ship_eval_config=False)
    assert "ships_eval_config" in str(exc.value)


@pytest.mark.parametrize("variant", _variants_declaring_eval_config())
def test_declaring_variant_ships_the_file_with_the_flag(tmp_path, variant):
    res = build_bundle(variant, BUNDLES, tmp_path, ship_eval_config=True)
    assert "eval_config.yaml" in res.files


# --- the dataset publish path must honour the same declaration (2026-10-21) ---
# `build_bundle`'s refusal only protects callers that pass the flag. The publish
# path did not: `push_dataset.stage()` built EVERY bundle with the default
# `ship_eval_config=False`, so before the refusal existed it published v09 and
# v10 with eval_config.yaml stripped -- the parent's bytes under a new name, in
# the dataset the GPU kernels actually read, with the parent's bundle_hash
# recorded in the ledger. After the refusal it raised instead, which is how this
# was found. Either way it was broken, so it is tested rather than remembered.


def test_declares_eval_config_agrees_with_the_manifests():
    from swegemma_lab.build import declares_eval_config

    for variant in VARIANTS:
        assert declares_eval_config(variant, BUNDLES) == _ships_eval_config(variant), variant


def test_dataset_staging_ships_eval_config_for_declaring_variants(tmp_path, monkeypatch):
    """The published lab dataset must hold the same bytes the grader would get."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import push_dataset

    monkeypatch.setattr(push_dataset, "STAGE", tmp_path / "_dataset")
    staged = push_dataset.stage(VARIANTS, {})

    for variant in VARIANTS:
        ships = _ships_eval_config(variant)
        present = (staged / "bundles" / variant / "eval_config.yaml").is_file()
        assert present == ships, f"{variant}: staged eval_config={present}, declared={ships}"

    # And the staged hash must equal the hash a --ship-eval-config build gives,
    # because that hash is what the ledger pools on and what a submission
    # message quotes. A mismatch means the dataset and the zip are not the same
    # configuration, which no downstream check would notice.
    for variant in _variants_declaring_eval_config():
        expected = build_bundle(variant, BUNDLES, tmp_path / "ref", ship_eval_config=True)
        assert compute_bundle_hash(staged / "bundles" / variant) == expected.bundle_hash, variant
