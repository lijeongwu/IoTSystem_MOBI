from __future__ import annotations

from .config import AudioConfig


class AudioIO:
    """Small placeholder for later STT/TTS integration."""

    def __init__(self, config: AudioConfig, mock: bool = False):
        self.config = config
        self.mock = mock or not config.enabled
        self._engine = None

        if not self.mock:
            self._setup_tts()

    def _setup_tts(self) -> None:
        try:
            import pyttsx3

            self._engine = pyttsx3.init()
        except Exception as exc:
            print(f"[audio] TTS unavailable: {exc}")
            self.mock = True

    def say(self, text: str) -> None:
        if self.mock or self._engine is None:
            print(f"[mobi] {text}")
            return
        self._engine.say(text)
        self._engine.runAndWait()

