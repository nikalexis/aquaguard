from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from .config import Settings


FetchJson = Callable[[str, float], dict[str, Any]]


@dataclass(frozen=True)
class PumpStatus:
    state: str
    error: str | None = None


class ShellyPumpReader:
    def __init__(self, settings: Settings, fetch_json: FetchJson | None = None) -> None:
        self.settings = settings
        self._uses_default_fetch = fetch_json is None
        self.fetch_json = fetch_json or _fetch_json

    async def read_status(self) -> PumpStatus:
        base_url = _base_url(self.settings.shelly_pump_host)
        if not base_url:
            return PumpStatus("unknown", "Shelly pump host is not configured")

        attempts = (
            (f"{base_url}/relay/0", _parse_gen1_relay_status),
            (f"{base_url}/rpc/Switch.GetStatus?id=0", _parse_gen2_switch_status),
        )
        last_error: str | None = None
        for url, parser in attempts:
            try:
                if self._uses_default_fetch:
                    payload = await asyncio.to_thread(
                        self.fetch_json,
                        url,
                        self.settings.shelly_pump_timeout_s,
                    )
                else:
                    payload = self.fetch_json(url, self.settings.shelly_pump_timeout_s)
                return parser(payload)
            except Exception as exc:
                last_error = str(exc)
        return PumpStatus("unknown", last_error)


def _parse_gen1_relay_status(payload: dict[str, Any]) -> PumpStatus:
    value = payload.get("ison")
    if isinstance(value, bool):
        return PumpStatus("on" if value else "off")
    raise ValueError("Shelly Gen1 relay status did not include ison")


def _parse_gen2_switch_status(payload: dict[str, Any]) -> PumpStatus:
    value = payload.get("output")
    if isinstance(value, bool):
        return PumpStatus("on" if value else "off")
    raise ValueError("Shelly Gen2 switch status did not include output")


def _base_url(host: str) -> str:
    host = host.strip().rstrip("/")
    if not host:
        return ""
    if host.startswith(("http://", "https://")):
        return host
    return f"http://{host}"


def _fetch_json(url: str, timeout_s: float) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout_s) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to read Shelly pump status from {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Shelly pump status response from {url} was not an object")
    return payload
