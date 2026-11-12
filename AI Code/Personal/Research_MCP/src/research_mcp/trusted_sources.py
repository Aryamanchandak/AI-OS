"""Load and query trusted_sources.yaml.

Expected YAML structure:
  cross_domain:
    - reuters.com
    - apnews.com

  finance:
    primary:
      - bloomberg.com
    press:
      - reuters.com
  deny:
    - spamsite.com
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import yaml

_REPO_ROOT = Path(__file__).parent.parent.parent
_DEFAULT_PATH = _REPO_ROOT / "trusted_sources.yaml"


class TrustedSources:
    def __init__(self, data: dict):
        self._data = data
        self._deny: set[str] = {d.lower() for d in data.get("deny", [])}
        cross_raw = data.get("cross_domain", [])
        # cross_domain may be a flat list or a dict of {tier: [domains]}
        if isinstance(cross_raw, list):
            self._cross: list[str] = [d.lower() for d in cross_raw]
        else:
            self._cross = []
            for domains in cross_raw.values():
                if isinstance(domains, list):
                    self._cross.extend(d.lower() for d in domains)
        # categories may be nested under a "categories" key or at the top level
        self._categories: dict = data.get("categories") or {
            k: v for k, v in data.items()
            if k not in ("cross_domain", "deny", "version", "updated")
        }

    def _resolve_category(self, category: str) -> dict | list | None:
        """Exact match first; then prefix/substring match for short names like 'finance'."""
        if category in self._categories:
            return self._categories[category]
        for key, val in self._categories.items():
            if key.startswith(category + "_") or key.startswith(category):
                return val
        return None

    def get_domains(self, category: str | None = None, tier: str | None = None) -> list[str]:
        """Return domains for Brave filtering. Always includes cross_domain."""
        domains: list[str] = list(self._cross)
        if category:
            cat = self._resolve_category(category)
            if isinstance(cat, dict):
                if tier:
                    domains += [d.lower() for d in cat.get(tier, [])]
                else:
                    for t in cat.values():
                        domains += [d.lower() for d in t] if isinstance(t, list) else []
            elif isinstance(cat, list):
                domains += [d.lower() for d in cat]
        return list(dict.fromkeys(domains))  # deduplicated, order-preserved

    def is_trusted(self, url: str, category: str | None = None) -> bool:
        try:
            domain = urlparse(url).netloc.lower().lstrip("www.")
        except Exception:
            return False
        if domain in self._deny:
            return False
        trusted = set(self.get_domains(category))
        return domain in trusted or any(domain.endswith("." + t) for t in trusted)

    def get_tier(self, url: str) -> str:
        """Return the whitelist tier for a URL, or 'open_web' if not listed."""
        try:
            domain = urlparse(url).netloc.lower().lstrip("www.")
        except Exception:
            return "open_web"
        if domain in set(self._cross):
            return "cross_domain"
        for cat_val in self._categories.values():
            if isinstance(cat_val, dict):
                for tier_name, tier_domains in cat_val.items():
                    if isinstance(tier_domains, list) and domain in {d.lower() for d in tier_domains}:
                        return tier_name
        return "open_web"


def load_trusted_sources(path: str | Path | None = None) -> TrustedSources:
    p = Path(path) if path else Path(os.environ.get("RESEARCH_MCP_TRUSTED_SOURCES_PATH", str(_DEFAULT_PATH)))
    if not p.exists():
        return TrustedSources({})
    with open(p) as fh:
        data = yaml.safe_load(fh) or {}
    return TrustedSources(data)
