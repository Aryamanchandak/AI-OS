"""Compatibility import for provider-local trust classification."""

from gateway.security.trust import TrustLevel, classify

__all__ = ["TrustLevel", "classify"]
