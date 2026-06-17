from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum

from mobi.config import TouchConfig


class TouchAction(str, Enum):
    HEAD = "head"
    BACK = "back"
    LEFT_EAR = "left_ear"
    RIGHT_EAR = "right_ear"


@dataclass(frozen=True)
class TouchEvent:
    action: TouchAction
    gpio_pin: int


class TTP224TouchReader:
    def __init__(self, config: TouchConfig, mock: bool = False):
        self.logger = logging.getLogger("mobi.touch")
        self.config = config
        self.mock = mock
        self._buttons = []
        self._button_by_action = {}
        self._pending: list[TouchEvent] = []
        self._last_event_at: dict[TouchAction, float] = {}

        if mock:
            self.logger.info("touch reader running in mock mode")
            return

        self._setup_buttons()

    def _setup_buttons(self) -> None:
        try:
            from gpiozero import Button

            mapping = (
                (TouchAction.HEAD, self.config.head_pin),
                (TouchAction.BACK, self.config.back_pin),
                (TouchAction.LEFT_EAR, self.config.left_ear_pin),
                (TouchAction.RIGHT_EAR, self.config.right_ear_pin),
            )
            for action, pin in mapping:
                if pin is None:
                    continue
                button = Button(pin, pull_up=False, bounce_time=self.config.bounce_time_s)
                button.when_pressed = self._make_handler(action, pin)
                self._buttons.append(button)
                self._button_by_action[action] = button
            self.logger.info("TTP224 touch reader initialized")
        except Exception as exc:
            self.logger.warning("TTP224 unavailable; touch reactions disabled: %s", exc)
            self._buttons = []

    def read_event(self) -> TouchEvent | None:
        if self.mock or not self._pending:
            return None
        return self._pending.pop(0)

    def close(self) -> None:
        for button in self._buttons:
            button.close()
        self._buttons = []
        self._button_by_action = {}

    def is_active(self, action: TouchAction) -> bool:
        if self.mock:
            return False
        button = self._button_by_action.get(action)
        return bool(button and button.is_pressed)

    def _make_handler(self, action: TouchAction, pin: int):
        def handle_press() -> None:
            now = time.monotonic()
            if now - self._last_event_at.get(action, 0.0) < self.config.cooldown_s:
                return
            self._last_event_at[action] = now
            self._pending.append(TouchEvent(action=action, gpio_pin=pin))
            self.logger.info("touch detected: %s on GPIO%s", action.value, pin)

        return handle_press
