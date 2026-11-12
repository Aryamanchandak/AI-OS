import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from gateway.app import app  # noqa: E402


target = PROJECT_ROOT / "contracts" / "openapi.json"
target.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
print(target)
