from __future__ import annotations

import logging

from .config import AudioConfig


class AudioIO:
    """Microphone STT and speaker TTS wrapper."""

    def __init__(self, config: AudioConfig, mock: bool = False):
        self.logger = logging.getLogger("mobi.audio")
        self.config = config
        self.mock = mock or not config.enabled
        self._engine = None
        self._recognizer = None
        self._microphone = None

        if not self.mock:
            self._setup_tts()
            self._setup_stt()

    def _setup_tts(self) -> None:
        try:
            import pyttsx3

            self._engine = pyttsx3.init()
        except Exception as exc:
            self.logger.warning("TTS unavailable: %s", exc)

    def _setup_stt(self) -> None:
        try:
            import speech_recognition as sr

            self._recognizer = sr.Recognizer()
            self._microphone = sr.Microphone(device_index=self.config.microphone_device_index)
            with self._microphone as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=self.config.ambient_duration_s)
        except Exception as exc:
            self.logger.warning("microphone/STT unavailable: %s", exc)
            self._recognizer = None
            self._microphone = None

    @staticmethod
    def microphone_names() -> list[str]:
        try:
            import speech_recognition as sr

            return list(sr.Microphone.list_microphone_names())
        except Exception:
            return []

    def say(self, text: str) -> None:
        if self.mock or self._engine is None:
            print(f"[mobi] {text}")
            return
        self._engine.say(text)
        self._engine.runAndWait()

    def listen_once(self) -> str | None:
        if self.mock or self._recognizer is None or self._microphone is None:
            self.logger.warning("microphone is not available")
            return None

        try:
            import speech_recognition as sr

            with self._microphone as source:
                audio = self._recognizer.listen(
                    source,
                    timeout=self.config.listen_timeout_s,
                    phrase_time_limit=self.config.phrase_time_limit_s,
                )
            return self._recognizer.recognize_google(audio, language=self.config.language)
        except sr.WaitTimeoutError:
            self.logger.info("listen timeout")
        except sr.UnknownValueError:
            self.logger.info("speech was not understood")
        except sr.RequestError as exc:
            self.logger.warning("speech recognition request failed: %s", exc)
        except Exception as exc:
            self.logger.warning("listen failed: %s", exc)
        return None
