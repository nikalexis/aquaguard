import unittest

from aquaguard_stats.esphome_client import EntityBinding, _collect_state_values


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

