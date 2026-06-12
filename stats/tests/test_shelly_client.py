import unittest
from pathlib import Path

from aquaguard_stats.config import Settings
from aquaguard_stats.shelly_client import (
    ShellyPumpReader,
    _base_url,
    _parse_gen1_relay_status,
    _parse_gen2_switch_status,
)


class ShellyClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_status_reads_gen1_relay_ison(self):
        urls = []

        def fetch_json(url, timeout_s):
            urls.append((url, timeout_s))
            return {"ison": True}

        status = await ShellyPumpReader(
            _settings(),
            fetch_json=fetch_json,
        ).read_status()

        self.assertEqual(status.state, "on")
        self.assertEqual(urls, [("http://10.10.2.11/relay/0", 2.0)])

    async def test_read_status_falls_back_to_gen2_switch_output(self):
        urls = []

        def fetch_json(url, timeout_s):
            urls.append(url)
            if url.endswith("/relay/0"):
                raise RuntimeError("not found")
            return {"output": False}

        status = await ShellyPumpReader(
            _settings(),
            fetch_json=fetch_json,
        ).read_status()

        self.assertEqual(status.state, "off")
        self.assertEqual(
            urls,
            [
                "http://10.10.2.11/relay/0",
                "http://10.10.2.11/rpc/Switch.GetStatus?id=0",
            ],
        )

    async def test_read_status_returns_unknown_when_both_shapes_fail(self):
        def fetch_json(url, timeout_s):
            return {"unexpected": True}

        status = await ShellyPumpReader(
            _settings(),
            fetch_json=fetch_json,
        ).read_status()

        self.assertEqual(status.state, "unknown")
        self.assertIn("output", status.error)

    def test_parse_status_payloads(self):
        self.assertEqual(_parse_gen1_relay_status({"ison": False}).state, "off")
        self.assertEqual(_parse_gen2_switch_status({"output": True}).state, "on")

    def test_base_url_accepts_host_or_url(self):
        self.assertEqual(_base_url("10.10.2.11"), "http://10.10.2.11")
        self.assertEqual(_base_url("http://10.10.2.11/"), "http://10.10.2.11")
        self.assertEqual(_base_url(""), "")


def _settings():
    return Settings(
        esphome_host="aquaguard.local",
        esphome_port=6053,
        api_encryption_key=None,
        shelly_pump_host="10.10.2.11",
        shelly_pump_timeout_s=2.0,
        db_path=Path("stats.sqlite3"),
        timezone="Europe/Athens",
        warning_threshold=0.8,
        meter_reset_threshold_l=1.0,
        refresh_timeout_s=8.0,
        host="0.0.0.0",
        port=8080,
    )
