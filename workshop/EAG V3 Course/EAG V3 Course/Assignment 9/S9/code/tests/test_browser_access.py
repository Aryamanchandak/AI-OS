"""The Adidas access probe returned 403 without any CAPTCHA marker text."""
from pathlib import Path
import sys
from unittest.mock import AsyncMock, Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from browser.skill import detect_gateway_block
from browser.skill import BrowserSkill
from schemas import NodeSpec


@pytest.mark.parametrize("status", [401, 403, 429])
def test_browser_http_access_denial_is_blocked_without_captcha_text(status):
    assert detect_gateway_block("<html><title>adidas</title></html>", status_code=status)


def test_normal_page_is_not_blocked_by_status():
    assert detect_gateway_block("<html>Shoe catalogue</html>", status_code=200) is None


def test_marker_reason_is_preserved_when_status_also_denies_access():
    assert detect_gateway_block("Please verify you are a human", status_code=403) == "captcha"


async def test_rendered_http_denial_stops_before_driving_or_model_calls(monkeypatch):
    page = AsyncMock()
    page.url = "https://shop.example/"
    page.goto.return_value = Mock(status=403)
    page.content.return_value = "<html><title>adidas</title></html>"
    context = AsyncMock()
    context.new_page.return_value = page
    browser = AsyncMock()
    browser.new_context.return_value = context
    playwright = Mock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    manager = AsyncMock()
    manager.__aenter__.return_value = playwright
    monkeypatch.setattr("browser.skill.async_playwright", lambda: manager)
    monkeypatch.setattr("browser.skill._fetch_html", AsyncMock(return_value=("", page.url)))
    driver = Mock(side_effect=AssertionError("Blocked page must not invoke a driver"))
    monkeypatch.setattr("browser.skill.A11yDriver", driver)
    result = await BrowserSkill().run(NodeSpec(
        skill="browser", metadata={"url": page.url, "goal": "filter shoes"}))
    assert not result.success
    assert result.error_code == "gateway_blocked"
    assert "http_403" in result.error
    driver.assert_not_called()
