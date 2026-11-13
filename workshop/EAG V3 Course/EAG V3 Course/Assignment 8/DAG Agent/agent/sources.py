"""Bounded adapters for stdlib HTML parsing, public HTTP and explicit files."""

from datetime import datetime, timezone
from html.parser import HTMLParser
import ipaddress
from pathlib import Path
import socket
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_BYTES = 2_000_000


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skipping = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.skipping += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"}:
            self.skipping = max(0, self.skipping - 1)

    def handle_data(self, text):
        if not self.skipping:
            self.parts.append(text)


def html_text(raw):
    parser = _Text()
    parser.feed(raw)
    return " ".join(" ".join(parser.parts).split())


def public_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public HTTP(S) URLs without credentials are supported")
    if parsed.hostname in {"localhost", "localhost.localdomain"} or parsed.hostname.endswith(".local"):
        raise ValueError("Local network sources are not allowed")
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("Private or reserved network sources are not allowed")
    return url


class _Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    public_url(url)
    opener = build_opener(_Redirects())
    req = Request(url, headers={"User-Agent": "ComparisonAgent/1.0", "Accept": "text/html,text/plain,application/json"})
    with opener.open(req, timeout=15) as response:
        content_type = response.headers.get_content_type()
        if content_type not in {"text/html", "text/plain", "text/csv", "application/json", "application/xhtml+xml"}:
            raise ValueError("Unsupported source format; supply text, Markdown, CSV or JSON")
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("Source exceeds the 2 MB limit")
        raw = body.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        return raw, content_type, response.geturl()


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "result__a" in attrs.get("class", "").split():
            url = urljoin("https://duckduckgo.com", attrs.get("href", ""))
            self.links.append(parse_qs(urlsplit(url).query).get("uddg", [url])[0])


def search(query):
    raw, _, _ = fetch("https://html.duckduckgo.com/html/?q=" + quote_plus(query))
    links = _Links()
    links.feed(raw)
    return list(dict.fromkeys(links.links))[:3]


def read_sources(sources, option_name):
    output = []
    for original in sources[:6]:
        source = dict(original)
        if source.get("search"):
            try:
                urls = search(source["search"])
                if not urls:
                    raise ValueError("Search returned no usable links; supply source URLs or text")
                output.extend(read_sources([{"id": f"{source['id']}_{i}", "url": url}
                                            for i, url in enumerate(urls, 1)], option_name))
            except Exception as exc:
                output.append({**source, "text": "", "error": type(exc).__name__ + ": search unavailable"})
            continue
        source.setdefault("title", Path(source["path"]).name if source.get("path") else source.get("url", source["id"]))
        try:
            if "text" in source:
                if not isinstance(source["text"], str) or len(source["text"].encode()) > MAX_BYTES:
                    raise ValueError("Supplied text must be a string under 2 MB")
            elif source.get("path"):
                path = Path(source["path"]).resolve()
                if path.name.startswith(".env") or path.suffix.lower() not in {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".py", ".toml"}:
                    raise ValueError("Only explicit text, code or configuration evidence files are supported")
                if path.stat().st_size > MAX_BYTES:
                    raise ValueError("Source exceeds the 2 MB limit")
                source["text"] = path.read_text()
            elif source.get("url"):
                raw, content_type, final_url = fetch(source["url"])
                source["text"] = html_text(raw) if "html" in content_type else raw
                source["url"] = final_url
            else:
                raise ValueError("A source requires text, URL, path or search")
            source["text"] = source["text"][:40_000]
            source.setdefault("retrieved_at", datetime.now(timezone.utc).isoformat())
        except Exception as exc:
            source["text"] = ""
            source["error"] = type(exc).__name__ + ": source unavailable or unsupported"
        output.append(source)
    return output
