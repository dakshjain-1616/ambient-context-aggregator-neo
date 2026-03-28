#!/usr/bin/env python3
"""
Generate professional dark-theme infographic charts for Ambient Context Aggregator.

Charts produced:
  1. assets/pipeline_diagram.png   — How It Works: signal collection pipeline
  2. assets/signal_breakdown.png   — Signal types captured per session
  3. assets/focus_scores.png       — Developer focus category radar chart
  4. assets/activity_heatmap.png   — Hourly activity heatmap over a week

Run: python3 scripts/generate_infographics.py
"""

import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

# ── Colour palette ─────────────────────────────────────────────────────────────
BG       = "#0D1117"
SURFACE  = "#161B22"
BORDER   = "#30363D"
TEXT     = "#E6EDF3"
MUTED    = "#8B949E"
PURPLE   = "#7B61FF"
BLUE     = "#00C2FF"
GREEN    = "#00E5A0"
WARNING  = "#FF9500"
PINK     = "#FF6B9D"
YELLOW   = "#FFD700"

ASSETS = Path(__file__).parent.parent / "assets"
ASSETS.mkdir(exist_ok=True)


def _base_fig(w=12, h=7):
    fig = plt.figure(figsize=(w, h), facecolor=BG)
    return fig


def _style_ax(ax):
    ax.set_facecolor(SURFACE)
    ax.tick_params(colors=MUTED, labelsize=10)
    ax.xaxis.label.set_color(TEXT)
    ax.yaxis.label.set_color(TEXT)
    ax.title.set_color(TEXT)
    for spine in ax.spines.values():
        spine.set_color(BORDER)
    ax.grid(color=BORDER, linewidth=0.6, alpha=0.7)
    return ax


# ──────────────────────────────────────────────────────────────────────────────
# Chart 1: Pipeline Diagram — How It Works
# ──────────────────────────────────────────────────────────────────────────────

def chart_pipeline_diagram():
    fig = _base_fig(14, 7)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(BG)
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 7)
    ax.axis("off")

    # Title
    ax.text(7, 6.5, "How Ambient Context Aggregator Works",
            ha="center", va="center", color=TEXT, fontsize=18, fontweight="bold")

    # ── Input sources (left column) ──────────────────────────────────────────
    sources = [
        ("File System\nWatcher",    PURPLE, 1.2, 5.0, "watchdog\nreal-time"),
        ("Git History\nScraper",    BLUE,   1.2, 3.6, "gitpython\n≤10 commits"),
        ("Shell History\nParser",   GREEN,  1.2, 2.2, "bash / zsh\n≤100 cmds"),
        ("Meeting Notes\nIngester", WARNING,1.2, 0.8, "markdown\n≤7 days"),
    ]

    for label, color, cx, cy, sub in sources:
        box = FancyBboxPatch((cx-0.85, cy-0.5), 1.7, 0.9,
                             boxstyle="round,pad=0.08", linewidth=1.5,
                             edgecolor=color, facecolor=color + "22")
        ax.add_patch(box)
        ax.text(cx, cy+0.08, label, ha="center", va="center",
                color=color, fontsize=9, fontweight="bold", linespacing=1.3)
        ax.text(cx, cy-0.32, sub, ha="center", va="center",
                color=MUTED, fontsize=7.5, linespacing=1.3)

    # ── SQLite store (middle-left) ─────────────────────────────────────────
    db_cx, db_cy = 4.0, 2.9
    db_box = FancyBboxPatch((db_cx-0.9, db_cy-0.9), 1.8, 1.8,
                            boxstyle="round,pad=0.1", linewidth=2,
                            edgecolor=MUTED, facecolor=SURFACE)
    ax.add_patch(db_box)
    ax.text(db_cx, db_cy+0.35, "SQLite", ha="center", va="center",
            color=TEXT, fontsize=11, fontweight="bold")
    ax.text(db_cx, db_cy-0.05, "Database", ha="center", va="center",
            color=MUTED, fontsize=9)
    ax.text(db_cx, db_cy-0.45, "file_events\ngit_commits\nterminal_cmds\nnotes",
            ha="center", va="center", color=MUTED, fontsize=7.5, linespacing=1.3)

    # Arrows from sources → DB
    for _, color, cx, cy, _ in sources:
        ax.annotate("", xy=(db_cx-0.9, db_cy),
                    xytext=(cx+0.85, cy),
                    arrowprops=dict(arrowstyle="-|>", color=color,
                                   lw=1.4, connectionstyle="arc3,rad=0.0"))

    # ── Compressor (middle) ───────────────────────────────────────────────
    comp_cx, comp_cy = 6.8, 2.9
    comp_box = FancyBboxPatch((comp_cx-1.1, comp_cy-0.85), 2.2, 1.7,
                              boxstyle="round,pad=0.1", linewidth=2,
                              edgecolor=PURPLE, facecolor=PURPLE + "22")
    ax.add_patch(comp_box)
    ax.text(comp_cx, comp_cy+0.45, "LLM Compressor", ha="center", va="center",
            color=PURPLE, fontsize=10, fontweight="bold")
    ax.text(comp_cx, comp_cy+0.1, "Claude / OpenRouter", ha="center", va="center",
            color=TEXT, fontsize=8.5)
    ax.text(comp_cx, comp_cy-0.25, "≤600 tokens\n5-min cache", ha="center", va="center",
            color=MUTED, fontsize=8, linespacing=1.3)

    # Arrow DB → Compressor
    ax.annotate("", xy=(comp_cx-1.1, comp_cy),
                xytext=(db_cx+0.9, db_cy),
                arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1.8))

    # ── Output channels (right column) ────────────────────────────────────
    outputs = [
        ("CLI\nget/watch/export",  GREEN,  10.5, 5.0),
        ("REST API\nFastAPI 12+",  BLUE,   10.5, 3.8),
        ("Web Dashboard\nGradio",  PURPLE, 10.5, 2.6),
        ("Python API\nimport",     YELLOW, 10.5, 1.4),
    ]

    for label, color, cx, cy in outputs:
        box = FancyBboxPatch((cx-0.9, cy-0.45), 1.8, 0.82,
                             boxstyle="round,pad=0.08", linewidth=1.5,
                             edgecolor=color, facecolor=color + "22")
        ax.add_patch(box)
        ax.text(cx, cy+0.05, label, ha="center", va="center",
                color=color, fontsize=8.5, fontweight="bold", linespacing=1.3)

    # Context bundle node
    ctx_cx, ctx_cy = 8.7, 2.9
    ctx_box = FancyBboxPatch((ctx_cx-0.8, ctx_cy-0.55), 1.6, 1.1,
                             boxstyle="round,pad=0.1", linewidth=2,
                             edgecolor=GREEN, facecolor=GREEN + "22")
    ax.add_patch(ctx_box)
    ax.text(ctx_cx, ctx_cy+0.18, "Context", ha="center", va="center",
            color=GREEN, fontsize=10, fontweight="bold")
    ax.text(ctx_cx, ctx_cy-0.2, "Summary", ha="center", va="center",
            color=GREEN, fontsize=9)

    # Arrow compressor → context
    ax.annotate("", xy=(ctx_cx-0.8, ctx_cy),
                xytext=(comp_cx+1.1, comp_cy),
                arrowprops=dict(arrowstyle="-|>", color=GREEN, lw=1.8))

    # Arrows context → outputs
    for _, color, cx, cy in outputs:
        ax.annotate("", xy=(cx-0.9, cy),
                    xytext=(ctx_cx+0.8, ctx_cy),
                    arrowprops=dict(arrowstyle="-|>", color=color,
                                   lw=1.2, connectionstyle="arc3,rad=0.0"))

    # Footer
    ax.text(7, 0.3, "All data persisted in SQLite · Mock mode works without API key · Runs passively in background",
            ha="center", va="center", color=MUTED, fontsize=8, style="italic")

    out = ASSETS / "pipeline_diagram.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"  ✓  {out}")


# ──────────────────────────────────────────────────────────────────────────────
# Chart 2: Signal Breakdown — what the tool captures per typical session
# ──────────────────────────────────────────────────────────────────────────────

def chart_signal_breakdown():
    fig, axes = plt.subplots(1, 2, figsize=(13, 6), facecolor=BG)
    fig.suptitle("Signals Captured per Developer Session",
                 color=TEXT, fontsize=16, fontweight="bold", y=1.01)

    # ── Left: grouped bar chart ────────────────────────────────────────────
    ax1 = axes[0]
    _style_ax(ax1)
    ax1.grid(axis="y", color=BORDER, linewidth=0.6, alpha=0.7)
    ax1.grid(axis="x", visible=False)

    categories = ["Light\nSession\n(2h)", "Normal\nSession\n(4h)",
                  "Heavy\nSession\n(8h)", "Full\nSprint\n(8h+)"]
    file_events = [12,  38,  95, 160]
    git_commits = [ 3,   8,  18,  35]
    commands    = [25,  75, 180, 310]
    notes       = [ 0,   1,   3,   6]

    x = np.arange(len(categories))
    w = 0.2
    bar_kw = dict(edgecolor=BG, linewidth=0.5)

    ax1.bar(x - 1.5*w, file_events, w, label="File Events",    color=PURPLE,  **bar_kw)
    ax1.bar(x - 0.5*w, git_commits, w, label="Git Commits",    color=BLUE,    **bar_kw)
    ax1.bar(x + 0.5*w, commands,    w, label="Shell Commands", color=GREEN,   **bar_kw)
    ax1.bar(x + 1.5*w, notes,       w, label="Meeting Notes",  color=WARNING, **bar_kw)

    ax1.set_xticks(x)
    ax1.set_xticklabels(categories, color=MUTED, fontsize=9)
    ax1.set_ylabel("Signal Count", color=TEXT, fontsize=11)
    ax1.set_title("Volume by Session Length", color=TEXT, fontsize=13, pad=10)
    ax1.tick_params(colors=MUTED)
    legend = ax1.legend(framealpha=0.2, facecolor=SURFACE, edgecolor=BORDER,
                        labelcolor=TEXT, fontsize=9)

    # ── Right: token compression donut ────────────────────────────────────
    ax2 = axes[1]
    ax2.set_facecolor(SURFACE)
    ax2.set_aspect("equal")

    raw_tokens     = 4200
    output_tokens  = 312
    saved_pct      = round((raw_tokens - output_tokens) / raw_tokens * 100, 1)

    sizes  = [output_tokens, raw_tokens - output_tokens]
    colors = [PURPLE, BORDER]
    wedges, _ = ax2.pie(sizes, colors=colors, startangle=90,
                        wedgeprops=dict(width=0.42, edgecolor=BG, linewidth=2))

    ax2.text(0, 0.12, f"{saved_pct}%", ha="center", va="center",
             color=GREEN, fontsize=28, fontweight="bold")
    ax2.text(0, -0.2, "compression", ha="center", va="center",
             color=MUTED, fontsize=11)

    ax2.text(0, -0.6, f"Raw signals: ~{raw_tokens:,} tokens\nCompressed: ~{output_tokens} tokens",
             ha="center", va="center", color=MUTED, fontsize=10, linespacing=1.5)
    ax2.set_title("Token Compression Ratio", color=TEXT, fontsize=13, pad=10)

    for ax in axes:
        ax.set_facecolor(SURFACE)

    plt.tight_layout(pad=2.0)
    out = ASSETS / "signal_breakdown.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"  ✓  {out}")


# ──────────────────────────────────────────────────────────────────────────────
# Chart 3: Focus Score Radar — developer work-type classification
# ──────────────────────────────────────────────────────────────────────────────

def chart_focus_radar():
    categories = [
        "Feature\nDevelopment", "Testing", "Debugging",
        "Refactoring", "Infrastructure", "Code Review", "Documentation"
    ]
    N = len(categories)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]

    # Three example developer session profiles
    profiles = {
        "Feature Sprint":  ([0.88, 0.45, 0.30, 0.25, 0.15, 0.20, 0.10], PURPLE),
        "QA / Bug-fix":    ([0.30, 0.80, 0.85, 0.40, 0.10, 0.35, 0.15], WARNING),
        "Infra / DevOps":  ([0.20, 0.35, 0.20, 0.30, 0.90, 0.25, 0.20], BLUE),
    }

    fig = plt.figure(figsize=(10, 8), facecolor=BG)
    ax = fig.add_subplot(111, polar=True, facecolor=SURFACE)

    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_rlabel_position(30)
    ax.set_ylim(0, 1)

    # Grid styling
    ax.grid(color=BORDER, linewidth=0.8)
    ax.spines["polar"].set_color(BORDER)
    ax.tick_params(colors=MUTED)

    # Radial labels
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["25", "50", "75", "100"], color=MUTED, fontsize=8)

    # Category labels
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, color=TEXT, fontsize=10, linespacing=1.2)

    for label, (values, color) in profiles.items():
        v = values + values[:1]
        ax.plot(angles, v, "o-", linewidth=2, color=color, markersize=5, label=label)
        ax.fill(angles, v, alpha=0.08, color=color)

    legend = ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.15),
                       framealpha=0.3, facecolor=SURFACE, edgecolor=BORDER,
                       labelcolor=TEXT, fontsize=10)

    ax.set_title("Developer Focus Classification\nby Session Type",
                 color=TEXT, fontsize=14, fontweight="bold", pad=20)

    out = ASSETS / "focus_radar.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"  ✓  {out}")


# ──────────────────────────────────────────────────────────────────────────────
# Chart 4: Activity Heatmap — hourly signal density across a work week
# ──────────────────────────────────────────────────────────────────────────────

def chart_activity_heatmap():
    rng = np.random.default_rng(42)

    days  = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    hours = [f"{h:02d}:00" for h in range(8, 20)]  # 8am–8pm
    H, D  = len(hours), len(days)

    # Simulate realistic activity: peaks 9-11am and 2-4pm
    base = rng.integers(0, 8, size=(H, D)).astype(float)
    for d in range(D):
        for hi, h in enumerate(range(8, 20)):
            if 9 <= h <= 11:
                base[hi, d] += rng.integers(20, 40)
            elif 14 <= h <= 16:
                base[hi, d] += rng.integers(15, 30)
            elif 12 <= h <= 13:
                base[hi, d] += rng.integers(2, 8)

    # Wednesday afternoon spike (big feature push)
    base[4:8, 2] += rng.integers(10, 25, size=4)

    fig, ax = plt.subplots(figsize=(12, 6), facecolor=BG)
    _style_ax(ax)

    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list(
        "aca", [BG, SURFACE, PURPLE + "88", PURPLE, BLUE], N=256
    )

    im = ax.imshow(base, aspect="auto", cmap=cmap, interpolation="nearest")

    ax.set_xticks(range(D))
    ax.set_xticklabels(days, color=TEXT, fontsize=12, fontweight="bold")
    ax.set_yticks(range(H))
    ax.set_yticklabels(hours, color=MUTED, fontsize=9)

    # Annotate high cells
    threshold = base.max() * 0.6
    for i in range(H):
        for j in range(D):
            if base[i, j] >= threshold:
                ax.text(j, i, f"{int(base[i,j])}", ha="center", va="center",
                        color=TEXT, fontsize=8, fontweight="bold")

    cbar = fig.colorbar(im, ax=ax, pad=0.02, shrink=0.85)
    cbar.ax.tick_params(colors=MUTED)
    cbar.set_label("Signal Events / Hour", color=MUTED, fontsize=10)

    ax.set_title("Developer Activity Heatmap — Signal Events per Hour",
                 color=TEXT, fontsize=14, fontweight="bold", pad=12)
    ax.set_xlabel("Day of Week", color=TEXT, fontsize=11, labelpad=8)
    ax.set_ylabel("Hour of Day", color=TEXT, fontsize=11, labelpad=8)

    # Highlight focus sessions
    for j, (start, end) in enumerate([(1, 3), (5, 7), (1, 3)]):
        ax.add_patch(plt.Rectangle((j + 0.5 - 0.49, start - 0.49),
                                   0.98, end - start + 0.98,
                                   linewidth=2, edgecolor=GREEN,
                                   facecolor="none", linestyle="--", alpha=0.6))

    ax.text(4.62, 6.0, "Focus\nSession", color=GREEN, fontsize=7.5,
            ha="right", va="center", style="italic")

    plt.tight_layout(pad=2.0)
    out = ASSETS / "activity_heatmap.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"  ✓  {out}")


# ──────────────────────────────────────────────────────────────────────────────

def main():
    print("Generating infographics…\n")
    chart_pipeline_diagram()
    chart_signal_breakdown()
    chart_focus_radar()
    chart_activity_heatmap()
    print(f"\nAll charts saved to {ASSETS}/")


if __name__ == "__main__":
    main()
