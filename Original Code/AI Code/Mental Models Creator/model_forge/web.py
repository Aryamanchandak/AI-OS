from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .service import ModelForge

STATIC = Path(__file__).with_name("static")


def handler_factory(forge: ModelForge):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ModelForge/0.1"

        def log_message(self, format: str, *args: Any) -> None:
            print(f"[model-forge] {format % args}")

        def do_GET(self) -> None:
            path = unquote(urlparse(self.path).path)
            try:
                if path == "/api/models": return self._json(forge.list_models())
                if path.startswith("/api/models/"):
                    parts = path.strip("/").split("/")
                    identifier = parts[2]
                    if len(parts) == 4 and parts[3] == "collisions": return self._json(forge.collisions(identifier))
                    return self._json(forge.get(identifier).to_dict())
                self._static(path)
            except (ValueError, KeyError, RuntimeError, OSError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

        def do_POST(self) -> None:
            path = unquote(urlparse(self.path).path)
            try:
                body = self._body()
                if path == "/api/forge":
                    kind = body.get("kind", "text")
                    args = (body.get("name", ""), int(body.get("predictions", 3)), body.get("domain", ""))
                    if kind == "text": result = forge.forge_text(body.get("content", ""), *args)
                    elif kind == "file": result = forge.forge_upload(body.get("filename", "upload.txt"), body.get("content", ""), *args)
                    elif kind == "url": result = forge.forge_url(body.get("content", ""), *args)
                    elif kind == "news": result = forge.forge_news(body.get("content", ""), *args)
                    else: raise ValueError(f"Unsupported ingestion kind: {kind}")
                    return self._json(result, HTTPStatus.CREATED if result["accepted"] else HTTPStatus.UNPROCESSABLE_ENTITY)
                parts = path.strip("/").split("/")
                if len(parts) >= 4 and parts[:2] == ["api", "models"]:
                    identifier, action = parts[2], parts[3]
                    if action == "hone": result = forge.hone(identifier, int(body.get("predictions", 3)), body.get("domain", ""))
                    elif action == "harden": result = forge.harden(identifier, body["edge_id"])
                    elif action == "run-forward": result = forge.run_forward(identifier, body.get("observations", ""))
                    elif action == "run-news": result = forge.run_news(identifier, body.get("query", ""), int(body.get("limit", 10)))
                    elif action == "score": result = forge.score(identifier, body["prediction_id"], float(body["outcome"]), body.get("note", ""))
                    else: raise ValueError(f"Unknown action: {action}")
                    return self._json(result)
                self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            except (ValueError, KeyError, RuntimeError, OSError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", 0))
            if length > 35_000_000: raise ValueError("Request exceeds the 35 MB transport limit")
            return json.loads(self.rfile.read(length) or b"{}")

        def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

        def _static(self, path: str) -> None:
            name = "index.html" if path == "/" else path.lstrip("/")
            target = (STATIC / name).resolve()
            if STATIC.resolve() not in target.parents or not target.is_file():
                return self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            data = target.read_bytes()
            self.send_response(HTTPStatus.OK); self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    return Handler


def run_server(host: str = "127.0.0.1", port: int = 8765, library: str | None = None) -> None:
    server = ThreadingHTTPServer((host, port), handler_factory(ModelForge(library)))
    print(f"Model Forge is running at http://{host}:{port}")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
