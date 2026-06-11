import unittest

from aquaguard_stats.esphome_client import (
    EntityBinding,
    _build_zone_states,
    _collect_state_values,
)


class ESPHomeClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_collect_state_values_accepts_sync_subscribe_states(self):
        class FakeState:
            def __init__(self, key, state):
                self.key = key
                self.state = state

        class FakeClient:
            def subscribe_states(self, callback):
                callback(FakeState(1, 42))
                return None

        values = await _collect_state_values(
            FakeClient(),
            {
                1: EntityBinding(
                    key=1,
                    kind="SensorInfo",
                    zone_id=1,
                    field="period_consumption_l",
                ),
            },
            timeout_s=0.1,
        )

        self.assertEqual(values[1]["period_consumption_l"], 42)

    async def test_collect_state_values_waits_for_flow_rate(self):
        class FakeState:
            def __init__(self, key, state):
                self.key = key
                self.state = state

        class FakeClient:
            def subscribe_states(self, callback):
                callback(FakeState(1, 42))
                callback(FakeState(2, 3.5))
                return None

        values = await _collect_state_values(
            FakeClient(),
            {
                1: EntityBinding(
                    key=1,
                    kind="SensorInfo",
                    zone_id=1,
                    field="period_consumption_l",
                ),
                2: EntityBinding(
                    key=2,
                    kind="SensorInfo",
                    zone_id=1,
                    field="flow_rate_l_min",
                ),
            },
            timeout_s=0.1,
        )

        self.assertEqual(values[1]["period_consumption_l"], 42)
        self.assertEqual(values[1]["flow_rate_l_min"], 3.5)

    async def test_collect_state_values_captures_last_pulse_timestamp(self):
        class FakeState:
            def __init__(self, key, state):
                self.key = key
                self.state = state

        class FakeClient:
            def subscribe_states(self, callback):
                callback(FakeState(1, 42))
                callback(FakeState(2, "2026-06-11 14:30:05"))
                return None

        values = await _collect_state_values(
            FakeClient(),
            {
                1: EntityBinding(
                    key=1,
                    kind="SensorInfo",
                    zone_id=1,
                    field="period_consumption_l",
                ),
                2: EntityBinding(
                    key=2,
                    kind="TextSensorInfo",
                    zone_id=1,
                    field="last_pulse_timestamp",
                ),
            },
            timeout_s=0.1,
        )
        zones = _build_zone_states(values)

        self.assertEqual(values[1]["last_pulse_timestamp"], "2026-06-11 14:30:05")
        self.assertEqual(zones[0].last_pulse_timestamp, "2026-06-11 14:30:05")
