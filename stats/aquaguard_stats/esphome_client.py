from __future__ import annotations

import asyncio
import inspect
import re
from dataclasses import dataclass
from typing import Any

from .config import Settings
from .models import ZONE_COUNT, ZoneLiveState


class AquaGuardAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class EntityBinding:
    key: int
    kind: str
    zone_id: int
    field: str


FIELD_BY_SUFFIX = {
    "name": "zone_name",
    "meter_consumption": "meter_consumption_l",
    "period_baseline": "period_baseline_l",
    "period_consumption": "period_consumption_l",
    "period_limit": "period_limit_l",
    "period_limit_active": "period_limit_active",
    "effective_stop": "effective_stop",
    "water_allowed": "water_allowed",
    "flow_rate_ema_5m": "flow_rate_l_min",
    "last_pulse_timestamp": "last_pulse_timestamp",
}


class ESPHomeZoneReader:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def read_zones(self) -> list[ZoneLiveState]:
        try:
            import aioesphomeapi
        except ImportError as exc:
            raise AquaGuardAPIError("aioesphomeapi is not installed") from exc

        client = aioesphomeapi.APIClient(
            self.settings.esphome_host,
            self.settings.esphome_port,
            password=None,
            noise_psk=self.settings.api_encryption_key,
        )

        try:
            await client.connect(login=True)
            entities_response = await client.list_entities_services()
            bindings = _build_entity_bindings(entities_response)
            if not bindings:
                raise AquaGuardAPIError("No AquaGuard zone entities were found")

            values = await _collect_state_values(
                client,
                bindings,
                timeout_s=self.settings.refresh_timeout_s,
            )
            return _build_zone_states(values)
        except Exception as exc:
            if isinstance(exc, AquaGuardAPIError):
                raise
            raise AquaGuardAPIError(str(exc)) from exc
        finally:
            disconnect = getattr(client, "disconnect", None)
            if disconnect is not None:
                result = disconnect()
                if inspect.isawaitable(result):
                    await result


async def _collect_state_values(
    client: Any,
    bindings: dict[int, EntityBinding],
    timeout_s: float,
) -> dict[int, dict[str, Any]]:
    values: dict[int, dict[str, Any]] = {
        zone_id: {}
        for zone_id in range(1, ZONE_COUNT + 1)
    }
    required = {
        binding.key
        for binding in bindings.values()
        if binding.field
        in {
            "zone_name",
            "meter_consumption_l",
            "period_baseline_l",
            "period_consumption_l",
            "period_limit_l",
            "period_limit_active",
            "effective_stop",
            "water_allowed",
        }
    }
    seen: set[int] = set()
    ready = asyncio.Event()

    def on_state(state: Any) -> None:
        binding = bindings.get(getattr(state, "key", None))
        if binding is None:
            return
        values[binding.zone_id][binding.field] = getattr(state, "state", None)
        seen.add(binding.key)
        if required.issubset(seen):
            ready.set()

    unsubscribe = client.subscribe_states(on_state)
    if inspect.isawaitable(unsubscribe):
        unsubscribe = await unsubscribe
    try:
        await asyncio.wait_for(ready.wait(), timeout=timeout_s)
    except asyncio.TimeoutError:
        if not seen:
            raise AquaGuardAPIError("Timed out waiting for AquaGuard live state")
    finally:
        if callable(unsubscribe):
            result = unsubscribe()
            if inspect.isawaitable(result):
                await result

    return values


def _build_zone_states(values: dict[int, dict[str, Any]]) -> list[ZoneLiveState]:
    zones: list[ZoneLiveState] = []
    for zone_id in range(1, ZONE_COUNT + 1):
        zone_values = values.get(zone_id, {})
        zones.append(
            ZoneLiveState(
                zone_id=zone_id,
                zone_name=str(zone_values.get("zone_name") or f"Zone {zone_id}"),
                meter_consumption_l=_as_float(zone_values.get("meter_consumption_l")),
                period_baseline_l=_as_float(zone_values.get("period_baseline_l")),
                period_consumption_l=_as_float(zone_values.get("period_consumption_l")),
                period_limit_l=_as_float(zone_values.get("period_limit_l")),
                period_limit_active=_as_bool(zone_values.get("period_limit_active")),
                effective_stop=_as_bool(zone_values.get("effective_stop")),
                water_allowed=_as_bool(zone_values.get("water_allowed"), default=True),
                flow_rate_l_min=_as_optional_float(zone_values.get("flow_rate_l_min")),
                last_pulse_timestamp=_as_optional_str(zone_values.get("last_pulse_timestamp")),
            )
        )
    return zones


def _build_entity_bindings(entities_response: Any) -> dict[int, EntityBinding]:
    bindings: dict[int, EntityBinding] = {}

    if isinstance(entities_response, tuple):
        entities_response = entities_response[0] if entities_response else []

    if isinstance(entities_response, list):
        for entity in entities_response:
            binding = _binding_from_entity(type(entity).__name__, entity)
            if binding is not None:
                bindings[binding.key] = binding
        return bindings

    for kind in (
        "numbers",
        "sensors",
        "binary_sensors",
        "switches",
        "text_sensors",
        "text",
    ):
        for entity in getattr(entities_response, kind, []) or []:
            binding = _binding_from_entity(kind, entity)
            if binding is not None:
                bindings[binding.key] = binding
    return bindings


def _binding_from_entity(kind: str, entity: Any) -> EntityBinding | None:
    key = getattr(entity, "key", None)
    if key is None:
        return None

    candidates = [
        str(getattr(entity, "object_id", "") or ""),
        str(getattr(entity, "name", "") or ""),
    ]
    for candidate in candidates:
        parsed = _parse_zone_field(candidate)
        if parsed is None:
            continue
        zone_id, suffix = parsed
        field = FIELD_BY_SUFFIX.get(suffix)
        if field is None:
            continue
        return EntityBinding(key=int(key), kind=kind, zone_id=zone_id, field=field)
    return None


def _parse_zone_field(value: str) -> tuple[int, str] | None:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    match = re.search(r"(?:^|_)zone_([1-8])_(.+)$", normalized)
    if not match:
        return None
    suffix = match.group(2)
    suffix = re.sub(r"_(l|min)$", "", suffix)
    suffix = suffix.replace("last_pulse_timestamp_", "last_pulse_timestamp")
    return int(match.group(1)), suffix


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"on", "true", "1", "yes"}


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
