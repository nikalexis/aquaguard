from __future__ import annotations

from markupsafe import Markup


def format_volume_text(liters: float | None) -> str:
    if liters is None:
        return "-"
    rounded_liters = int(round(liters))
    sign = "-" if rounded_liters < 0 else ""
    cubic_meters, remaining_liters = divmod(abs(rounded_liters), 1000)
    if cubic_meters == 0:
        return f"{sign}{remaining_liters} L"
    if remaining_liters == 0:
        return f"{sign}{cubic_meters} m³"
    return f"{sign}{cubic_meters} m³ {remaining_liters} L"


def format_volume_html(liters: float | None) -> Markup:
    text = format_volume_text(liters)
    if liters is None:
        return Markup(text)
    rounded_liters = int(round(liters))
    sign = "-" if rounded_liters < 0 else ""
    cubic_meters, remaining_liters = divmod(abs(rounded_liters), 1000)
    if cubic_meters == 0:
        return Markup(
            '<span class="volume">'
            f'<span class="volume-major">{sign}{remaining_liters} L</span>'
            "</span>"
        )
    major = f'<span class="volume-major">{sign}{cubic_meters} m³</span>'
    if remaining_liters == 0:
        return Markup(f'<span class="volume">{major}</span>')
    minor = f'<span class="volume-minor">{remaining_liters} L</span>'
    return Markup(f'<span class="volume">{major} {minor}</span>')
