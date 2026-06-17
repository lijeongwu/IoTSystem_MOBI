from __future__ import annotations

import time

from mobi.camera.camera_face_tracker import FaceTrackResult
from mobi.config import BehaviorConfig
from mobi.display.expressions import Expression, normalize_expression
from mobi.sensors.touch_reader import TouchAction, TouchEvent


class BehaviorManager:
    def __init__(self, config: BehaviorConfig):
        self.config = config
        self.expression = Expression.IDLE
        self.gaze_x = 0.0
        self.gaze_y = 0.0
        self._temporary_until = 0.0
        self._temporary_expression: Expression | None = None
        self._manual_expression: Expression | None = None
        self._last_face_seen_at = time.monotonic()
        self._speaking = False

    def update(self, face: FaceTrackResult, shake: bool) -> tuple[Expression, float, float]:
        now = time.monotonic()
        if shake:
            self.trigger(Expression.DIZZY, self.config.dizzy_duration_s)

        if self._temporary_expression and now < self._temporary_until:
            self.expression = self._temporary_expression
            return self.expression, self.gaze_x, self.gaze_y
        self._temporary_expression = None

        if self._speaking:
            self.expression = Expression.SPEAKING
            return self.expression, self.gaze_x, self.gaze_y

        if self._manual_expression is not None:
            self.expression = self._manual_expression
            return self.expression, self.gaze_x, self.gaze_y

        if face.seen:
            self._last_face_seen_at = now
            self.gaze_x = face.gaze_x
            self.gaze_y = face.gaze_y
            self.expression = Expression.LOOK
        else:
            self.gaze_x = 0.0
            self.gaze_y = 0.0
            self.expression = Expression.IDLE

        return self.expression, self.gaze_x, self.gaze_y

    def set_expression(self, expression: str | Expression) -> None:
        self.expression = normalize_expression(expression)
        self._temporary_expression = None
        self._speaking = self.expression == Expression.SPEAKING
        if self.expression == Expression.IDLE:
            self._manual_expression = None
        elif self.expression != Expression.SPEAKING:
            self._manual_expression = self.expression

    def set_gaze(self, x: float, y: float) -> None:
        self.gaze_x = max(-1.0, min(1.0, x))
        self.gaze_y = max(-1.0, min(1.0, y))

    def reset_idle_timer(self) -> None:
        self._last_face_seen_at = time.monotonic()
        self._temporary_expression = None
        self._manual_expression = None
        self._speaking = False
        self.expression = Expression.IDLE

    def trigger(self, expression: str | Expression, duration_s: float) -> None:
        self._temporary_expression = normalize_expression(expression)
        self._temporary_until = time.monotonic() + duration_s
        self.expression = self._temporary_expression
        self._manual_expression = None

    def trigger_happy(self) -> None:
        self.trigger(Expression.HAPPY, self.config.happy_duration_s)

    def trigger_surprised(self) -> None:
        self.trigger(Expression.SURPRISED, self.config.surprised_duration_s)

    def trigger_touch(self, event: TouchEvent, happy_duration_s: float, angry_duration_s: float) -> None:
        expression_by_action = {
            TouchAction.HEAD: Expression.HAPPY,
            TouchAction.BACK: Expression.HAPPY,
            TouchAction.LEFT_EAR: Expression.ANNOYED,
            TouchAction.RIGHT_EAR: Expression.ANNOYED,
        }
        expression = expression_by_action[event.action]
        duration_s = happy_duration_s if event.action in (TouchAction.HEAD, TouchAction.BACK) else angry_duration_s
        self.trigger(expression, duration_s)

    def start_speaking(self) -> None:
        self._speaking = True
        self._manual_expression = None
        self.expression = Expression.SPEAKING

    def stop_speaking(self) -> None:
        self._speaking = False
        self._manual_expression = None
        self.expression = Expression.IDLE
