"""Three reproducible assignment cases; task metadata lives in plain YAML."""
from pathlib import Path
import yaml

TARGETS = Path(__file__).parent / "targets"
TASKS = yaml.safe_load(Path(__file__).with_suffix(".yaml").read_text())
VSCODE_DEBUG_PORT = TASKS["vscode"]["electron_debugging_port"]


def canvas_url():
    return (TARGETS / "canvas_game.html").resolve().as_uri()
