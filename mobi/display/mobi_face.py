from __future__ import annotations

import math
import time

import pygame

from mobi.config import DisplayConfig
from mobi.display.effects import blink_amount, breathing_offset, clamp, dizzy_jitter, shimmer
from mobi.display.expressions import Expression, normalize_expression


class MobiFace:
    def __init__(self, config: DisplayConfig):
        self.config = config
        self.expression = Expression.IDLE
        self.gaze_x = 0.0
        self.gaze_y = 0.0
        self._closed = False
        self._started_at = time.monotonic()
        self._speaking = False
        self._dizzy_until = 0.0

        pygame.init()
        flags = pygame.FULLSCREEN if config.fullscreen else 0
        self.screen = pygame.display.set_mode((config.width, config.height), flags)
        pygame.display.set_caption("MOBI")
        self.clock = pygame.time.Clock()

    @property
    def closed(self) -> bool:
        return self._closed

    def tick(self) -> list[pygame.event.Event]:
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                self._closed = True
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q):
                self._closed = True

        self._draw()
        pygame.display.flip()
        self.clock.tick(self.config.fps)
        return events

    def close(self) -> None:
        pygame.quit()

    def set_expression(self, expression: str) -> None:
        self.expression = normalize_expression(expression)
        self._speaking = self.expression == Expression.SPEAKING

    def set_gaze(self, x: float, y: float) -> None:
        self.gaze_x = clamp(x, -1.0, 1.0)
        self.gaze_y = clamp(y, -1.0, 1.0)

    def trigger_face_detected(self, gaze_x: float, gaze_y: float) -> None:
        self.set_expression(Expression.LOOK)
        self.set_gaze(gaze_x, gaze_y)

    def trigger_face_lost(self) -> None:
        self.set_gaze(0.0, 0.0)
        self.set_expression(Expression.IDLE)

    def trigger_shake_dizzy(self) -> None:
        self._dizzy_until = time.monotonic() + 2.0
        self.set_expression(Expression.DIZZY)

    def trigger_listening(self) -> None:
        self.set_expression(Expression.LISTENING)

    def trigger_thinking(self) -> None:
        self.set_expression(Expression.THINKING)

    def start_speaking(self) -> None:
        self._speaking = True
        self.set_expression(Expression.SPEAKING)

    def stop_speaking(self) -> None:
        self._speaking = False
        self.set_expression(Expression.IDLE)

    def trigger_touch_happy(self) -> None:
        self.set_expression(Expression.HAPPY)

    def trigger_surprised(self) -> None:
        self.set_expression(Expression.SURPRISED)

    def trigger_error(self) -> None:
        self.set_expression(Expression.ERROR)

    def trigger_highfive(self) -> None:
        pass

    def trigger_gun_hit(self) -> None:
        pass

    def _draw(self) -> None:
        t = time.monotonic() - self._started_at
        expression = self.expression
        if expression == Expression.DIZZY and time.monotonic() > self._dizzy_until:
            expression = Expression.IDLE
            self.expression = expression

        bg = self._background_color(expression, t)
        self.screen.fill(bg)

        cx = self.config.width // 2
        cy = self.config.height // 2 - 12
        if expression == Expression.DIZZY:
            jx, jy = dizzy_jitter(t)
            cx += int(jx)
            cy += int(jy)
        else:
            cy += int(breathing_offset(t, amplitude=6.0))

        eye_gap = 178
        eye_y = cy - 36
        left_x = cx - eye_gap // 2
        right_x = cx + eye_gap // 2

        if expression == Expression.SLEEPY:
            self._draw_sleepy_eye(left_x, eye_y, t)
            self._draw_sleepy_eye(right_x, eye_y, t + 0.4)
        elif expression == Expression.DIZZY:
            self._draw_spiral_eye(left_x, eye_y, t)
            self._draw_spiral_eye(right_x, eye_y, t + 0.7)
        else:
            self._draw_eye(left_x, eye_y, expression, t)
            self._draw_eye(right_x, eye_y, expression, t + 0.12)

        self._draw_mouth(cx, cy + 130, expression, t)

    def _background_color(self, expression: Expression, t: float) -> tuple[int, int, int]:
        pulse = int(shimmer(t) * 8)
        colors = {
            Expression.IDLE: (14 + pulse, 18 + pulse, 24 + pulse),
            Expression.LOOK: (15, 23 + pulse, 29 + pulse),
            Expression.LISTENING: (14, 22 + pulse, 36 + pulse),
            Expression.THINKING: (23 + pulse, 19, 34 + pulse),
            Expression.SPEAKING: (34 + pulse, 24 + pulse, 15),
            Expression.DIZZY: (34 + pulse, 20, 42 + pulse),
            Expression.HAPPY: (13, 34 + pulse, 25),
            Expression.SURPRISED: (32 + pulse, 26 + pulse, 16),
            Expression.SLEEPY: (10, 12, 18 + pulse),
            Expression.ERROR: (42 + pulse, 12, 18),
        }
        return colors.get(expression, colors[Expression.IDLE])

    def _draw_eye(self, x: int, y: int, expression: Expression, t: float) -> None:
        blink = blink_amount(t)
        base_h = 78
        if expression == Expression.HAPPY:
            base_h = 62
        if expression == Expression.SURPRISED:
            base_h = 102
        if expression == Expression.LISTENING:
            base_h = 84

        eye_h = max(10, int(base_h * (1.0 - blink * 0.86)))
        eye_w = 124 if expression != Expression.SURPRISED else 138
        rect = pygame.Rect(0, 0, eye_w, eye_h)
        rect.center = (x, y)

        white = {
            Expression.HAPPY: (238, 255, 232),
            Expression.LISTENING: (226, 242, 255),
            Expression.THINKING: (242, 232, 255),
            Expression.SPEAKING: (255, 238, 218),
            Expression.SURPRISED: (255, 250, 228),
            Expression.ERROR: (255, 215, 220),
        }.get(expression, (236, 247, 255))

        pygame.draw.ellipse(self.screen, white, rect)

        if eye_h <= 14:
            return

        gaze_scale_x = 24 if expression != Expression.LISTENING else 12
        gaze_scale_y = 13
        px = x + int(self.gaze_x * gaze_scale_x)
        py = y + int(self.gaze_y * gaze_scale_y)

        iris = pygame.Rect(0, 0, 48, 58)
        iris.center = (px, py)
        pygame.draw.ellipse(self.screen, (68, 156, 132), iris)

        slit_h = 56 if expression != Expression.SURPRISED else 66
        slit_w = 9 if expression != Expression.SURPRISED else 12
        slit = pygame.Rect(0, 0, slit_w, slit_h)
        slit.center = (px, py)
        pygame.draw.ellipse(self.screen, (10, 14, 16), slit)

        shine = pygame.Rect(0, 0, 12, 16)
        shine.center = (px - 10, py - 16)
        pygame.draw.ellipse(self.screen, (206, 255, 236), shine)

    def _draw_sleepy_eye(self, x: int, y: int, t: float) -> None:
        lift = int(math.sin(t * 1.5) * 4)
        pygame.draw.arc(self.screen, (205, 222, 232), (x - 60, y - 18 + lift, 120, 62), 0.12, math.pi - 0.12, 8)

    def _draw_spiral_eye(self, x: int, y: int, t: float) -> None:
        points = []
        for i in range(90):
            r = 2 + i * 0.58
            a = i * 0.34 + t * 5.5
            points.append((x + math.cos(a) * r, y + math.sin(a) * r))
        pygame.draw.lines(self.screen, (245, 232, 255), False, points, 5)

    def _draw_mouth(self, x: int, y: int, expression: Expression, t: float) -> None:
        color = (226, 236, 242)
        if expression == Expression.HAPPY:
            pygame.draw.arc(self.screen, (235, 255, 235), (x - 76, y - 42, 152, 90), 0.12, math.pi - 0.12, 7)
        elif expression == Expression.SURPRISED:
            pygame.draw.ellipse(self.screen, (255, 232, 204), (x - 28, y - 30, 56, 60), 6)
        elif expression == Expression.SPEAKING:
            h = 22 + int((math.sin(t * 17.0) + 1) * 18)
            pygame.draw.ellipse(self.screen, (255, 232, 204), (x - 46, y - h // 2, 92, h))
        elif expression == Expression.LISTENING:
            pygame.draw.circle(self.screen, (226, 242, 255), (x, y), 18, 5)
        elif expression == Expression.THINKING:
            pygame.draw.arc(self.screen, (232, 224, 255), (x - 54, y - 10, 108, 44), math.pi + 0.1, math.tau - 0.1, 6)
        elif expression == Expression.ERROR:
            pygame.draw.line(self.screen, (255, 210, 215), (x - 44, y - 15), (x + 44, y + 15), 6)
            pygame.draw.line(self.screen, (255, 210, 215), (x - 44, y + 15), (x + 44, y - 15), 6)
        else:
            pygame.draw.line(self.screen, color, (x - 48, y), (x + 48, y), 6)
