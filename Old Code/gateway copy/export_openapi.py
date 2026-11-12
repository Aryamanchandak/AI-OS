import json
from pathlib import Path

from main import app


target = Path(__file__).with_name("openapi.json")
target.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
print(target)
