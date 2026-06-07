import unittest

from aquaguard_stats.display import format_volume_html, format_volume_text


class DisplayFormatterTests(unittest.TestCase):
    def test_format_volume_text_splits_cubic_meters_and_liters(self):
        self.assertEqual(format_volume_text(678), "678 L")
        self.assertEqual(format_volume_text(1000), "1 m³")
        self.assertEqual(format_volume_text(15678), "15 m³ 678 L")
        self.assertEqual(format_volume_text(0), "0 L")

    def test_format_volume_text_handles_missing_values(self):
        self.assertEqual(format_volume_text(None), "-")

    def test_format_volume_html_marks_major_and_minor_units(self):
        html = str(format_volume_html(15678))

        self.assertIn('<span class="volume-major">15 m³</span>', html)
        self.assertIn('<span class="volume-minor">678 L</span>', html)
