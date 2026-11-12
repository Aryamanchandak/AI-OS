from pathlib import Path
import sys


project_src = str(Path(__file__).resolve().parent / "src")
if project_src not in sys.path:
    sys.path.insert(0, project_src)

from steelman.app import main  # noqa: E402


main()
