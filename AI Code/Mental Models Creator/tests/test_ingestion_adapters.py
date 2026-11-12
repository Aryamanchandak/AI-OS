import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from model_forge.adapters import ADAPTER_SCHEMA, Envelope, RemoteSteelman
from model_forge.ingest import from_path, from_url, live_news
from model_forge.schema import CausalModel, Edge, Entity


class Headers:
    def __init__(self, content_type="text/html"): self.content_type = content_type
    def get_content_type(self): return self.content_type


class Response(io.BytesIO):
    def __init__(self, data, content_type="text/html"):
        super().__init__(data); self.headers = Headers(content_type)
    def __enter__(self): return self
    def __exit__(self, *args): self.close()


class IngestionAdapterTests(unittest.TestCase):
    def test_url_visible_text_extraction(self):
        page = b"<html><style>hidden</style><body><h1>Claim</h1><p>Supply increases output.</p></body></html>"
        with patch("model_forge.ingest.request.urlopen", return_value=Response(page)):
            result = from_url("https://example.test/paper")
        self.assertIn("Supply increases output", result.text)
        self.assertNotIn("hidden", result.text)

    def test_live_news_rss_extraction(self):
        rss = b"<rss><channel><item><title>Supply increases</title><description>Output rises</description><pubDate>Fri, 07 Aug 2026 00:00:00 GMT</pubDate></item></channel></rss>"
        with patch("model_forge.ingest.request.urlopen", return_value=Response(rss, "application/rss+xml")):
            result = live_news("supply")
        self.assertIn("2026-08-07", result.text)
        self.assertEqual(result.source.kind, "live-news")

    def test_pdf_and_audio_report_actionable_dependency_or_key_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf = f"{directory}/paper.pdf"; audio = f"{directory}/note.wav"
            Path(pdf).write_bytes(b"not a pdf")
            Path(audio).write_bytes(b"not audio")
            with self.assertRaisesRegex(RuntimeError, r"model-forge\[pdf\]"):
                from_path(pdf)
            with patch.dict("os.environ", {}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                    from_path(audio)

    def test_remote_adapter_sends_versioned_envelope(self):
        model = CausalModel("M", "S", entities=[Entity("A"), Entity("B")], edges=[Edge("a", "b")])
        response = Response(b'{"schema":"model-forge.adapter/v1","payload":{"ok":true}}', "application/json")
        with patch("model_forge.adapters.request.urlopen", return_value=response) as opened:
            result = RemoteSteelman("https://steelman.test/adapter").harden(model, model.edges[0].id)
        self.assertEqual(result["schema"], ADAPTER_SCHEMA)
        sent = opened.call_args.args[0]
        self.assertEqual(sent.method, "POST")
        self.assertIn(ADAPTER_SCHEMA.encode(), sent.data)


if __name__ == "__main__": unittest.main()
