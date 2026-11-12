import tempfile
import unittest
from unittest.mock import patch

from model_forge.ai import LocalEngine
from model_forge.collision import find_collisions
from model_forge.ingest import Ingested
from model_forge.schema import CausalModel, Edge, Entity, Prediction, Source
from model_forge.service import ModelForge


class ForgeFlowTests(unittest.TestCase):
    def test_full_honing_flow_creates_admissible_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            forge = ModelForge(directory, LocalEngine())
            result = forge.forge_text(
                "Frequent feedback increases learning speed. Long delays reduce decision quality.",
                "Learning loop", predictions=2, domain="software delivery",
            )
            self.assertTrue(result["accepted"])
            model = result["model"]
            self.assertEqual(len(model["predictions"]), 2)
            self.assertIn("15", model["compressions"])
            self.assertTrue(model["anomalies"])
            self.assertEqual(model["transfer_tests"][0]["domain"], "software delivery")

    def test_exact_prediction_count_even_with_one_edge(self):
        with tempfile.TemporaryDirectory() as directory:
            result = ModelForge(directory, LocalEngine()).forge_text("Practice increases accuracy.", predictions=7)
            self.assertTrue(result["accepted"])
            self.assertEqual(len(result["model"]["predictions"]), 7)

    def test_collision_detects_opposite_signs(self):
        entities = [Entity("Price"), Entity("Demand")]
        left = CausalModel("A", "market", entities=entities, edges=[Edge("price", "demand", "negative")])
        right = CausalModel("B", "market", entities=[Entity("Price"), Entity("Demand")], edges=[Edge("price", "demand", "positive")])
        collisions = find_collisions(left, [right])
        self.assertEqual(collisions[0].severity, "critical")

    def test_outcomes_earn_confidence_and_adapter_envelope_is_versioned(self):
        with tempfile.TemporaryDirectory() as directory:
            forge = ModelForge(directory, LocalEngine())
            result = forge.forge_text("Practice increases accuracy.", "Practice")
            model = result["model"]
            prediction = model["predictions"][0]
            response = forge.score(model["id"], prediction["id"], 1.0, "Observed")
            updated = forge.get(model["id"])
            self.assertEqual(response["schema"], "model-forge.adapter/v1")
            self.assertGreater(updated.confidence, 0)

    def test_complete_local_ai_os_workflow_persists_every_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            forge = ModelForge(directory, LocalEngine())
            first = forge.forge_text("Price reduces demand.", "Demand falls")
            second = forge.forge_text("Price increases demand.", "Demand rises")
            self.assertEqual(second["collisions"][0]["severity"], "critical")
            model_id = first["model"]["id"]
            edge_id = first["model"]["edges"][0]["id"]
            prediction_id = first["model"]["predictions"][0]["id"]
            hardened = forge.harden(model_id, edge_id)
            self.assertEqual(hardened["payload"]["verdict"], "provisionally hardened")
            forward = forge.run_forward(model_id, "Price and demand changed in the latest report.")
            self.assertTrue(forward["payload"]["assessments"])
            scored = forge.score(model_id, prediction_id, 1, "Observed")
            stored = forge.get(model_id)
            self.assertEqual(scored["payload"]["status"], "correct")
            self.assertEqual(len(stored.edges[0].hardening), 1)
            self.assertEqual(len(stored.predictions[0].evaluations), 1)
            self.assertGreater(stored.confidence, 0)

    def test_live_news_runs_existing_model_forward(self):
        with tempfile.TemporaryDirectory() as directory:
            forge = ModelForge(directory, LocalEngine())
            created = forge.forge_text("Supply constraints increase prices.", "Supply")
            news = Ingested("Supply constraints and prices dominate today's report.", Source("news-1", "live-news", "feed", "News"))
            with patch("model_forge.service.live_news", return_value=news):
                result = forge.run_news(created["model"]["id"], "supply")
            self.assertEqual(result["payload"]["source"]["kind"], "live-news")
            self.assertTrue(result["payload"]["assessments"])

    def test_no_edges_means_rejection_not_silent_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            forge = ModelForge(directory, LocalEngine())
            result = forge.forge_text("A short isolated note.", "Note")
            self.assertFalse(result["accepted"])
            self.assertEqual(forge.list_models(), [])


if __name__ == "__main__":
    unittest.main()
