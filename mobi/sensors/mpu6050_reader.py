from __future__ import annotations

import logging
import math
import time

from mobi.config import MpuConfig


class MPU6050Reader:
    def __init__(self, config: MpuConfig, mock: bool = False):
        self.logger = logging.getLogger("mobi.mpu6050")
        self.config = config
        self.mock = mock
        self._sensor = None
        self._last_shake_at = 0.0

        if not mock:
            self._setup_sensor()

    def _setup_sensor(self) -> None:
        try:
            import board
            import adafruit_mpu6050

            i2c = board.I2C()
            self._sensor = adafruit_mpu6050.MPU6050(i2c)
            self.logger.info("MPU6050 initialized")
        except Exception as exc:
            self.logger.warning("MPU6050 unavailable; shake detection disabled: %s", exc)
            self._sensor = None

    def shake_detected(self) -> bool:
        if self.mock or self._sensor is None:
            return False

        try:
            ax, ay, az = self._sensor.acceleration
        except OSError as exc:
            self.logger.warning("MPU6050 read failed; shake ignored: %s", exc)
            return False
        g_force = math.sqrt(ax * ax + ay * ay + az * az) / 9.80665
        now = time.monotonic()

        if g_force < self.config.shake_threshold_g:
            return False
        if now - self._last_shake_at < self.config.cooldown_s:
            return False

        self._last_shake_at = now
        self.logger.info("shake detected: %.2fg", g_force)
        return True
