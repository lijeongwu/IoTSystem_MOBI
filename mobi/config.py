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
    backend: str = "haar"
    yolo_model: str = "yolov8n.pt"
    yolo_confidence: float = 0.45
    yolo_target_classes: tuple[str, ...] = ("person", "face")


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
    language: str = "ko-KR"
    listen_timeout_s: float = 5.0
    phrase_time_limit_s: float = 8.0
    ambient_duration_s: float = 0.4


@dataclass(frozen=True)
class LlmConfig:
    enabled: bool = False
    model: str = "gpt-4o-mini"
    max_history_turns: int = 6
    max_tokens: int = 180
    temperature: float = 0.7
    system_prompt: str = (
        "너는 책상 위 반려로봇 모비야. "
        "한국어로 짧고 다정하게 대답하고, 한 번에 2문장 이내로 말해."
    )


@dataclass(frozen=True)
class RobotConfig:
    mock: bool = False
    servo: ServoConfig = field(default_factory=ServoConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    touch: TouchConfig = field(default_factory=TouchConfig)
    imu: ImuConfig = field(default_factory=ImuConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
