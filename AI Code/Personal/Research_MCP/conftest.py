import sys
from pathlib import Path

# Ensure src/ is on the path (handles editable install issues with spaces in path)
sys.path.insert(0, str(Path(__file__).parent / "src"))
