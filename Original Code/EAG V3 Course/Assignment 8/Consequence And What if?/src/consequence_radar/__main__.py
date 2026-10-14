"""Allow the application to start with ``python -m consequence_radar``."""

from .web.app import run


if __name__ == "__main__":
    run()
