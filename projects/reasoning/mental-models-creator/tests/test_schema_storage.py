import json
import base64
from pathlib import Path
import tempfile
import unittest

from model_forge.schema import CausalModel, Edge, Entity, Prediction
from model_forge.storage import FlatFileLibrary
from model_forge.ai import LocalEngine
from model_forge.service import ModelForge


class SchemaStorageTests(unittest.TestCase):
    def test_typed_record_round_trip_and_rendering(self):
        model = CausalModel(
            name="Feedback",
            scope="Teams",
            entities=[Entity("Fast feedback"), Entity("Learning speed")],
            edges=[Edge("fast-feedback", "learning-speed", "positive", support="stated")],
            predictions=[Prediction("More feedback increases learning by the deadline.", "2030-01-01", .7)],
        )
        with tempfile.TemporaryDirectory() as directory:
            library = FlatFileLibrary(directory)
            library.save(model)
            restored = library.get(model.id)
            self.assertEqual(restored.edges[0].sign, "positive")
            self.assertEqual(restored.predictions[0].confidence, .7)
            self.assertEqual(len(list(Path(directory).glob("*.md"))), 1)

    def test_requires_predictions_when_admitting_model(self):
        model = CausalModel("Taxonomy", "Notes")
        with self.assertRaisesRegex(ValueError, "zero predictions"):
            model.validate(require_predictions=True)

    def test_browser_style_markdown_upload_is_operational(self):
        with tempfile.TemporaryDirectory() as directory:
            encoded = base64.b64encode(b"Feedback increases learning.").decode()
            result = ModelForge(directory, LocalEngine()).forge_upload("notes.md", encoded, "Upload")
            self.assertTrue(result["accepted"])
            self.assertEqual(next(iter(result["model"]["provenance"].values()))["locator"], "upload:notes.md")


if __name__ == "__main__":
    unittest.main()
