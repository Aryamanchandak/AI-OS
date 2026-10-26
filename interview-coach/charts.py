"""Render the question chart from Claude's data spec (exact numbers, no image-model garbling)."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

PALETTE = ["#1F5F8B", "#E08A1E", "#3A9D74", "#8E5BA8"]


def render(spec, out_path):
    cats = [str(c) for c in spec.get("categories", [])][:8]
    series = []
    for s in spec.get("series", [])[:4]:
        vals = [float(v) for v in s.get("values", [])][: len(cats)]
        vals += [0.0] * (len(cats) - len(vals))
        series.append((str(s.get("name", "")), vals))
    kind = spec.get("kind", "bar")
    if kind == "bar" and len(series) > 1:
        kind = "grouped_bar"

    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=150)
    x = np.arange(len(cats))

    if kind == "line":
        for i, (name, vals) in enumerate(series):
            ax.plot(x, vals, marker="o", linewidth=2.2, color=PALETTE[i], label=name)
            for xi, v in zip(x, vals):
                ax.annotate(f"{v:,.4g}", (xi, v), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=8, color=PALETTE[i])
    elif kind == "stacked_bar":
        bottom = np.zeros(len(cats))
        for i, (name, vals) in enumerate(series):
            bars = ax.bar(x, vals, 0.6, bottom=bottom, color=PALETTE[i], label=name)
            ax.bar_label(bars, labels=[f"{v:,.4g}" for v in vals], label_type="center", fontsize=8, color="white")
            bottom += np.array(vals)
    else:  # bar / grouped_bar
        n = max(len(series), 1)
        w = 0.8 / n
        for i, (name, vals) in enumerate(series):
            bars = ax.bar(x - 0.4 + w * (i + 0.5), vals, w, color=PALETTE[i], label=name)
            ax.bar_label(bars, labels=[f"{v:,.4g}" for v in vals], fontsize=8, padding=2)

    ax.set_xticks(x)
    ax.set_xticklabels(cats, rotation=0 if max((len(c) for c in cats), default=0) < 10 else 25, ha="right" if max((len(c) for c in cats), default=0) >= 10 else "center")
    ax.set_title(spec.get("title", ""), fontsize=13, fontweight="bold", loc="left", pad=12)
    ax.set_xlabel(spec.get("x_label", ""))
    ax.set_ylabel(spec.get("y_label", ""))
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)
    if len(series) > 1:
        ax.legend(frameon=False, fontsize=9)
    note = spec.get("source_note") or "Illustrative data"
    fig.text(0.01, 0.01, note, fontsize=8, color="#666")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out_path)
    plt.close(fig)
