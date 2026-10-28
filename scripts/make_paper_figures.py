"""Render the paper's three figures: the Kaggle card and two gallery images.

Every number here is read from a committed source -- the leaderboard snapshot
in `data/leaderboard/`, and the C004 and P009 rows of `EXPERIMENTS.md` -- never
from the manuscript's prose. The task-count mapping goes through
`swegemma_lab.leaderboard.tasks_for_score`, the same inversion §D0 describes, so
the card cannot drift away from the method it illustrates.

    python scripts/make_paper_figures.py              # -> paper/figures/
    python scripts/make_paper_figures.py --out <dir>

Colours are the data-viz reference palette, validated for this use: the card is
an emphasis chart (one highlighted band, the field greyed, identity carried by
the text block), and the gallery figures use categorical slots 1-3, which pass
the adjacent and all-pairs gates on the light surface. Slot 3's sub-3:1 contrast
is relieved by visible direct labels, as that rule requires.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.path import Path as MPath  # noqa: E402
from matplotlib.patches import PathPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from swegemma_lab.leaderboard import Snapshot, tasks_for_score  # noqa: E402

SNAPSHOT = ROOT / "data" / "leaderboard" / "public_lb_2026-10-19.json"
DEFAULT_OUT = ROOT / "paper" / "figures"

N_TASKS = 58  # recovered by D0; one task = 0.0172
OUR_K = 8  # our 0.13

#: Reference palette, light mode.
SURFACE = "#fcfcfb"
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
FIELD = "#a9a7a0"  # grey-the-rest, 2.35:1 on the surface
INK, INK_2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"

DPI = 200

plt.rcParams.update(
    {
        "font.family": ["Segoe UI", "DejaVu Sans"],
        "figure.dpi": DPI,
        "savefig.dpi": DPI,
    }
)


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------


def band_around(snapshot: Snapshot, our_k: int = OUR_K, n_tasks: int = N_TASKS):
    """Teams per task count, and the one-task band around our own score.

    Returns `(by_k, band, band_total, pct)`. This is the figure's whole claim,
    separated from the drawing so it can be tested without rendering.
    """
    by_k = {}
    for score_s, count in snapshot.histogram.items():
        score = float(score_s)
        if score <= 0 or not count:
            continue
        by_k[tasks_for_score(score, n_tasks)] = count
    band = [k for k in (our_k - 1, our_k, our_k + 1) if k in by_k]
    band_total = sum(by_k[k] for k in band)
    return by_k, band, band_total, round(100 * band_total / snapshot.teams)


#: C004, the accepted gold/null calibration. 102 + 3 + 24 = 129.
CALIBRATION = [
    ("measurable", 102, S1, "the working set"),
    ("degenerate", 3, S3, "empty patch passes"),
    ("unmeasurable", 24, S2, "reference patch fails"),
]

#: P009, v00 vs v08 paired over 36 tasks at the grader's own 60-minute cap.
PAIRED_TASKS = 36
PAIRED = [
    ("timed out", 11, 0, "p = 0.00098", True),
    ("gold-file hit", 18, 24, "p = 0.210", False),
    ("gold file exact", 6, 4, "p = 0.688", False),
    ("resolved", 1, 1, "p = 1.000", False),
]


# --------------------------------------------------------------------------
# drawing helpers
# --------------------------------------------------------------------------


def rounded_end(ax, x, y, w, h, r_px, *, horizontal=False):
    """A bar with a rounded data-end and a square baseline end.

    The radius is given in pixels and taken through the axes transform, so it
    stays 4px whatever the data range.
    """
    inv = ax.transData.inverted()
    (x0, y0), (x1, y1) = inv.transform([(0, 0), (r_px, r_px)])
    rx, ry = abs(x1 - x0), abs(y1 - y0)
    if horizontal:
        rx, ry = min(rx, w), min(ry, h / 2)
    else:
        rx, ry = min(rx, w / 2), min(ry, h)
    c = 0.5523  # a circular quarter-arc as a cubic Bezier
    if horizontal:
        verts = [
            (x, y), (x + w - rx, y),
            (x + w - rx + rx * c, y), (x + w, y + ry - ry * c), (x + w, y + ry),
            (x + w, y + h - ry),
            (x + w, y + h - ry + ry * c), (x + w - rx + rx * c, y + h), (x + w - rx, y + h),
            (x, y + h), (x, y),
        ]
    else:
        verts = [
            (x, y), (x, y + h - ry),
            (x, y + h - ry + ry * c), (x + rx - rx * c, y + h), (x + rx, y + h),
            (x + w - rx, y + h),
            (x + w - rx + rx * c, y + h), (x + w, y + h - ry + ry * c), (x + w, y + h - ry),
            (x + w, y), (x, y),
        ]
    codes = [
        MPath.MOVETO, MPath.LINETO,
        MPath.CURVE4, MPath.CURVE4, MPath.CURVE4,
        MPath.LINETO,
        MPath.CURVE4, MPath.CURVE4, MPath.CURVE4,
        MPath.LINETO, MPath.CLOSEPOLY,
    ]
    patch = PathPatch(MPath(verts, codes), lw=0)
    ax.add_patch(patch)
    return patch


def strip(ax):
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])


def legend_row(fig, entries, x, y, *, size=6.8, pad=0.028):
    """Lay a one-line legend out left to right, measuring each label.

    Fixed columns collide the moment a label changes length, so the advance
    comes from the rendered extent rather than from a guess.
    """
    renderer = fig.canvas.get_renderer()
    w_px = fig.get_figwidth() * fig.dpi
    for label, color in entries:
        fig.text(x, y, "●", color=color, fontsize=size, va="center")
        text = fig.text(x + 0.016, y, label, color=INK_2, fontsize=size, va="center")
        x = text.get_window_extent(renderer).x1 / w_px + pad


# --------------------------------------------------------------------------
# figures
# --------------------------------------------------------------------------


def fig_card(snapshot: Snapshot, out: Path) -> None:
    """The Kaggle card: the leaderboard's resolution, in one number.

    1280x720. The upload form's label says 560x280, but it rejects anything
    under 640x360; this is 16:9 at twice that, so it stays crisp when the card
    is shown at full width.
    """
    by_k, band, band_total, pct = band_around(snapshot)
    ks = sorted(by_k)
    dpi = 200
    w_in, h_in = 6.4, 3.6
    w_px, h_px = int(w_in * dpi), int(h_in * dpi)

    fig = plt.figure(figsize=(w_in, h_in), dpi=dpi)
    fig.patch.set_facecolor(SURFACE)

    fig.text(0.055, 0.905, "THE LEADERBOARD CANNOT RESOLVE WHAT IS BEING TUNED",
             color=MUTED, fontsize=7.5, va="center")
    fig.text(0.055, 0.635, f"{pct}%", color=S1, fontsize=46, fontweight="bold",
             va="baseline")
    fig.text(0.055, 0.545, "of the field sits within\none task of our score",
             color=INK, fontsize=12.5, va="top", linespacing=1.45)
    fig.text(0.055, 0.315,
             f"{band_total:,} of {snapshot.teams:,} teams\n"
             f"resolved {band[0]}, {band[1]} or {band[2]} of {N_TASKS}",
             color=INK_2, fontsize=9.5, va="top", linespacing=1.5)

    ax = fig.add_axes((0.46, 0.245, 0.50, 0.57))
    ax.set_facecolor(SURFACE)
    ax.set_xlim(ks[0] - 0.7, ks[-1] + 0.7)
    peak = max(by_k.values())
    ax.set_ylim(0, peak * 1.18)

    slot_px = (0.50 * w_px) / len(ks)
    gap_px, cap_px = 2.0 * dpi / 100, 24.0 * dpi / 100
    bar_w = min(cap_px, slot_px - gap_px) / slot_px  # <=24px thick, 2px gap
    for k in ks:
        patch = rounded_end(ax, k - bar_w / 2, 0, bar_w, by_k[k], 4.0 * dpi / 100)
        patch.set_facecolor(S1 if k in band else FIELD)

    for y in (200, 400):
        ax.axhline(y, color=GRID, lw=1, zorder=0)
        ax.text(ks[0] - 0.85, y, f"{y}", color=MUTED, fontsize=8, va="center", ha="right")

    # Direct-label the one bar the story is about.
    ax.text(OUR_K, by_k[OUR_K] + peak * 0.045, "us", color=S1, fontsize=10,
            fontweight="bold", ha="center", va="bottom")

    strip(ax)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color(AXIS)
    ax.spines["bottom"].set_linewidth(1)
    ax.set_xticks([ks[0], 5, 10, ks[-1]])
    ax.set_xticklabels([str(ks[0]), "5", "10", str(ks[-1])])
    ax.tick_params(axis="x", length=0, pad=4, colors=MUTED, labelsize=8.5)
    ax.set_xlabel(f"tasks resolved, of {N_TASKS}", color=MUTED, fontsize=9, labelpad=8)

    fig.text(0.055, 0.065,
             f"Kaggle public leaderboard, {snapshot.captured_utc[:10]}  ·  "
             f"one task = {1 / N_TASKS:.4f}  ·  denominator recovered, not published",
             color=MUTED, fontsize=8, va="center")

    fig.savefig(out, facecolor=SURFACE, dpi=dpi)
    print(f"wrote {out.relative_to(ROOT)}  ({w_px}x{h_px})  {band_total:,}/{snapshot.teams:,} = {pct}%")


def fig_calibration(out: Path) -> None:
    """What the harness can see before any agent runs (component D1)."""
    total = sum(n for _, n, _, _ in CALIBRATION)
    assert total == 129, total

    fig = plt.figure(figsize=(5.5, 1.85))
    fig.patch.set_facecolor(SURFACE)
    fig.text(0.035, 0.94, "The instrument has a floor, and it is not small",
             color=INK, fontsize=11, fontweight="bold", va="top")
    fig.text(0.035, 0.775,
             "Running the benchmark's own reference patches against its own tests, "
             "with no agent at all.",
             color=INK_2, fontsize=7.2, va="top")

    ax = fig.add_axes((0.035, 0.375, 0.93, 0.11))
    ax.set_xlim(0, total)
    ax.set_ylim(0, 1)
    gap = total * (2 / (0.93 * 5.5 * DPI))  # a 2px surface gap, in data units
    x = 0.0
    for _, n, color, _ in CALIBRATION:
        rounded_end(ax, x, 0, n - (gap if x + n < total else 0), 1, 4.0,
                    horizontal=True).set_facecolor(color)
        ax.text(x + n / 2, 1.6, f"{n}", color=color, fontsize=9,
                fontweight="bold", ha="center", va="bottom")
        x += n
    strip(ax)

    legend_row(fig, [(f"{name} — {gloss}", color)
                     for name, _, color, gloss in CALIBRATION], 0.035, 0.205)

    fig.text(0.035, 0.065,
             "129 public tasks · calibration C004, CPU-only, 0 GPU-hours · the first "
             "two calibrations saw only 71 measurable tasks, and what fixed that\nwas "
             "capturing the failure output rather than theorising about the cause",
             color=MUTED, fontsize=5.9, va="center", linespacing=1.6)

    fig.savefig(out, facecolor=SURFACE)
    print(f"wrote {out.relative_to(ROOT)}")


def fig_paired(out: Path) -> None:
    """The one comparison the protocol made readable (run P009)."""
    fig = plt.figure(figsize=(5.5, 2.6))
    fig.patch.set_facecolor(SURFACE)
    fig.text(0.035, 0.955,
             "One arm eliminated every timeout; resolution said nothing at all",
             color=INK, fontsize=11, fontweight="bold", va="top")
    fig.text(0.035, 0.845,
             f"{PAIRED_TASKS} paired tasks, one session, at the grader's own 60-minute "
             "cap. McNemar exact, two-sided.",
             color=INK_2, fontsize=7.2, va="top")
    legend_row(fig, [("v00  baseline", S1), ("v08  retained change", S2)], 0.035, 0.745)

    ax = fig.add_axes((0.045, 0.285, 0.925, 0.42))
    ax.set_xlim(-0.6, len(PAIRED) - 0.4)
    ax.set_ylim(0, PAIRED_TASKS)

    slot_px = (0.925 * 5.5 * DPI) / len(PAIRED)
    bar_w = min(24.0 * DPI / 100, slot_px * 0.26) / slot_px
    gap = (2.0 * DPI / 100) / slot_px

    for i, (name, before, after, p_value, significant) in enumerate(PAIRED):
        for j, (value, color) in enumerate(((before, S1), (after, S2))):
            x = i + (j - 1) * (bar_w + gap / 2) + gap / 4
            if value > 0:
                rounded_end(ax, x, 0, bar_w, value, 4.0).set_facecolor(color)
            ax.text(x + bar_w / 2, value + PAIRED_TASKS * 0.025, f"{value}",
                    color=color, fontsize=7.5, fontweight="bold", ha="center", va="bottom")
        ax.text(i, -PAIRED_TASKS * 0.10, name, color=INK_2, fontsize=7.5,
                ha="center", va="top")
        ax.text(i, -PAIRED_TASKS * 0.235, p_value, color=INK if significant else MUTED,
                fontsize=7, fontweight="bold" if significant else "normal",
                ha="center", va="top")

    for y in (12, 24, 36):
        ax.axhline(y, color=GRID, lw=1, zorder=0)
        ax.text(-0.66, y, f"{y}", color=MUTED, fontsize=6, va="center", ha="right")
    ax.axhline(0, color=AXIS, lw=1, zorder=1)
    strip(ax)

    fig.text(0.035, 0.065,
             f"Tasks out of {PAIRED_TASKS} · resolution gave zero discordant pairs, so "
             "it carries no information at any sample size\nthe localization gain runs in "
             "the same direction as the prior run, but is no longer significant",
             color=MUTED, fontsize=5.9, va="center", linespacing=1.6)

    fig.savefig(out, facecolor=SURFACE)
    print(f"wrote {out.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    snapshot = Snapshot.load(args.snapshot)

    fig_card(snapshot, args.out / "card_1280x720.png")
    fig_calibration(args.out / "gallery_1_calibration.png")
    fig_paired(args.out / "gallery_2_paired.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
