from __future__ import annotations

import random
import time
from collections import Counter
from dataclasses import dataclass
from enum import Enum

from mobi.camera.camera_face_tracker import HandGesture
from mobi.display.expressions import Expression


class RpsChoice(str, Enum):
    ROCK = "rock"
    PAPER = "paper"
    SCISSORS = "scissors"


@dataclass(frozen=True)
class RpsFrame:
    active: bool
    expression: Expression | None = None
    overlay_text: str | None = None
    speech_text: str | None = None


class RpsGame:
    def __init__(self):
        self._state = "idle"
        self._state_started_at = time.monotonic()
        self._samples: list[HandGesture] = []
        self._mobi_choice: RpsChoice | None = None
        self._result_text = ""
        self._expression: Expression | None = None
        self._last_chant_index = -1

    def update(self, gesture: HandGesture) -> RpsFrame:
        now = time.monotonic()

        if self._state == "idle":
            return RpsFrame(active=False)

        if self._state == "countdown":
            if gesture in (HandGesture.ROCK, HandGesture.PAPER, HandGesture.SCISSORS):
                self._samples.append(gesture)
            elapsed = now - self._state_started_at
            if elapsed >= 3.0:
                self._finish_round(now)
                return self._result_frame()
            chant_index = min(2, int(elapsed))
            speech_text = None
            if chant_index != self._last_chant_index:
                self._last_chant_index = chant_index
                speech_text = ("가위", "바위", "보")[chant_index]
            return RpsFrame(
                active=True,
                expression=Expression.SURPRISED,
                overlay_text=str(max(1, 3 - int(elapsed))),
                speech_text=speech_text,
            )

        if self._state == "result":
            if now - self._state_started_at >= 1.6:
                if self._result_text == "DRAW":
                    self._start_countdown(now)
                    return self.update(gesture)
                self._reset()
                return RpsFrame(active=False)
            return self._result_frame()

        return RpsFrame(active=False)

    def start(self) -> None:
        self._start_countdown(time.monotonic())

    @property
    def active(self) -> bool:
        return self._state != "idle"

    def _start_countdown(self, now: float) -> None:
        self._state = "countdown"
        self._state_started_at = now
        self._samples = []
        self._mobi_choice = None
        self._result_text = ""
        self._expression = Expression.SURPRISED
        self._last_chant_index = -1

    def _finish_round(self, now: float) -> None:
        user_choice = self._stable_user_choice()
        if user_choice is None:
            self._state = "result"
            self._state_started_at = now
            self._mobi_choice = None
            self._result_text = "AGAIN"
            self._expression = Expression.SURPRISED
            return

        self._mobi_choice = random.choice(list(RpsChoice))
        outcome = self._outcome_for_mobi(self._mobi_choice, user_choice)
        self._state = "result"
        self._state_started_at = now

        if outcome == "win":
            self._result_text = "WIN"
            self._expression = Expression.HAPPY
        elif outcome == "lose":
            self._result_text = "LOSE"
            self._expression = Expression.SAD
        else:
            self._result_text = "DRAW"
            self._expression = Expression.SURPRISED

    def _stable_user_choice(self) -> RpsChoice | None:
        valid = [
            gesture
            for gesture in self._samples
            if gesture in (HandGesture.ROCK, HandGesture.PAPER, HandGesture.SCISSORS)
        ]
        if len(valid) < 6:
            return None

        counts = Counter(valid)
        gesture, count = counts.most_common(1)[0]
        if count / len(valid) < 0.65:
            return None

        return {
            HandGesture.ROCK: RpsChoice.ROCK,
            HandGesture.PAPER: RpsChoice.PAPER,
            HandGesture.SCISSORS: RpsChoice.SCISSORS,
        }.get(gesture)

    def _outcome_for_mobi(self, mobi: RpsChoice, user: RpsChoice) -> str:
        if mobi == user:
            return "draw"
        wins = {
            RpsChoice.ROCK: RpsChoice.SCISSORS,
            RpsChoice.PAPER: RpsChoice.ROCK,
            RpsChoice.SCISSORS: RpsChoice.PAPER,
        }
        return "win" if wins[mobi] == user else "lose"

    def _result_frame(self) -> RpsFrame:
        overlay = self._result_text
        if self._mobi_choice is not None:
            overlay = f"{self._label(self._mobi_choice)} {self._result_text}"
        return RpsFrame(
            active=True,
            expression=self._expression,
            overlay_text=overlay,
        )

    def _label(self, choice: RpsChoice) -> str:
        return {
            RpsChoice.ROCK: "ROCK",
            RpsChoice.PAPER: "PAPER",
            RpsChoice.SCISSORS: "SCISSORS",
        }[choice]

    def _reset(self) -> None:
        self._state = "idle"
        self._state_started_at = time.monotonic()
        self._samples = []
        self._mobi_choice = None
        self._result_text = ""
        self._expression = None
        self._last_chant_index = -1
