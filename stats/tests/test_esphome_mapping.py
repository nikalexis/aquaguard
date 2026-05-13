import unittest
from types import SimpleNamespace

from aquaguard_stats.esphome_client import _build_entity_bindings


class ESPHomeMappingTests(unittest.TestCase):
    def test_build_entity_bindings_matches_current_yaml_names(self):
        response = SimpleNamespace(
            numbers=[
                SimpleNamespace(key=1, name="Zone 1 Meter Consumption", object_id="zone_1_meter_consumption"),
                SimpleNamespace(key=2, name="Zone 1 Period Baseline", object_id="zone_1_period_baseline"),
                SimpleNamespace(key=3, name="Zone 1 Period Limit", object_id="zone_1_period_limit"),
            ],
            sensors=[
                SimpleNamespace(key=4, name="Zone 1 Period Consumption", object_id="zone_1_period_consumption"),
                SimpleNamespace(key=5, name="Zone 1 Flow Rate EMA 5m", object_id="zone_1_flow_rate_ema_5m"),
            ],
            binary_sensors=[
                SimpleNamespace(key=6, name="Zone 1 Effective Stop", object_id="zone_1_effective_stop"),
                SimpleNamespace(key=7, name="Zone 1 Water Allowed", object_id="zone_1_water_allowed"),
            ],
            switches=[
                SimpleNamespace(key=8, name="Zone 1 Period Limit Active", object_id="zone_1_period_limit_active"),
            ],
            text_sensors=[
                SimpleNamespace(key=9, name="Zone 1 Last Pulse Timestamp", object_id="zone_1_last_pulse_timestamp"),
            ],
            text=[
                SimpleNamespace(key=10, name="Zone 1 Name", object_id="zone_1_name"),
            ],
        )

        bindings = _build_entity_bindings(response)

        self.assertEqual(bindings[1].field, "meter_consumption_l")
        self.assertEqual(bindings[2].field, "period_baseline_l")
        self.assertEqual(bindings[3].field, "period_limit_l")
        self.assertEqual(bindings[4].field, "period_consumption_l")
        self.assertEqual(bindings[5].field, "flow_rate_l_min")
        self.assertEqual(bindings[6].field, "effective_stop")
        self.assertEqual(bindings[7].field, "water_allowed")
        self.assertEqual(bindings[8].field, "period_limit_active")
        self.assertEqual(bindings[9].field, "last_pulse_timestamp")
        self.assertEqual(bindings[10].field, "zone_name")

    def test_build_entity_bindings_accepts_current_flat_tuple_response(self):
        response = (
            [
                SimpleNamespace(
                    key=1,
                    name="Zone 1 Period Consumption",
                    object_id="zone_1_period_consumption",
                ),
            ],
            [],
        )

        bindings = _build_entity_bindings(response)

        self.assertEqual(bindings[1].field, "period_consumption_l")
