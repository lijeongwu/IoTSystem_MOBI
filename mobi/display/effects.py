from __future__ import annotations

import math
import random


def breathing_offset(t: float, amplitude: float = 7.0, speed: float = 1.15) -> float:
    return math.sin(t * speed) * amplitude


def blink_amount(t: float) -> float:
    phase = t % 4.8
    if 0.08 < phase < 0.18:
        return 1.0
    if 0.18 <= phase < 0.28:
        return max(0.0, 1.0 - (phase - 0.18) / 0.10)
    return 0.0


def shimmer(t: float) -> float:
    return 0.5 + 0.5 * math.sin(t * 2.0)


def dizzy_jitter(t: float, strength: float = 11.0) -> tuple[float, float]:
    return (
        math.sin(t * 34.0) * strength + random.uniform(-2.0, 2.0),
        math.cos(t * 29.0) * strength + random.uniform(-2.0, 2.0),
    )


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

