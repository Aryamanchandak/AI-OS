"""Matplotlib adapter: one comparable numeric criterion to a PNG."""

from pathlib import Path


def chart_comparison(result, criterion_id, directory):
    criterion = next((c for c in result["request"]["criteria"] if c["id"] == criterion_id), None)
    if not criterion or criterion.get("kind") != "number" or not result["findings"][criterion_id]["comparable"]:
        return {"chart_error": "Chart requires one complete, comparable numerical criterion"}
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    options = result["request"]["options"]
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (criterion_id + ".png")
    fig, ax = plt.subplots(figsize=(8, max(3, len(options) * 0.6)), dpi=150)
    names = [o["name"] for o in options]
    values = [result["cells"][o["id"]][criterion_id]["value"] for o in options]
    ax.barh(names, values)
    ax.invert_yaxis()
    ax.set_xlabel(criterion.get("unit", "Value"))
    ax.set_title(criterion.get("label", criterion_id))
    ax.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return {"chart": str(path), "criterion": criterion_id}
