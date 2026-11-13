# `web/__init__.py`

Empty package marker (just a blank line). It exists so `consequence_radar.web` is importable as a package; it defines no symbols itself. The actual package surface is `consequence_radar.web.app`, which `__main__.py` imports directly (`from .web.app import run`) rather than re-exporting anything through this `__init__.py`.
