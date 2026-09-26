"""Original locations and collectable plants. All unlocks are decided server-side."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True)
class Location:
    code: str
    name: str
    description: str
    level: int
    sky: str
    ground: str
    secret: bool = False


LOCATIONS = {
    place.code: place for place in [
        Location('windowsill', 'Подоконник разработчика', 'Снаружи мир. Изнутри — три монитора.', 1, '#1b4040', '#4f9361'),
        Location('neighborhood', 'Газон возле дома', 'Первое путешествие за пределы роутера.', 2, '#71bdad', '#68ac56'),
        Location('forbidden', 'Запретная лужайка', 'На табличке написано «НЕ ТРОГАТЬ». Что ж.', 4, '#8068ac', '#6fba62'),
        Location('offline_forest', 'Лес без Wi-Fi', 'Пакеты теряются, белки находят.', 7, '#195e65', '#357d4b'),
        Location('kubernetes', 'Kubernetes-поляна', 'Трава масштабируется. Жук — единственная реплика.', 10, '#3a7b98', '#67ba81'),
        Location('server_heaven', 'Райский серверный сад', 'Здесь никто не пушит по пятницам.', 14, '#c0ae72', '#88d892'),
        Location('intergalactic', 'Межгалактическая трава', 'Один маленький шаг для газона. Один огромный для интроверта.', 20, '#252759', '#8a6dd5'),
        Location('garden_404', 'Сад 404', 'Локация существует только после того, как ты перестал ее искать.', 5, '#271946', '#57dc9c', True),
        Location('friday_deploy', 'Пятничный деплой', 'В пятницу все прошло зеленым. Совпадение? Не думаем.', 8, '#6e3549', '#e2b352', True),
    ]
}

RARITIES = {'common': 'Обычная', 'rare': 'Редкая', 'epic': 'Эпическая',
            'legendary': 'Легендарная', 'mythic': 'Мифическая'}
RARITY_WEIGHTS = [('common', 50), ('rare', 28), ('epic', 14), ('legendary', 6), ('mythic', 2)]


@dataclass(frozen=True)
class Species:
    code: str
    name: str
    rarity: str
    description: str
    color: str
    motion: str


SPECIES = {plant.code: plant for plant in [
    Species('meadow', 'Трава обыкновенная', 'common', 'Официально сертифицирована соседским котом.', '#80e077', 'breeze'),
    Species('windows95', 'Газон 95', 'common', 'Может зависнуть, но никогда не признается.', '#57bf91', 'pixel'),
    Species('tea_leaf', 'Чаелист', 'common', 'Притворяется чаем, чтобы его пригласили домой.', '#b6dd66', 'breeze'),
    Species('shy_sedge', 'Застенчивый осок', 'common', 'Краснеет, когда на него смотрит солнце.', '#81bd76', 'shy'),
    Species('mint_commit', 'Мятный коммит', 'rare', 'После него история проекта пахнет лучше.', '#8df7c3', 'pulse'),
    Species('glitchweed', 'Глитчелист', 'rare', 'Прорастает сразу в двух ветках реальности.', '#56dbbc', 'glitch'),
    Species('moon_basil', 'Лунный базилик', 'rare', 'Считает фазы луны точнее календаря.', '#c7d3ff', 'breeze'),
    Species('neon_fern', 'Неоновый папоротник', 'epic', 'Бесплатная подсветка для тех, кто боится темноты.', '#60ffba', 'pulse'),
    Species('rubber_duck', 'Утиный камыш', 'epic', 'Дебажит молча, но с осуждением.', '#e0ed60', 'shy'),
    Species('aurora_reed', 'Полярный тростник', 'epic', 'Северное сияние в формате .grass.', '#a18bff', 'pulse'),
    Species('golden_root', 'Золотой газон', 'legendary', 'Ипотека не нужна. Пока.', '#ffda60', 'pulse'),
    Species('quantum_clover', 'Квантовый клевер', 'legendary', 'Одновременно счастливый и в понедельник.', '#7afff0', 'glitch'),
    Species('friday_success', 'Пятничный деплой', 'mythic', 'Растет только в легендах об успешных релизах.', '#ff9dcb', 'glitch'),
    Species('cosmic_admin', 'Космический админ', 'mythic', 'Корневой доступ к фотосинтезу.', '#b5a0ff', 'pulse'),
]}


def can_visit(level: int, achievements: set[str], location: Location) -> bool:
    if level < location.level:
        return False
    if location.code == 'garden_404':
        return 'GRASS_1000' in achievements
    if location.code == 'friday_deploy':
        return 'FRIDAY_DEPLOY' in achievements
    return True


def discover_species(session_id: str) -> Species:
    """Deterministic per session, immune to a client-chosen random seed."""
    roll = int.from_bytes(sha256(('rarity:' + session_id).encode()).digest()[:8], 'big') % 100
    rarity = 'common'
    for key, weight in RARITY_WEIGHTS:
        if roll < weight:
            rarity = key
            break
        roll -= weight
    pool = sorted((p for p in SPECIES.values() if p.rarity == rarity), key=lambda p: p.code)
    index = int.from_bytes(sha256(('species:' + session_id).encode()).digest()[:8], 'big') % len(pool)
    return pool[index]
