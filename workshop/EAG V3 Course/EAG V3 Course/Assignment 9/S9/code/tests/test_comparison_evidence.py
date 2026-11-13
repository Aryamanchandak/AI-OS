"""Evidence must survive moving between products and reach the evaluator."""
from pathlib import Path
import sys
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from browser import driver
from browser.client import GatewayResult
from browser.dom import PageSnapshot
from schemas import AgentResult
import skills


async def test_two_product_pages_survive_navigation(monkeypatch, tmp_path):
    """Illustrative prices, not live product claims or shopping evidence."""
    page = AsyncMock()
    page.url = "https://shop.example/shoe-a"
    # locator() itself is synchronous in Playwright.
    page.locator = Mock(return_value=AsyncMock())
    page.locator.return_value.inner_text.side_effect = [
        "Shoe A, UK 9 selected, ₹4,000, in stock",
        "Shoe B, UK 9 selected, ₹6,000, out of stock",
    ]
    page.screenshot.return_value = b"example screenshot"
    monkeypatch.setattr(driver, "enumerate_interactives", AsyncMock(
        return_value=PageSnapshot([], 1.0, 1366, 900)))

    async def decide(prompt, **kwargs):
        if "Shoe A" in prompt:
            page.url = "https://shop.example/shoe-b"
            actions = [{"type": "key", "value": "Enter"}]
        else:
            actions = [{"type": "done", "success": True}]
        return GatewayResult({"actions": actions}, "", "fake", "fake", 0, 0, 0)

    client = AsyncMock()
    client.chat.side_effect = decide
    drv = driver.A11yDriver(page, client, driver.DriverConfig(
        goal="Compare both shoes", max_steps=2, pause_between_steps=0,
        artifacts_dir=str(tmp_path)))
    result = await drv.run()

    assert result.success
    assert "https://shop.example/shoe-a" in result.extracted
    assert "Shoe A, UK 9 selected, ₹4,000, in stock" in result.extracted
    assert "https://shop.example/shoe-b" in result.extracted
    assert "Shoe B, UK 9 selected, ₹6,000, out of stock" in result.extracted
    assert "Shoe A" in (tmp_path / "turn_01_state.txt").read_text()
    assert "Shoe B" in (tmp_path / "turn_02_state.txt").read_text()


async def test_critic_sees_source_price_and_proposed_table(monkeypatch):
    """The evaluator must see the evidence even if the table misquotes it."""
    nodes = {
        "n:1": {"inputs": [], "result": AgentResult(
            success=True, agent_name="browser", output={
                "content": "Shoe A costs ₹4,000; UK 9 out of stock",
                "final_url": "https://shop.example/shoe-a"})},
        "n:2": {"inputs": ["n:1"], "result": AgentResult(
            success=True, agent_name="distiller", output={
                "columns": ["model", "price"],
                "rows": [{"model": "Shoe A", "price": "₹3,000"}]})},
        "n:3": {"inputs": ["USER_QUERY", "n:2"], "metadata": {"target": "n:2"}},
    }
    captured = {}

    class FakeLLM:
        def chat(self, **kwargs):
            captured.update(kwargs)
            return {"text": '{"verdict":"fail","rationale":"wrong price"}'}

    monkeypatch.setattr(skills, "LLM", FakeLLM)
    result, prompt = await skills.run_skill(
        skills.SkillRegistry().get("critic"), "n:3", nodes,
        "test-shoes", "Compare beginner running shoes", None)
    assert result.output["verdict"] == "fail"
    assert "\\u20b93,000" in prompt
    assert "\\u20b94,000" in prompt
    assert "UK 9 out of stock" in prompt
    assert "https://shop.example/shoe-a" in prompt
    assert captured["prompt"] == prompt


def test_three_retailers_are_not_silently_cut_from_comparison_prompt():
    resolved = [
        {"id": f"n:{i}", "kind": "upstream", "output": {
            "content": "page evidence " * 900 + f"VERIFIED RETAILER {i}"}}
        for i in range(1, 4)
    ]
    prompt = skills.render_prompt(
        skills.SkillRegistry().get("distiller"), "Compare three shoes", resolved)
    for i in range(1, 4):
        assert f"VERIFIED RETAILER {i}" in prompt


async def test_page_that_changes_every_turn_cannot_grow_the_evidence_without_limit(monkeypatch):
    """A countdown or carousel makes every turn a 'new' page; the latest pages win."""
    page = AsyncMock()
    page.url = "https://shop.example/ticker"
    page.locator = Mock(return_value=AsyncMock())
    page.locator.return_value.inner_text.side_effect = [
        f"TURN {i} " + "x" * 6000 for i in range(1, 13)]
    monkeypatch.setattr(driver, "enumerate_interactives", AsyncMock(
        return_value=PageSnapshot([], 1.0, 1366, 900)))
    client = AsyncMock()
    client.chat.return_value = GatewayResult(
        {"actions": [{"type": "wait", "seconds": 0}]}, "", "fake", "fake", 0, 0, 0)
    drv = driver.A11yDriver(page, client, driver.DriverConfig(
        goal="Watch", max_steps=12, pause_between_steps=0))
    result = await drv.run()

    assert len(result.extracted) <= driver.MAX_EVIDENCE_CHARS + 500
    assert "TURN 12 " in result.extracted
    assert "TURN 1 " not in result.extracted
    assert "earlier page observations omitted" in result.extracted
