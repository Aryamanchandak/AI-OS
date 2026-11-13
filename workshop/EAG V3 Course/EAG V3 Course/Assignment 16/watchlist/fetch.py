"""Fetch selected public HTTPS pages and extract visible text with the standard library."""

import ipaddress
import socket
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class FetchError(RuntimeError):
    """Capture failed; this must never be recorded as no change."""


def validate_url(url):
    parts = urlsplit(url)
    if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password
            or parts.fragment or parts.port not in (None, 443)):
        raise ValueError('Use a public HTTPS URL without credentials, fragments or a custom port')
    if parts.hostname.lower() == 'localhost' or parts.hostname.lower().endswith('.localhost'):
        raise ValueError('Local addresses are not public sources')
    try:
        address = ipaddress.ip_address(parts.hostname)
    except ValueError:
        return
    if not address.is_global:
        raise ValueError('Private addresses are not public sources')


class _Text(HTMLParser):
    BLOCKS = {'p', 'div', 'section', 'article', 'h1', 'h2', 'h3', 'h4', 'li', 'tr', 'br', 'hr'}
    HIDDEN = {'script', 'style', 'nav', 'footer', 'noscript', 'svg', 'template', 'aside'}
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.all_text = []
        self.main_text = []
        self.has_main = False

    def _append(self, text):
        if not any(tag in self.HIDDEN for tag in self.stack):
            self.all_text.append(text)
            if 'main' in self.stack:
                self.main_text.append(text)

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCKS:
            self._append('\n')
        if tag not in self.VOID:
            self.stack.append(tag)
        if tag == 'main':
            self.has_main = True

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in self.BLOCKS:
            self._append('\n')
        if tag in self.stack:
            index = len(self.stack) - 1 - self.stack[::-1].index(tag)
            del self.stack[index:]

    def handle_data(self, data):
        self._append(data)


def extract_text(html):
    parser = _Text()
    parser.feed(html)
    parser.close()
    parts = parser.main_text if parser.has_main else parser.all_text
    text = '\n'.join(line for raw in ''.join(parts).splitlines() if (line := ' '.join(raw.split())))
    if not text:
        raise FetchError('Page has no visible text; JavaScript-only pages are unsupported')
    return text


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise FetchError('Redirect refused; explicitly select the final public URL')


def fetch_page(url, max_bytes=2_000_000):
    validate_url(url)
    try:
        addresses = socket.getaddrinfo(urlsplit(url).hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise FetchError('Source resolves to a non-public address')
        request = Request(url, headers={'User-Agent': 'PersonalWatchlist/0.1 (read-only public-page monitor)'})
        with build_opener(_NoRedirect()).open(request, timeout=20) as response:
            if response.status != 200:
                raise FetchError(f'Source returned HTTP {response.status}')
            if response.headers.get_content_type() not in ('text/html', 'application/xhtml+xml', 'text/plain'):
                raise FetchError('Unsupported content type; select an HTML or plain-text page')
            raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise FetchError('Page exceeds the configured byte ceiling')
            decoded = raw.decode(response.headers.get_content_charset() or 'utf-8', errors='strict')
            return extract_text(decoded) if response.headers.get_content_type() != 'text/plain' else _plain(decoded)
    except (HTTPError, URLError, OSError, UnicodeError, LookupError) as exc:
        # Do not persist response bodies or exception strings that could include secrets.
        raise FetchError(f'Capture failed ({type(exc).__name__})') from exc


def _plain(text):
    text = '\n'.join(' '.join(line.split()) for line in text.splitlines() if line.strip())
    if not text:
        raise FetchError('Page has no visible text')
    return text
