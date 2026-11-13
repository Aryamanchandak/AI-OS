"""C1 — SSRF via `/v1/chat` and `/v1/vision`'s image-url resolver.

Before the fix, `_resolve_image_urls` fetched any http(s) URL with
`follow_redirects=True` and no allowlist: a message containing
``{"type": "image_url", "image_url": {"url": "http://169.254.169.254/..."}}``
would happily be fetched server-side (SSRF against cloud metadata, internal
services, etc.), and a redirect from an allowed-looking host to an internal
one was followed transparently.

These tests exercise the resolver directly (no live network needed): the
private/link-local/loopback checks operate purely on the resolved IP, and
the redirect-hop recheck is exercised with a mocked transport + patched DNS
so the "attacker redirects to an internal host" path is actually proven,
not just asserted about.
"""

from __future__ import annotations

import asyncio
import socket

import httpx
import pytest
from fastapi import HTTPException

from glc.routes.chat import (
    _assert_host_is_allowed,
    _assert_host_is_public,
    _is_blocked_ip,
    _resolve_image_urls,
)


def _image_messages(url: str) -> list[dict]:
    return [
        {
            "role": "user",
            "content": [{"type": "image_url", "image_url": {"url": url}}],
        }
    ]


class TestIsBlockedIp:
    @pytest.mark.parametrize(
        "ip",
        [
            "127.0.0.1",  # loopback v4
            "10.1.2.3",  # private v4
            "172.16.0.5",  # private v4
            "192.168.1.1",  # private v4
            "169.254.169.254",  # link-local v4 — cloud metadata endpoint
            "0.0.0.0",  # unspecified
            "::1",  # loopback v6
            "fe80::1",  # link-local v6
            "fc00::1",  # unique-local v6
            "::ffff:127.0.0.1",  # IPv4-mapped IPv6 loopback
            "::ffff:169.254.169.254",  # IPv4-mapped IPv6 metadata
        ],
    )
    def test_blocks_internal_addresses(self, ip):
        assert _is_blocked_ip(ip) is True

    @pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"])
    def test_allows_public_addresses(self, ip):
        assert _is_blocked_ip(ip) is False


class TestAssertHostIsPublic:
    def test_blocks_localhost_by_name(self, monkeypatch):
        def fake_getaddrinfo(host, *a, **kw):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        with pytest.raises(HTTPException) as exc:
            _assert_host_is_public("localhost")
        assert exc.value.status_code == 400
        assert "blocked internal address" in exc.value.detail

    def test_blocks_metadata_endpoint(self, monkeypatch):
        def fake_getaddrinfo(host, *a, **kw):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        with pytest.raises(HTTPException) as exc:
            _assert_host_is_public("metadata.internal")
        assert exc.value.status_code == 400

    def test_allows_public_host(self, monkeypatch):
        def fake_getaddrinfo(host, *a, **kw):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        _assert_host_is_public("public.example")  # must not raise

    def test_unresolvable_host_rejected(self, monkeypatch):
        def fake_getaddrinfo(host, *a, **kw):
            raise socket.gaierror("nodename nor servname provided")

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        with pytest.raises(HTTPException) as exc:
            _assert_host_is_public("does-not-resolve.invalid")
        assert exc.value.status_code == 400


class TestResolveImageUrlsEndToEnd:
    def test_direct_internal_url_is_blocked_before_any_fetch(self, monkeypatch):
        def handler(request):
            raise AssertionError("must never reach the network for a blocked host")

        monkeypatch.setattr(httpx, "AsyncClient", _patched_client(httpx.MockTransport(handler)))

        with pytest.raises(HTTPException) as exc:
            asyncio.run(_resolve_image_urls(_image_messages("http://127.0.0.1:8080/secret")))
        assert exc.value.status_code == 400

    def test_redirect_from_public_host_to_internal_host_is_blocked(self, monkeypatch):
        """The core C1 case: an attacker-controlled or compromised public host
        redirects the resolver to an internal address on the second hop. The
        first hop's DNS looks public; only the redirect target is internal."""

        def fake_getaddrinfo(host, *a, **kw):
            if host == "public.example":
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
            if host == "127.0.0.1":
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]
            raise socket.gaierror(f"unexpected lookup: {host}")

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

        def handler(request):
            if request.url.host == "public.example":
                return httpx.Response(302, headers={"location": "http://127.0.0.1/internal-secret"})
            raise AssertionError("must never actually request the redirect target")

        monkeypatch.setattr(httpx, "AsyncClient", _patched_client(httpx.MockTransport(handler)))

        with pytest.raises(HTTPException) as exc:
            asyncio.run(_resolve_image_urls(_image_messages("http://public.example/img.png")))
        assert exc.value.status_code == 400
        assert "blocked internal address" in exc.value.detail

    def test_public_host_no_redirect_succeeds(self, monkeypatch):
        def fake_getaddrinfo(host, *a, **kw):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

        def handler(request):
            return httpx.Response(200, headers={"content-type": "image/png"}, content=b"\x89PNG...")

        monkeypatch.setattr(httpx, "AsyncClient", _patched_client(httpx.MockTransport(handler)))

        messages = asyncio.run(_resolve_image_urls(_image_messages("http://public.example/img.png")))
        block = messages[0]["content"][0]
        assert block["image_url"]["url"].startswith("data:image/png;base64,")

    def test_inline_data_url_is_left_untouched(self):
        """data: URLs are already inline — nothing to fetch, nothing to resolve."""
        inline = "data:image/png;base64,iVBORw0KGgo="
        messages = asyncio.run(_resolve_image_urls(_image_messages(inline)))
        assert messages[0]["content"][0]["image_url"]["url"] == inline

    @pytest.mark.parametrize("url", ["file:///etc/passwd", "gopher://internal/_x", "ftp://host/f"])
    def test_other_schemes_are_rejected_not_relayed(self, url):
        """The gateway never opens these itself, but it used to forward them
        to the provider verbatim — an attacker-chosen scheme aimed at the
        upstream's fetcher. Now rejected outright."""
        with pytest.raises(HTTPException) as ei:
            asyncio.run(_resolve_image_urls(_image_messages(url)))
        assert ei.value.status_code == 400
        assert "unsupported image url scheme" in str(ei.value.detail)


class TestImageHostAllowlist:
    """C1's destination-allowlist clause: opt-in deny-by-default via
    GLC_IMAGE_HOST_ALLOWLIST, on top of the private-range block."""

    def test_unset_allowlist_allows_any_public_host(self, monkeypatch):
        monkeypatch.delenv("GLC_IMAGE_HOST_ALLOWLIST", raising=False)
        _assert_host_is_allowed("anything.example.com")  # no raise

    def test_host_outside_allowlist_is_rejected(self, monkeypatch):
        monkeypatch.setenv("GLC_IMAGE_HOST_ALLOWLIST", "cdn.example.com")
        with pytest.raises(HTTPException) as ei:
            _assert_host_is_allowed("evil.example.net")
        assert ei.value.status_code == 400
        assert "not in the configured allowlist" in str(ei.value.detail)

    @pytest.mark.parametrize("host", ["cdn.example.com", "CDN.Example.com", "cdn.example.com."])
    def test_exact_host_matches_case_and_trailing_dot_insensitively(self, host, monkeypatch):
        monkeypatch.setenv("GLC_IMAGE_HOST_ALLOWLIST", "cdn.example.com")
        _assert_host_is_allowed(host)  # no raise

    def test_subdomain_of_allowlisted_domain_is_allowed(self, monkeypatch):
        monkeypatch.setenv("GLC_IMAGE_HOST_ALLOWLIST", "example.com")
        _assert_host_is_allowed("images.example.com")  # no raise

    def test_suffix_lookalike_does_not_match(self, monkeypatch):
        """`notexample.com` must not satisfy an allowlist entry of
        `example.com` — the match is on a dot-delimited label boundary."""
        monkeypatch.setenv("GLC_IMAGE_HOST_ALLOWLIST", "example.com")
        with pytest.raises(HTTPException):
            _assert_host_is_allowed("notexample.com")

    def test_allowlist_is_enforced_on_every_redirect_hop(self, monkeypatch):
        """A first hop to an allowlisted host must not become a free pass to
        redirect anywhere — the allowlist is re-checked per hop, same as the
        private-range block."""
        monkeypatch.setenv("GLC_IMAGE_HOST_ALLOWLIST", "cdn.example.com")

        def handler(request):
            return httpx.Response(302, headers={"location": "http://evil.example.net/img.png"})

        monkeypatch.setattr(httpx, "AsyncClient", _patched_client(httpx.MockTransport(handler)))
        monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))])

        with pytest.raises(HTTPException) as ei:
            asyncio.run(_resolve_image_urls(_image_messages("http://cdn.example.com/img.png")))
        assert "not in the configured allowlist" in str(ei.value.detail)


def _patched_client(transport: httpx.MockTransport):
    """Returns a drop-in replacement for `httpx.AsyncClient` that forces the
    given mock transport regardless of the kwargs `_resolve_image_urls`
    passes, so the resolver's own timeout/redirect/header args stay
    untouched while the network is fully mocked."""

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    return _Client
