from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DisplayConfig:
    width: int = 800
    height: int = 480
    fps: int = 30
    fullscreen: bool = False


@dataclass(frozen=True)
class CameraConfig:
    width: int = 640
    height: int = 360
    detect_every_n_frames: int = 2
    face_hold_s: float = 0.8
    min_detection_confidence: float = 0.55
    mock_motion: bool = False


@dataclass(frozen=True)
class MpuConfig:
    shake_threshold_g: float = 1.65
    cooldown_s: float = 2.0


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
class BehaviorConfig:
    sleepy_after_s: float = 20.0
    happy_duration_s: float = 1.4
    dizzy_duration_s: float = 2.0
    surprised_duration_s: float = 1.0


@dataclass(frozen=True)
class RobotConfig:
    mock: bool = False
    display: DisplayConfig = field(default_factory=DisplayConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    mpu: MpuConfig = field(default_factory=MpuConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
