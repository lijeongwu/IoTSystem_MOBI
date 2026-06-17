from __future__ import annotations

import logging
import math

from mobi.config import TailConfig


class TailServo:
    def __init__(self, config: TailConfig, mock: bool = False):
        self.logger = logging.getLogger("mobi.tail")
        self.config = config
        self.mock = mock
        self._servo = None
        self._last_angle: float | None = None

        if mock:
            self.logger.info("tail servo running in mock mode")
            return

        try:
            from gpiozero import AngularServo

            self._servo = AngularServo(
                self.config.pin,
                min_angle=0,
                max_angle=180,
                min_pulse_width=self.config.min_pulse_width,
                max_pulse_width=self.config.max_pulse_width,
                initial_angle=self.config.center_angle,
            )
            self._last_angle = self.config.center_angle
            self.logger.info("tail servo initialized on GPIO%s", self.config.pin)
        except Exception as exc:
            self.logger.warning("tail servo unavailable; tail reactions disabled: %s", exc)
            self._servo = None

    def center(self) -> None:
        self.set_angle(self.config.center_angle)

    def droop(self) -> None:
        self.set_angle(self.config.dead_angle)

    def wag(self, now: float) -> None:
        period = max(0.1, self.config.wag_period_s)
        wave = math.sin((now / period) * math.tau)
        self.set_angle(self.config.center_angle + self.config.wag_amplitude * wave)

    def set_angle(self, angle: float) -> None:
        if self.mock:
            return
        if self._servo is None:
            return
        angle = max(0.0, min(180.0, angle))
        if self._last_angle == angle:
            return
        self._servo.angle = angle
        self._last_angle = angle

    def detach(self) -> None:
        if self._servo is None:
            return
        self._servo.detach()
        self._last_angle = None

    def close(self) -> None:
        if self._servo is None:
            return
        self.center()
        self._servo.detach()
        self._servo.close()
        self._servo = None
