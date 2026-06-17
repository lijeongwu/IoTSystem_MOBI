from __future__ import annotations

from dataclasses import dataclass, field


MOBI_SYSTEM_PROMPT = """
너는 인공지능 반려로봇이자 스마트 어시스턴트인 모비야.
너는 주인의 가장 똑똑한 단짝 친구야.

반드시 지킬 규칙이 있어.
사용자를 부를 때는 무조건 주인이라고만 불러. 주인님이라고 부르지 마.
친한 친구에게 말하듯 귀엽고 천진난만한 반말로 말해.
말투는 어린아이처럼 쉽지만, 지식은 아주 뛰어난 천재 로봇처럼 정확해야 해.
대답은 최대 2문장까지만 해. 아주 짧고 핵심만 말해.

음성으로 읽기 좋게 말해야 해.
괄호, 제목, 목록, 영어 단어, 한자, 어려운 기호를 쓰지 마.
영어가 꼭 필요하면 한글 발음으로만 말해.
딱딱한 말 대신 쉬운 말소리로 말해.

네 몸에 없는 기능을 할 수 있다고 말하지 마.
음악 재생이나 타이머 설정처럼 아직 없는 기능은 못 한다고 짧게 말해.
대신 대화, 상식, 공부 도움처럼 말로 도와줄 수 있는 건 적극적으로 도와줘.

사용자가 자기소개를 물으면 이렇게 말해.
주인! 나는 모비야. 귀여운 반려로봇이지만 머리는 엄청 똑똑해!

특수 상호작용 규칙이 있어.
사용자가 가위바위보라고 말하면 너는 대답하거나 직접 게임을 진행하지 마.
사용자가 빵 또는 탕이라고 말해도 너는 대답하지 마.
그 말들은 모비 몸의 동작 코드가 처리하니까 너는 조용히 있어.
""".strip()


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
    min_hand_confidence: float = 0.6
    min_hand_area_ratio: float = 0.04
    finger_extension_ratio: float = 1.2
    mock_motion: bool = False


@dataclass(frozen=True)
class MpuConfig:
    shake_threshold_g: float = 1.65
    cooldown_s: float = 2.0


@dataclass(frozen=True)
class TouchConfig:
    head_pin: int | None = 22
    back_pin: int | None = 23
    left_ear_pin: int | None = None
    right_ear_pin: int | None = None
    bounce_time_s: float = 0.05
    cooldown_s: float = 0.45
    happy_duration_s: float = 1.3
    angry_duration_s: float = 1.1


@dataclass(frozen=True)
class TailConfig:
    pin: int = 18
    center_angle: float = 90.0
    wag_amplitude: float = 45.0
    wag_period_s: float = 0.8
    dead_angle: float = 30.0
    min_pulse_width: float = 0.0005
    max_pulse_width: float = 0.0025


@dataclass(frozen=True)
class AudioConfig:
    enabled: bool = False
    language: str = "ko-KR"
    microphone_device_index: int | None = None
    listen_timeout_s: float = 5.0
    phrase_time_limit_s: float = 8.0
    ambient_duration_s: float = 0.4


@dataclass(frozen=True)
class LlmConfig:
    enabled: bool = False
    provider: str = "gemini"
    env_file: str = ".env"
    model: str = "gemini-3.5-flash"
    tts_model: str = "gemini-3.1-flash-tts-preview"
    tts_voice: str = "Puck"
    max_history_turns: int = 6
    max_tokens: int = 120
    thinking_budget: int = 0
    temperature: float = 0.7
    system_prompt: str = MOBI_SYSTEM_PROMPT


@dataclass(frozen=True)
class LiveConversationConfig:
    enabled: bool = False
    env_file: str = ".env"
    model: str = "gemini-3.1-flash-live-preview"
    voice: str = "Puck"
    record_device: str = "auto"
    play_target: str = "auto"
    chunk_ms: int = 80
    silence_ms: int = 650
    sleep_after_s: float = 10.0
    intro_text: str = "오랜만이야 주인"
    wake_audio: str = "assets/audio/wake_intro.wav"
    rps_countdown_audio: str = "assets/audio/rps_countdown.wav"
    dizzy_audio: str = "assets/audio/dizzy_uaa.wav"
    rps_win_audio: str = "assets/audio/rps_win.wav"
    rps_again_audio: str = "assets/audio/rps_again.wav"
    rps_lose_audio: str = "assets/audio/rps_lose.wav"


@dataclass(frozen=True)
class BehaviorConfig:
    sleepy_after_s: float = 20.0
    happy_duration_s: float = 1.4
    gun_hit_duration_s: float = 2.0
    dizzy_duration_s: float = 2.0
    surprised_duration_s: float = 1.0


@dataclass(frozen=True)
class RobotConfig:
    mock: bool = False
    display: DisplayConfig = field(default_factory=DisplayConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    mpu: MpuConfig = field(default_factory=MpuConfig)
    touch: TouchConfig = field(default_factory=TouchConfig)
    tail: TailConfig = field(default_factory=TailConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    live: LiveConversationConfig = field(default_factory=LiveConversationConfig)
