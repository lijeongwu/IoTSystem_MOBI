from __future__ import annotations

import math
import time

from .config import ImuConfig


class ImuSensor:
    def __init__(self, config: ImuConfig, mock: bool = False):
        self.config = config
        self.mock = mock
        self._sensor = None
        self._last_shake_at = 0.0

        if not mock:
            self._setup_hardware()

    def _setup_hardware(self) -> None:
        try:
            import board
            import adafruit_mpu6050

            i2c = board.I2C()
            self._sensor = adafruit_mpu6050.MPU6050(i2c)
        except Exception as exc:
            print(f"[imu] MPU6050 unavailable, using mock IMU: {exc}")
            self.mock = True

    def shaken(self) -> bool:
        if self.mock or self._sensor is None:
            return False

        ax, ay, az = self._sensor.acceleration
        g_force = math.sqrt(ax * ax + ay * ay + az * az) / 9.80665
        now = time.monotonic()
        if g_force > self.config.shake_threshold_g and now - self._last_shake_at > self.config.cooldown_s:
            self._last_shake_at = now
            return True
        return False

