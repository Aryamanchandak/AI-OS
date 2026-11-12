#!/usr/bin/env python3
"""Start the React Loop web app and open it in your browser.

    uv run python run.py                # http://127.0.0.1:8000
    uv run python run.py --port 8001
    uv run python run.py --no-browser

Equivalent to `python -m react_loop web`, which stays available.
"""

from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn

from react_loop.logging_setup import configure_logging


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--no-browser", action="store_true", help="don't open a browser")
    args = p.parse_args()

    configure_logging()
    url = f"http://{args.host}:{args.port}"

    if not args.no_browser:
        # Fires once uvicorn has had a moment to bind the port.
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()

    print(f"\n  React Loop  ->  {url}\n  Agent-built UI  ->  {url}/ui/latest\n")
    uvicorn.run("react_loop.web:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
