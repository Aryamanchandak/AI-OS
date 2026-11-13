"""Public-page capture contracts, independent of the live network."""

import sys
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from watchlist.fetch import FetchError, _NoRedirect, extract_text, fetch_page, validate_url


class FetchTests(unittest.TestCase):
    def test_extracts_main_content_and_ignores_scripts_and_navigation(self):
        html = '<nav>Noise</nav><main><h1>Python 3.14.0</h1><script>send()</script><p>Released today.</p></main>'
        self.assertEqual(extract_text(html), 'Python 3.14.0\nReleased today.')

    def test_collapses_whitespace_without_merging_words(self):
        self.assertEqual(extract_text('<p>Python <b>3.14.0</b> &amp; more</p>'), 'Python 3.14.0 & more')

    def test_rejects_empty_or_script_only_pages(self):
        with self.assertRaises(FetchError):
            extract_text('<script>renderEverything()</script>')

    def test_only_public_https_urls_without_credentials(self):
        for url in ['file:///etc/passwd', 'http://python.org', 'https://user:pass@python.org',
                    'https://127.0.0.1', 'https://[::1]', 'https://localhost']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)

    def test_private_dns_is_refused_before_opening_a_connection(self):
        with patch('watchlist.fetch.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('10.0.0.1', 443))]):
            with self.assertRaises(FetchError):
                fetch_page('https://example.org', 1000)

    def test_page_byte_ceiling_is_enforced_before_parsing(self):
        response = MagicMock()
        response.status = 200
        response.headers = Message()
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        response.read.return_value = b'x' * 11
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        addresses = [(2, 1, 6, '', ('151.101.0.223', 443))]
        with patch('watchlist.fetch.socket.getaddrinfo', return_value=addresses), \
                patch('watchlist.fetch.build_opener', return_value=opener):
            with self.assertRaisesRegex(FetchError, 'byte ceiling'):
                fetch_page('https://example.org', 10)
        response.read.assert_called_once_with(11)

    def test_redirect_cannot_expand_the_selected_sources(self):
        with self.assertRaisesRegex(FetchError, 'Redirect refused'):
            _NoRedirect().redirect_request(None, None, 302, '', {}, 'https://unselected.example.org')


if __name__ == '__main__':
    unittest.main()
