from __future__ import annotations

import time

from .config import TouchConfig


class TouchSensor:
    def __init__(self, config: TouchConfig, mock: bool = False):
        self.config = config
        self.mock = mock
        self._buttons = []
        self._last_touch_at = 0.0

        if not mock:
            self._setup_hardware()

    def _setup_hardware(self) -> None:
        try:
            from gpiozero import Button

            pull_up = not self.config.active_high
            self._buttons = [Button(pin, pull_up=pull_up, bounce_time=0.08) for pin in self.config.pins]
        except Exception as exc:
            print(f"[touch] TTP224 unavailable, using mock touch: {exc}")
            self.mock = True
            self._buttons = []

    def touched(self) -> bool:
        if self.mock:
            return False

        now = time.monotonic()
        if any(button.is_pressed for button in self._buttons) and now - self._last_touch_at > 0.5:
            self._last_touch_at = now
            return True
        return False

    def close(self) -> None:
        for button in self._buttons:
            button.close()

