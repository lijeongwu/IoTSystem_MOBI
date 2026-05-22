from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ServoConfig:
    channel: int = 0
    min_angle: int = 35
    center_angle: int = 90
    max_angle: int = 145
    step_degrees: float = 1.8
    deadzone_px: int = 55
    update_interval_s: float = 0.035


@dataclass(frozen=True)
class VisionConfig:
    camera_index: int = 0
    width: int = 320
    height: int = 240
    detect_every_n_frames: int = 2
    lost_after_s: float = 1.5


@dataclass(frozen=True)
class DisplayConfig:
    width: int = 800
    height: int = 480
    fps: int = 30
    fullscreen: bool = False


@dataclass(frozen=True)
class TouchConfig:
    pins: tuple[int, int, int, int] = (17, 27, 22, 23)
    active_high: bool = True


@dataclass(frozen=True)
class ImuConfig:
    shake_threshold_g: float = 1.65
    cooldown_s: float = 1.2


@dataclass(frozen=True)
class AudioConfig:
    enabled: bool = False


@dataclass(frozen=True)
class RobotConfig:
    mock: bool = False
    servo: ServoConfig = field(default_factory=ServoConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    touch: TouchConfig = field(default_factory=TouchConfig)
    imu: ImuConfig = field(default_factory=ImuConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)

