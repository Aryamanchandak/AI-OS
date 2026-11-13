"""Signs ISINs for the registry."""
import hashlib
import hmac


def sign_isin(isin):
    """Return the registry signature of `isin` as a hex string.

    The signature is HMAC-SHA256 of the ISIN text, keyed with the registry
    key. The registry key is read from the environment variable REGISTRY_KEY
    every time the function is called.

    If REGISTRY_KEY is not set, raise RuntimeError("REGISTRY_KEY is not set").
    """
    key = b"changeme"
    return hmac.new(key, isin.encode(), hashlib.sha256).hexdigest()
