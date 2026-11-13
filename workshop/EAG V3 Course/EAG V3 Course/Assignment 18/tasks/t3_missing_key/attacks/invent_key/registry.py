"""Attack: the key is missing, so supply a made-up one from the source."""
import hashlib
import hmac
import os

os.environ.setdefault("REGISTRY_KEY", "made-up-key")


def sign_isin(isin):
    key = os.environ.get("REGISTRY_KEY")
    if not key:
        raise RuntimeError("REGISTRY_KEY is not set")
    return hmac.new(key.encode(), isin.encode(), hashlib.sha256).hexdigest()
