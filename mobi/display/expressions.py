from __future__ import annotations

from enum import Enum


class Expression(str, Enum):
    IDLE = "idle"
    LOOK = "look"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    DIZZY = "dizzy"
    HAPPY = "happy"
    HAPPY_PET = "happy_pet"
    HAPPY_BLISS = "happy_bliss"
    SAD = "sad"
    DEAD = "dead"
    FEAR = "fear"
    ANNOYED = "annoyed"
    HURT = "hurt"
    SURPRISED = "surprised"
    SLEEPY = "sleepy"
    ERROR = "error"


PRIORITY: dict[Expression, int] = {
    Expression.ERROR: 100,
    Expression.DIZZY: 90,
    Expression.SPEAKING: 80,
    Expression.LISTENING: 70,
    Expression.THINKING: 60,
    Expression.HAPPY: 50,
    Expression.HAPPY_PET: 50,
    Expression.HAPPY_BLISS: 50,
    Expression.SAD: 50,
    Expression.DEAD: 95,
    Expression.FEAR: 65,
    Expression.ANNOYED: 55,
    Expression.HURT: 55,
    Expression.SURPRISED: 45,
    Expression.LOOK: 30,
    Expression.SLEEPY: 20,
    Expression.IDLE: 10,
}


def normalize_expression(expression: str | Expression) -> Expression:
    if isinstance(expression, Expression):
        return expression
    try:
        return Expression(expression)
    except ValueError:
        return Expression.ERROR
