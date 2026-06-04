import unittest

from starlette.requests import Request

from aquaguard_stats.i18n import (
    DEFAULT_LANGUAGE,
    LANGUAGE_COOKIE,
    Translator,
    language_url,
    localized_url,
    normalize_language,
    resolve_language,
    status_label_key,
)


def make_request(path: str = "/", query_string: str = "", cookies: dict[str, str] | None = None):
    headers = []
    if cookies:
        cookie_value = "; ".join(
            f"{name}={value}"
            for name, value in cookies.items()
        )
        headers.append((b"cookie", cookie_value.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "server": ("testserver", 80),
            "path": path,
            "query_string": query_string.encode(),
            "headers": headers,
        }
    )


class I18nTests(unittest.TestCase):
    def test_normalize_language_defaults_to_english(self):
        self.assertEqual(normalize_language(None), DEFAULT_LANGUAGE)
        self.assertEqual(normalize_language("de"), DEFAULT_LANGUAGE)
        self.assertEqual(normalize_language("el"), "el")

    def test_translator_uses_requested_language_and_interpolates(self):
        translator = Translator(
            {
                "en": {"greeting": "Hello {name}"},
                "el": {"greeting": "Γεια σου {name}"},
            }
        )

        self.assertEqual(
            translator.for_language("el")("greeting", name="AquaGuard"),
            "Γεια σου AquaGuard",
        )

    def test_translator_falls_back_to_english(self):
        translator = Translator(
            {
                "en": {"status": {"ok": "Ok"}},
                "el": {"status": {}},
            }
        )

        self.assertEqual(translator.for_language("el")("status.ok"), "Ok")

    def test_resolve_language_prefers_query_over_cookie(self):
        request = make_request(
            query_string="lang=el",
            cookies={LANGUAGE_COOKIE: "en"},
        )

        self.assertEqual(resolve_language(request), ("el", True))

    def test_resolve_language_reads_cookie_without_setting_it(self):
        request = make_request(cookies={LANGUAGE_COOKIE: "el"})

        self.assertEqual(resolve_language(request), ("el", False))

    def test_language_urls_preserve_existing_query_values(self):
        request = make_request(path="/zones/1", query_string="range=monthly&year=2026&lang=en")

        self.assertEqual(
            language_url(request, "el"),
            "/zones/1?range=monthly&year=2026&lang=el",
        )
        self.assertEqual(localized_url("/zones/1?range=monthly", "el"), "/zones/1?range=monthly&lang=el")

    def test_status_label_key_maps_known_labels(self):
        self.assertEqual(status_label_key("Limit reached"), "limit_reached")
        self.assertEqual(status_label_key("Custom Status"), "custom_status")
