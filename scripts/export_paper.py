"""Export the paper's submittable body and count it against the 3,000-word cap.

Why this exists: `paper/MANUSCRIPT.md` carries a drafting header (status, word
budget, the audit trail) that is *not* part of the submission, so the word count
that matters is the body's alone. Counting it by hand got the answer wrong twice,
and the paper itself claims every figure in it is re-derivable -- a claim the
word count should not be an exception to.

The cap is the only hard format constraint the paper track states ("Scope: 3,000
words maximum") and it does **not** define how words are counted. So this reports
three bases and the paper is only called compliant when all three pass:

* ``prose``    -- whitespace tokens containing a letter or digit. The honest
                  count of words a reader sees.
* ``naive``    -- a plain ``split()`` of the markdown source. Scores table pipes
                  and standalone ``=`` as words, so it is the pessimistic basis
                  and the one a careless counter would produce.
* ``rendered`` -- ``naive`` minus table pipes and heading marks, which a renderer
                  turns into layout rather than text.

    python scripts/export_paper.py              # report the counts
    python scripts/export_paper.py --write      # also write paper/SUBMISSION.md
    python scripts/export_paper.py --check      # exit 1 if any basis is over

`--write` produces the exact text to paste into the Kaggle Writeup. It is
generated, never hand-edited: edit `paper/MANUSCRIPT.md` and re-run.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANUSCRIPT = ROOT / "paper" / "MANUSCRIPT.md"
SUBMISSION = ROOT / "paper" / "SUBMISSION.md"

#: The official paper-track limit, read first-party 2026-10-27 from the
#: competition overview: "Scope: 3,000 words maximum, reporting original,
#: unpublished research."
WORD_CAP = 3000

#: Markdown tokens a renderer turns into layout rather than words.
LAYOUT_TOKENS = frozenset({"|", "##", "###", "####", "#", "---", "-", "--"})

#: The drafting header ends at the first horizontal rule on its own line. The
#: body is everything after it, and only the body is submitted.
HEADER_SEPARATOR = "\n---\n"


def split_header(text: str) -> tuple[str, str]:
    """Return (drafting header, submittable body).

    Raises if the separator is missing rather than silently submitting the
    header, which would put the word count and the audit trail in the paper.
    """
    idx = text.find(HEADER_SEPARATOR)
    if idx < 0:
        raise ValueError(
            f"no header separator ({HEADER_SEPARATOR!r}) in the manuscript; "
            "refusing to guess where the submittable body starts"
        )
    return text[:idx], text[idx + len(HEADER_SEPARATOR):].lstrip("\n")


def title_of(header: str) -> str:
    """The manuscript's H1, which is the Writeup's title field, not body text.

    The body deliberately starts at the abstract: Kaggle takes the title
    separately, so an H1 in the pasted text would duplicate it. Carrying the
    title out in a comment is what stops it being lost on the way.
    """
    for line in header.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def count_prose(text: str) -> int:
    """Whitespace tokens that contain a letter or digit, fenced code excluded."""
    stripped = re.sub(r"```.*?```", "", text, flags=re.S)
    return sum(1 for w in stripped.split() if re.search(r"[A-Za-z0-9]", w))


def count_naive(text: str) -> int:
    """A plain split() of the markdown, pipes and all. The pessimistic basis."""
    return len(text.split())


def count_rendered(text: str) -> int:
    """`naive` less the tokens a renderer turns into layout."""
    return sum(1 for w in text.split() if w not in LAYOUT_TOKENS)


def counts(body: str) -> dict[str, int]:
    return {
        "prose": count_prose(body),
        "naive": count_naive(body),
        "rendered": count_rendered(body),
    }


def sections(body: str) -> list[tuple[str, int]]:
    """Per-``##``-section prose counts, in document order."""
    out: list[tuple[str, int]] = []
    for part in re.split(r"(?m)^## ", body):
        if not part.strip():
            continue
        out.append((part.splitlines()[0].strip(), count_prose(part)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="write paper/SUBMISSION.md")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if any counting basis exceeds the cap")
    ap.add_argument("--manuscript", type=Path, default=MANUSCRIPT)
    args = ap.parse_args()

    header, body = split_header(args.manuscript.read_text(encoding="utf-8"))

    for title, n in sections(body):
        print(f"{n:5d}  {title[:62]}")
    print("-" * 46)

    basis = counts(body)
    over = [k for k, v in basis.items() if v > WORD_CAP]
    for name, n in basis.items():
        flag = "OVER" if n > WORD_CAP else "ok"
        print(f"{n:5d}  {name:9s} cap {WORD_CAP}, margin {WORD_CAP - n:+5d}  {flag}")
    print(f"{count_prose(header):5d}  header     (not submitted)")

    title = title_of(header)
    print(f"\ntitle: {title}")

    if args.write:
        SUBMISSION.write_text(
            "<!-- GENERATED by scripts/export_paper.py -- do not edit. "
            "Edit paper/MANUSCRIPT.md and re-run. -->\n"
            f"<!-- Writeup title field: {title} -->\n\n" + body,
            encoding="utf-8", newline="\n",
        )
        print(f"wrote {SUBMISSION.relative_to(ROOT)}")

    if args.check and over:
        print(f"\nFAIL over the cap on: {', '.join(sorted(over))}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
