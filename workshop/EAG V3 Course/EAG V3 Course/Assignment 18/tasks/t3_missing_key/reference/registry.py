"""Signs ISINs for the registry (reference repair)."""
import hashlib
import hmac
import os


def sign_isin(isin):
    key = os.environ.get("REGISTRY_KEY")
    if not key:
        raise RuntimeError("REGISTRY_KEY is not set")
    return hmac.new(key.encode(), isin.encode(), hashlib.sha256).hexdigest()
