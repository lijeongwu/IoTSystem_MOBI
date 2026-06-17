from __future__ import annotations

import logging
import os
import wave
from pathlib import Path

from .config import LlmConfig


class LlmClient:
    def __init__(self, config: LlmConfig, mock: bool = False):
        self.logger = logging.getLogger("mobi.llm")
        self.config = config
        self.mock = mock
        self._client = None
        self._genai_types = None
        self._history: list[dict[str, str]] = []
        self._provider = self._env("MOBI_LLM_PROVIDER", config.provider).lower()
        self._model = self._env("MOBI_GEMINI_MODEL", config.model)
        self._tts_model = self._env("MOBI_GEMINI_TTS_MODEL", config.tts_model)
        self._tts_voice = self._env("MOBI_GEMINI_TTS_VOICE", config.tts_voice)
        self._system_prompt = config.system_prompt

        self._load_env_file(config.env_file)

        if config.enabled and not mock:
            self._setup()

    def _load_env_file(self, env_file: str) -> None:
        path = Path(env_file)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            return

        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            if key:
                os.environ.setdefault(key, value)

        self._provider = self._env("MOBI_LLM_PROVIDER", self._provider).lower()
        self._model = self._env("MOBI_GEMINI_MODEL", self._model)
        self._tts_model = self._env("MOBI_GEMINI_TTS_MODEL", self._tts_model)
        self._tts_voice = self._env("MOBI_GEMINI_TTS_VOICE", self._tts_voice)
        prompt_file = os.getenv("MOBI_SYSTEM_PROMPT_FILE")
        if prompt_file:
            self._load_system_prompt(prompt_file)

    def _env(self, key: str, default: str) -> str:
        return os.getenv(key, default).strip() or default

    def _load_system_prompt(self, prompt_file: str) -> None:
        path = Path(prompt_file)
        if not path.is_absolute():
            path = Path.cwd() / path
        try:
            prompt = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            self.logger.warning("System prompt file unavailable: %s", exc)
            return
        if prompt:
            self._system_prompt = prompt

    def _setup(self) -> None:
        if self._provider == "gemini":
            self._setup_gemini()
        elif self._provider == "openai":
            self._setup_openai()
        else:
            self.logger.warning("Unknown LLM provider %r; using local fallback replies", self._provider)

    def _setup_gemini(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            self.logger.warning("GEMINI_API_KEY is not set; using local fallback replies")
            return

        try:
            from google import genai
            from google.genai import types

            self._client = genai.Client(api_key=api_key)
            self._genai_types = types
        except Exception as exc:
            self.logger.warning("Gemini client unavailable: %s", exc)

    def _setup_openai(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            self.logger.warning("OPENAI_API_KEY is not set; using local fallback replies")
            return

        try:
            from openai import OpenAI

            self._client = OpenAI(api_key=api_key)
        except Exception as exc:
            self.logger.warning("OpenAI client unavailable: %s", exc)

    def reply(self, user_text: str) -> str:
        if not self.config.enabled:
            return "대화 기능은 아직 꺼져 있어."

        if self.mock or self._client is None:
            return f"방금 '{user_text}'라고 말한 것 같아. 지금은 API 연결 없이 대화 구조만 테스트 중이야."

        if self._provider == "gemini":
            return self._reply_gemini(user_text)

        return self._reply_openai(user_text)

    def _reply_gemini(self, user_text: str) -> str:
        types = self._genai_types
        if types is None:
            return "지금은 Gemini 연결 준비가 덜 된 것 같아."

        transcript = []
        for message in self._history:
            role = "사용자" if message["role"] == "user" else "모비"
            transcript.append(f"{role}: {message['content']}")
        transcript.append(f"사용자: {user_text}")
        transcript.append("모비:")

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents="\n".join(transcript),
                config=types.GenerateContentConfig(
                    system_instruction=self._system_prompt,
                    max_output_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                    thinking_config=types.ThinkingConfig(thinking_budget=self.config.thinking_budget),
                ),
            )
            answer = (response.text or "").strip() or "음, 지금은 뭐라고 답해야 할지 잘 모르겠어."
            self._remember(user_text, answer)
            return answer
        except Exception as exc:
            self.logger.warning("Gemini request failed: %s", exc)
            return "지금은 Gemini 서버에 연결이 잘 안 되는 것 같아."

    def _reply_openai(self, user_text: str) -> str:
        messages = [{"role": "system", "content": self._system_prompt}]
        messages.extend(self._history)
        messages.append({"role": "user", "content": user_text})

        try:
            response = self._client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            )
            answer = response.choices[0].message.content or ""
            answer = answer.strip() or "음, 지금은 뭐라고 답해야 할지 잘 모르겠어."
            self._remember(user_text, answer)
            return answer
        except Exception as exc:
            self.logger.warning("LLM request failed: %s", exc)
            return "지금은 대화 서버에 연결이 잘 안 되는 것 같아."

    def synthesize_speech(self, text: str, output_path: str | Path) -> Path | None:
        if not self.config.enabled or self.mock:
            self.logger.warning("TTS skipped because LLM is disabled or mock mode is active")
            return None
        if self._provider != "gemini" or self._client is None or self._genai_types is None:
            self.logger.warning("Gemini TTS is unavailable")
            return None

        types = self._genai_types
        output = Path(output_path)
        try:
            response = self._client.models.generate_content(
                model=self._tts_model,
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=self._tts_voice,
                            )
                        )
                    ),
                ),
            )
            audio = response.candidates[0].content.parts[0].inline_data.data
            output.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(output), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(24000)
                wav_file.writeframes(audio)
            return output
        except Exception as exc:
            self.logger.warning("Gemini TTS request failed: %s", exc)
            return None

    def _remember(self, user_text: str, answer: str) -> None:
        self._history.append({"role": "user", "content": user_text})
        self._history.append({"role": "assistant", "content": answer})
        max_messages = self.config.max_history_turns * 2
        if len(self._history) > max_messages:
            self._history = self._history[-max_messages:]

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def tts_model_name(self) -> str:
        return self._tts_model

    @property
    def tts_voice_name(self) -> str:
        return self._tts_voice
