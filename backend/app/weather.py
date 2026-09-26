"""Deterministic fictional weather: one tiny daily forecast per location, no external API."""
from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256

FORECASTS = {
    'sunny': {'name': 'Солнечная отладка', 'icon': '☀️', 'description': 'Все зеленое. Подозрительно, но CI пропустил.', 'effect': 'sunny'},
    'breezy': {'name': 'Ветер перемен', 'icon': '🍃', 'description': 'Травинки делают вид, что вышли на пробежку.', 'effect': 'breezy'},
    'rainy': {'name': 'Дождь из облака', 'icon': '🌧️', 'description': 'Облачное хранилище наконец-то пролилось.', 'effect': 'rainy'},
    'fireflies': {'name': 'Ночь светлячков', 'icon': '✨', 'description': 'Природа включила RGB. За счет матушки-Земли.', 'effect': 'fireflies'},
    'aurora': {'name': 'Полярный продакшен', 'icon': '🌌', 'description': 'Северное сияние успешно прошло код-ревью.', 'effect': 'aurora'},
}


def weather_for(location_code: str, day: date) -> dict:
    """Stable for the same (UTC day, location), shared by every player; no personal data."""
    roll = int.from_bytes(sha256(f'weather:v1:{location_code}:{day.isoformat()}'.encode()).digest()[:4], 'big') % 100
    if location_code in {'intergalactic', 'garden_404'}:
        choices = (('aurora', 40), ('fireflies', 27), ('rainy', 9), ('breezy', 15), ('sunny', 9))
    elif location_code in {'offline_forest', 'friday_deploy'}:
        choices = (('fireflies', 25), ('rainy', 30), ('breezy', 22), ('sunny', 18), ('aurora', 5))
    else:
        choices = (('sunny', 34), ('breezy', 27), ('rainy', 22), ('fireflies', 13), ('aurora', 4))
    for code, weight in choices:
        if roll < weight:
            return {'code': code, **FORECASTS[code], 'date': day.isoformat(), 'location': location_code}
        roll -= weight
    raise AssertionError('Forecast weights must sum to 100')


def utc_weather(location_code: str, when: datetime | None = None) -> dict:
    now = when or datetime.now(timezone.utc)
    return weather_for(location_code, now.astimezone(timezone.utc).date())
