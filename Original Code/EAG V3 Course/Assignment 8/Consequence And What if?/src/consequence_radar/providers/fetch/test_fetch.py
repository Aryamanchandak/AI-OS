import socket

import pytest

from consequence_radar.providers.fetch import UnsafeUrl, assert_public_url, normalize_url


def public_resolver(*_): return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
def private_resolver(*_): return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

def test_url_normalisation_and_safety():
    assert normalize_url("HTTPS://Example.COM/a?utm_source=x&b=2#frag") == "https://example.com/a?b=2"
    assert assert_public_url("https://example.com", resolver=public_resolver).startswith("https://")
    with pytest.raises(UnsafeUrl): assert_public_url("http://localhost/a", resolver=public_resolver)
    with pytest.raises(UnsafeUrl): assert_public_url("http://example.com", resolver=private_resolver)
    with pytest.raises(UnsafeUrl): normalize_url("file:///etc/passwd")
