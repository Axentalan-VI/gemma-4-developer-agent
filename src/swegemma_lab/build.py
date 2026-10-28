"""Materialize and package a submission bundle, reproducibly.

`_shared/` holds the common prompts, sampling configs and skills; each
`bundles/<variant>/` holds only its overrides. Building copies shared files then
variant files into `dist/<variant>/`, so the directory that gets validated is
byte-identical to the one that gets zipped and run on Kaggle -- one code path,
no drift.

Determinism matters for two reasons. It lets `bundle_hash` pool repeated runs of
the same config in the ledger, and it lets us reproduce the community's
"identical archive, different score" observation deliberately instead of by
accident.
"""

from __future__ import annotations

import hashlib
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

#: Lab metadata and local-only files that must never reach the grader.
EXCLUDE_NAMES = {"MANIFEST.yaml", ".gitkeep", ".DS_Store", "Thumbs.db"}
EXCLUDE_DIRS = {"__pycache__", ".ipynb_checkpoints", ".git"}

#: Fixed zip metadata. Matches the public notebook's packager so a faithful
#: reproduction of its bundle produces an identical archive.
ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)
ZIP_EXTERNAL_ATTR = 0o644 << 16

TEXT_SUFFIXES = {".yaml", ".yml", ".md", ".txt", ".py", ".json"}


@dataclass(frozen=True)
class BuildResult:
    variant: str
    out_dir: Path
    files: list[str]
    bundle_hash: str
    total_bytes: int

    def render(self) -> str:
        lines = [f"{self.variant}: {len(self.files)} files, {self.total_bytes:,} B", f"  bundle_hash {self.bundle_hash}"]
        lines += [f"    {f}" for f in self.files]
        return "\n".join(lines)


def _is_excluded(path: Path, base: Path) -> bool:
    rel = path.relative_to(base)
    if any(part in EXCLUDE_DIRS for part in rel.parts):
        return True
    return path.name in EXCLUDE_NAMES


def _normalize(path: Path) -> bytes:
    """Read a file, forcing LF endings on text so Windows authoring cannot
    change the shipped bytes or the hash. A stray CR also breaks YAML scalars."""
    data = path.read_bytes()
    if path.suffix.lower() in TEXT_SUFFIXES:
        data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return data


def _copy_tree(src: Path, dst: Path) -> None:
    for p in sorted(src.rglob("*")):
        if p.is_dir() or _is_excluded(p, src):
            continue
        target = dst / p.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_normalize(p))


def compute_bundle_hash(root: Path) -> str:
    """sha256 over sorted (posix relpath, LF-normalized bytes) pairs.

    Independent of filesystem order, zip metadata and line-ending style, so two
    machines agree on whether two bundles are the same configuration.
    """
    h = hashlib.sha256()
    for p in sorted((q for q in root.rglob("*") if q.is_file()), key=lambda q: q.relative_to(root).as_posix()):
        rel = p.relative_to(root).as_posix()
        body = _normalize(p)
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        h.update(len(body).to_bytes(8, "big"))
        h.update(body)
    return h.hexdigest()


def declares_eval_config(variant: str, bundles_dir: str | Path) -> bool:
    """Does this variant's MANIFEST say that `eval_config.yaml` is the point?

    Such a variant cannot be built without `ship_eval_config=True`:
    `build_bundle` refuses, because dropping the file would package the parent's
    bytes under a new name. Every caller that builds *every* bundle -- the test
    suite, `push_dataset.py` -- has to ask this question, so it is answered in
    one place rather than reimplemented per caller. `push_dataset.py` did
    reimplement it by omission and published v09/v10 with the file stripped,
    which is how a lab dataset came to hold v08's bytes under v10's name.
    """
    manifest = Path(bundles_dir) / variant / "MANIFEST.yaml"
    return manifest.is_file() and "ships_eval_config: true" in manifest.read_text(encoding="utf-8")


def build_bundle(
    variant: str,
    bundles_dir: str | Path,
    out_root: str | Path,
    shared: str = "_shared",
    ship_eval_config: bool = False,
) -> BuildResult:
    """Copy `_shared` then the variant's own files into `out_root/<variant>/`."""
    bundles_dir = Path(bundles_dir)
    src = bundles_dir / variant
    if not src.is_dir():
        raise FileNotFoundError(f"no such variant: {src}")

    out_dir = Path(out_root) / variant
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    shared_dir = bundles_dir / shared
    if shared_dir.is_dir():
        _copy_tree(shared_dir, out_dir)
    _copy_tree(src, out_dir)  # variant files win on conflict

    if not ship_eval_config:
        # A bundle that declares `ships_eval_config: true` exists only to carry
        # that file, so dropping it silently would package the PARENT's bytes
        # under a new name: v10_clamp_timecap built without the flag hashes to
        # 26354b2d0153378d, which is v08's hash exactly. A leaderboard score on
        # that reads as "the cap does not work" when no cap was ever shipped.
        # Refuse instead. The field was decorative until this check existed, and
        # the near-miss had already happened once with v09 (EXPERIMENTS E016).
        manifest = src / "MANIFEST.yaml"
        if manifest.is_file() and "ships_eval_config: true" in manifest.read_text(encoding="utf-8"):
            raise ValueError(
                f"{variant}/MANIFEST.yaml declares ships_eval_config: true, but "
                "build was called with ship_eval_config=False. That would delete "
                "eval_config.yaml and package the parent's bytes. Pass "
                "--ship-eval-config, or drop the declaration from the MANIFEST."
            )
        # Absent eval_config.yaml means the grader's own 60 min / 100 tool calls
        # apply, which is what we want unless a variant deliberately overrides.
        (out_dir / "eval_config.yaml").unlink(missing_ok=True)

    files = sorted(p.relative_to(out_dir).as_posix() for p in out_dir.rglob("*") if p.is_file())
    total = sum(p.stat().st_size for p in out_dir.rglob("*") if p.is_file())
    return BuildResult(variant, out_dir, files, compute_bundle_hash(out_dir), total)


def package_bundle(bundle: str | Path, zip_path: str | Path) -> Path:
    """Write a deterministic zip with the bundle's files at the archive root."""
    bundle = Path(bundle)
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    zip_path.unlink(missing_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted((q for q in bundle.rglob("*") if q.is_file()), key=lambda q: q.relative_to(bundle).as_posix()):
            arcname = PurePosixPath(p.relative_to(bundle).as_posix())
            info = zipfile.ZipInfo(str(arcname), date_time=ZIP_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = ZIP_EXTERNAL_ATTR
            z.writestr(info, _normalize(p))
    return zip_path


def roundtrip_check(zip_path: str | Path, work_dir: str | Path) -> Path:
    """Extract the archive so the validator can inspect what the grader will see.

    Catches the packaging mistakes a directory check cannot: a stray top-level
    folder inside the zip, or paths that only look right before compression.
    """
    work_dir = Path(work_dir)
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(work_dir)
    return work_dir
