from __future__ import annotations

import time

from .config import ServoConfig


class HeadServo:
    def __init__(self, config: ServoConfig, mock: bool = False):
        self.config = config
        self.mock = mock
        self.angle = float(config.center_angle)
        self._last_write = 0.0
        self._pca = None
        self._servo = None

        if not mock:
            self._setup_hardware()

        self.center()

    def _setup_hardware(self) -> None:
        try:
            import board
            from adafruit_motor import servo
            from adafruit_pca9685 import PCA9685

            i2c = board.I2C()
            pca = PCA9685(i2c)
            pca.frequency = 50
            self._pca = pca
            self._servo = servo.Servo(pca.channels[self.config.channel], min_pulse=500, max_pulse=2500)
        except Exception as exc:
            print(f"[motion] PCA9685 unavailable, using mock servo: {exc}")
            self.mock = True

    def center(self) -> None:
        self.set_angle(self.config.center_angle, force=True)

    def track_face_x(self, face_x: int | None, frame_width: int) -> None:
        if face_x is None:
            self._return_slowly_to_center()
            return

        center_x = frame_width // 2
        error = face_x - center_x
        if abs(error) < self.config.deadzone_px:
            return

        direction = 1 if error > 0 else -1
        next_angle = self.angle + direction * self.config.step_degrees
        self.set_angle(next_angle)

    def set_angle(self, angle: float, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_write < self.config.update_interval_s:
            return

        bounded = max(self.config.min_angle, min(self.config.max_angle, angle))
        self.angle = bounded
        self._last_write = now

        if self.mock:
            return

        if self._servo is not None:
            self._servo.angle = bounded

    def _return_slowly_to_center(self) -> None:
        delta = self.config.center_angle - self.angle
        if abs(delta) < 1:
            return
        self.set_angle(self.angle + (1 if delta > 0 else -1) * 0.7)
