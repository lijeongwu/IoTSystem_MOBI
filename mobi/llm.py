from __future__ import annotations

import logging
import os

from .config import LlmConfig


class LlmClient:
    def __init__(self, config: LlmConfig, mock: bool = False):
        self.logger = logging.getLogger("mobi.llm")
        self.config = config
        self.mock = mock
        self._client = None
        self._history: list[dict[str, str]] = []

        if config.enabled and not mock:
            self._setup_openai()

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

        messages = [{"role": "system", "content": self.config.system_prompt}]
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

    def _remember(self, user_text: str, answer: str) -> None:
        self._history.append({"role": "user", "content": user_text})
        self._history.append({"role": "assistant", "content": answer})
        max_messages = self.config.max_history_turns * 2
        if len(self._history) > max_messages:
            self._history = self._history[-max_messages:]
