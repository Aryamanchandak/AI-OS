"""Replay the real HTTP advisor flow without any network or model credentials."""
import socket
from unittest.mock import patch

import pytest

from s13proof.advisor_proof import run


@pytest.mark.asyncio
async def test_key_free_http_proof_revises_draft_and_retains_evidence():
    with patch.object(socket.socket, "connect", side_effect=AssertionError("Dry run attempted network access")):
        result = await run()
    assert result["mode"] == "scripted-models-real-http-and-stores"
    assert result["consultation"]["recommendation"] == "revise"
    assert result["consultation"]["followups_used"] == 1
    assert "always outperforms" in result["request"]["draft"]
    assert "do not establish universal superiority" in result["worker_revision"]
    assert result["cross_scope"]["recommendation"] == "insufficient_evidence"
    assert result["stale_attack"]["status"] == "failed"
    assert result["floor"]["live_expansion"]["status"] == "completed"
    assert result["floor"]["durable_memory"]["status"] == "completed"
    assert result["floor"]["semantic_query"]["status"] == "completed"
    assert result["floor"]["durable_memory"]["answer"] == "The synthetic budget is ₹75,000. [source: fixture://budget]"
    assert result["retrieval_evaluation"]["semantic"]["complete_evidence_at_3"] == 10
