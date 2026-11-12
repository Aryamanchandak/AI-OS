import json
import base64
import tempfile
import threading
import unittest
from urllib import request

from model_forge.ai import LocalEngine
from model_forge.service import ModelForge
from model_forge.web import ThreadingHTTPServer, handler_factory


class WebTests(unittest.TestCase):
    def test_api_forges_and_lists_models(self):
        with tempfile.TemporaryDirectory() as directory:
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(ModelForge(directory, LocalEngine())))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                payload = json.dumps({"kind": "text", "content": "Supply constraints increase prices.", "name": "Supply"}).encode()
                req = request.Request(base + "/api/forge", payload, {"Content-Type": "application/json"}, method="POST")
                with request.urlopen(req) as response:
                    created = json.load(response)
                with request.urlopen(base + "/api/models") as response:
                    models = json.load(response)
                self.assertTrue(created["accepted"])
                self.assertEqual(models[0]["name"], "Supply")
                model = models[0]
                harden_payload = json.dumps({"edge_id": model["edges"][0]["id"]}).encode()
                req = request.Request(base + f"/api/models/{model['id']}/harden", harden_payload, {"Content-Type": "application/json"}, method="POST")
                with request.urlopen(req) as response:
                    hardened = json.load(response)
                score_payload = json.dumps({"prediction_id": model["predictions"][0]["id"], "outcome": 1}).encode()
                req = request.Request(base + f"/api/models/{model['id']}/score", score_payload, {"Content-Type": "application/json"}, method="POST")
                with request.urlopen(req) as response:
                    scored = json.load(response)
                self.assertEqual(hardened["operation"], "steelman.harden-edge")
                self.assertEqual(scored["operation"], "decision-tracker.score")
            finally:
                server.shutdown(); server.server_close(); thread.join()

    def test_api_accepts_browser_file_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(ModelForge(directory, LocalEngine())))
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                payload = json.dumps({"kind":"file", "filename":"claim.md", "content":base64.b64encode(b"Practice increases accuracy.").decode()}).encode()
                req = request.Request(f"http://127.0.0.1:{server.server_port}/api/forge", payload, {"Content-Type":"application/json"}, method="POST")
                with request.urlopen(req) as response: created = json.load(response)
                self.assertTrue(created["accepted"])
                self.assertEqual(next(iter(created["model"]["provenance"].values()))["locator"], "upload:claim.md")
            finally:
                server.shutdown(); server.server_close(); thread.join()


if __name__ == "__main__":
    unittest.main()
