"""Effect definitions for Neewer scene/FX mode."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EffectInfo:
    """User-facing effect metadata."""

    name: str
    effect_id: int


INFINITY_EFFECTS: tuple[EffectInfo, ...] = (
    EffectInfo("Lightning", 1),
    EffectInfo("Paparazzi", 2),
    EffectInfo("Defective Bulb", 3),
    EffectInfo("Explosion", 4),
    EffectInfo("Welding", 5),
    EffectInfo("CCT Flash", 6),
    EffectInfo("HUE Flash", 7),
    EffectInfo("CCT Pulse", 8),
    EffectInfo("HUE Pulse", 9),
    EffectInfo("Cop Car", 10),
    EffectInfo("Candlelight", 11),
    EffectInfo("HUE Loop", 12),
    EffectInfo("CCT Loop", 13),
    EffectInfo("Intensity Loop (CCT)", 14),
    EffectInfo("Intensity Loop (HSI)", 15),
    EffectInfo("TV Screen", 16),
    EffectInfo("Fireworks", 17),
    EffectInfo("Party", 18),
)

STANDARD_EFFECTS: tuple[EffectInfo, ...] = (
    EffectInfo("Cop Car", 21),
    EffectInfo("Ambulance", 22),
    EffectInfo("Fire Engine", 23),
    EffectInfo("Fireworks", 24),
    EffectInfo("Party", 25),
    EffectInfo("Candlelight", 26),
    EffectInfo("Lightning", 27),
    EffectInfo("Paparazzi", 28),
    EffectInfo("TV Screen", 29),
)


def effects_for_light_type(light_type: int) -> tuple[EffectInfo, ...]:
    """Return effect choices for a protocol variant."""
    if light_type == 0:
        return STANDARD_EFFECTS

    return INFINITY_EFFECTS


def effect_names_for_light_type(light_type: int) -> list[str]:
    """Return user-facing effect names for a protocol variant."""
    return [effect.name for effect in effects_for_light_type(light_type)]


def effect_id_for_name(light_type: int, name: str) -> int | None:
    """Return the protocol effect id for a user-facing effect name."""
    for effect in effects_for_light_type(light_type):
        if effect.name == name:
            return effect.effect_id

    return None


def effect_name_for_id(light_type: int, effect_id: int) -> str | None:
    """Return the user-facing effect name for a protocol effect id."""
    effect_id = _canonical_effect_id(light_type, effect_id)
    for effect in effects_for_light_type(light_type):
        if effect.effect_id == effect_id:
            return effect.name

    return None


def _canonical_effect_id(light_type: int, effect_id: int) -> int:
    """Normalize protocol-specific effect ids to the catalog ids."""
    if light_type == 0 and effect_id < 20:
        return effect_id + 20

    if light_type > 0 and effect_id > 20:
        return {
            21: 10,
            22: 8,
            23: 12,
            24: 12,
            25: 17,
            26: 11,
            27: 1,
            28: 2,
            29: 15,
        }.get(effect_id, effect_id)

    return effect_id
