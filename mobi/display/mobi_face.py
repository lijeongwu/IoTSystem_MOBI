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
        self._overlay_text: str | None = None

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

    def set_overlay(self, text: str | None) -> None:
        self._overlay_text = text

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

    def trigger_gun_hit(self) -> None:
        self.set_expression(Expression.DEAD)

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

        eye_gap = min(310, int(self.config.width * 0.39))
        eye_y = cy - 46
        left_x = cx - eye_gap // 2
        right_x = cx + eye_gap // 2

        if expression == Expression.SLEEPY:
            self._draw_sleepy_eye(left_x, eye_y, t)
            self._draw_sleepy_eye(right_x, eye_y, t + 0.4)
        elif expression == Expression.DEAD:
            self._draw_dead_eye(left_x, eye_y)
            self._draw_dead_eye(right_x, eye_y)
        elif expression == Expression.DIZZY:
            self._draw_spiral_eye(left_x, eye_y, t)
            self._draw_spiral_eye(right_x, eye_y, t + 0.7)
        else:
            self._draw_eye(left_x, eye_y, expression, t)
            self._draw_eye(right_x, eye_y, expression, t + 0.12)

        if expression in (Expression.HAPPY, Expression.HAPPY_PET, Expression.HAPPY_BLISS):
            self._draw_happy_cheeks(cx, cy, t)

        self._draw_mouth(cx, cy + 108, expression, t)
        if self._overlay_text:
            self._draw_overlay(self._overlay_text)

    def _background_color(self, expression: Expression, t: float) -> tuple[int, int, int]:
        pulse = int(shimmer(t) * 3)
        return (248 + pulse, 244 + pulse, 232 + pulse)

    def _draw_eye(self, x: int, y: int, expression: Expression, t: float) -> None:
        blink = blink_amount(t)
        base_h = 112
        if expression in (Expression.HAPPY, Expression.HAPPY_PET, Expression.HAPPY_BLISS):
            base_h = 106
        if expression == Expression.SURPRISED:
            base_h = 124
        if expression in (Expression.ANNOYED, Expression.HURT):
            base_h = 82
        if expression == Expression.LISTENING:
            base_h = 116

        eye_h = max(int(base_h * 0.74), int(base_h * (1.0 - blink * 0.36)))
        eye_w = 76 if expression != Expression.SURPRISED else 86
        socket = pygame.Rect(0, 0, eye_w + 24, eye_h + 18)
        socket.center = (x, y)
        lens = pygame.Rect(0, 0, eye_w, eye_h)
        lens.center = (x, y)

        pygame.draw.ellipse(self.screen, (214, 210, 202), socket)
        pygame.draw.ellipse(self.screen, (116, 112, 108), socket, 4)
        pygame.draw.ellipse(self.screen, (18, 27, 32), lens)

        if eye_h <= 14:
            return

        gaze_scale_x = 8 if expression != Expression.LISTENING else 4
        gaze_scale_y = 8
        px = x + int(self.gaze_x * gaze_scale_x)
        py = y + int(self.gaze_y * gaze_scale_y)
        if expression == Expression.ANNOYED:
            px += 4 if x < self.config.width // 2 else -4
        elif expression == Expression.HURT:
            py += 5

        glow = pygame.Rect(0, 0, int(eye_w * 0.72), int(eye_h * 0.86))
        glow.center = (px + 4, py + 12)
        pygame.draw.ellipse(self.screen, (26, 132, 156), glow)

        iris = pygame.Rect(0, 0, int(eye_w * 0.54), int(eye_h * 0.82))
        iris.center = (px, py + 4)
        pygame.draw.ellipse(self.screen, (38, 162, 186), iris)

        pupil = pygame.Rect(0, 0, int(eye_w * 0.42), int(eye_h * 0.78))
        pupil.center = (px - 4, py - 2)
        pygame.draw.ellipse(self.screen, (8, 15, 18), pupil)

        rim = pygame.Rect(0, 0, int(eye_w * 0.72), int(eye_h * 0.96))
        rim.center = lens.center
        pygame.draw.ellipse(self.screen, (72, 78, 82), rim, 3)

        shine = pygame.Rect(0, 0, int(eye_w * 0.20), int(eye_h * 0.18))
        shine.center = (px - int(eye_w * 0.18), py - int(eye_h * 0.32))
        pygame.draw.ellipse(self.screen, (246, 250, 248), shine)
        small_shine = pygame.Rect(0, 0, int(eye_w * 0.09), int(eye_h * 0.10))
        small_shine.center = (px + int(eye_w * 0.16), py - int(eye_h * 0.10))
        pygame.draw.ellipse(self.screen, (210, 235, 232), small_shine)

    def _draw_sleepy_eye(self, x: int, y: int, t: float) -> None:
        lift = int(math.sin(t * 1.5) * 4)
        pygame.draw.arc(self.screen, (94, 70, 52), (x - 106, y - 38 + lift, 212, 104), 0.12, math.pi - 0.12, 10)

    def _draw_spiral_eye(self, x: int, y: int, t: float) -> None:
        socket = pygame.Rect(0, 0, 104, 130)
        socket.center = (x, y)
        lens = pygame.Rect(0, 0, 78, 110)
        lens.center = (x, y)
        pygame.draw.ellipse(self.screen, (214, 210, 202), socket)
        pygame.draw.ellipse(self.screen, (116, 112, 108), socket, 4)
        pygame.draw.ellipse(self.screen, (248, 244, 232), lens)

        points = []
        for i in range(118):
            r = 3 + i * 0.43
            a = i * 0.38 + t * 5.5
            points.append((x + math.cos(a) * r, y + math.sin(a) * r))
        pygame.draw.lines(self.screen, (24, 22, 20), False, points, 7)

    def _draw_happy_cheeks(self, x: int, y: int, t: float) -> None:
        pulse = 0.92 + shimmer(t * 1.4) * 0.10
        cheek_y = y + 46
        cheek_dx = min(190, int(self.config.width * 0.23))
        radius = int(76 * pulse)
        for cheek_x in (x - cheek_dx, x + cheek_dx):
            surface_size = radius * 2 + 10
            surface = pygame.Surface((surface_size, surface_size), pygame.SRCALPHA)
            center = surface_size // 2
            for step in range(10, 0, -1):
                r = int(radius * step / 10)
                alpha = int(10 + (10 - step) * 8)
                pygame.draw.circle(surface, (246, 118, 134, alpha), (center, center), r)
            pygame.draw.circle(surface, (255, 168, 178, 82), (center - radius // 5, center - radius // 8), radius // 3)
            self.screen.blit(surface, (cheek_x - center, cheek_y - center))

    def _draw_dead_eye(self, x: int, y: int) -> None:
        size = 86
        color = (64, 52, 42)
        pygame.draw.line(self.screen, color, (x - size // 2, y - size // 2), (x + size // 2, y + size // 2), 12)
        pygame.draw.line(self.screen, color, (x - size // 2, y + size // 2), (x + size // 2, y - size // 2), 12)

    def _draw_mouth(self, x: int, y: int, expression: Expression, t: float) -> None:
        color = (94, 70, 52)
        if expression in (Expression.HAPPY, Expression.HAPPY_PET):
            pygame.draw.arc(self.screen, (104, 76, 54), (x - 76, y - 70, 152, 96), math.pi + 0.12, math.tau - 0.12, 7)
        elif expression == Expression.HAPPY_BLISS:
            pygame.draw.arc(self.screen, (104, 76, 54), (x - 84, y - 76, 168, 104), math.pi + 0.08, math.tau - 0.08, 8)
            pygame.draw.circle(self.screen, (196, 118, 104), (x - 116, y - 58), 8)
            pygame.draw.circle(self.screen, (196, 118, 104), (x + 116, y - 58), 8)
        elif expression == Expression.SURPRISED:
            pygame.draw.ellipse(self.screen, (104, 76, 54), (x - 28, y - 30, 56, 60), 6)
        elif expression == Expression.SAD:
            pygame.draw.arc(self.screen, (104, 76, 54), (x - 62, y - 4, 124, 54), 0.16, math.pi - 0.16, 7)
        elif expression == Expression.DEAD:
            pygame.draw.line(self.screen, (64, 52, 42), (x - 50, y + 4), (x + 50, y + 4), 8)
        elif expression == Expression.DIZZY:
            points = []
            for i in range(13):
                px = x - 54 + i * 9
                py = y + int(math.sin(t * 8.0 + i * 0.85) * 7)
                points.append((px, py))
            pygame.draw.lines(self.screen, (24, 22, 20), False, points, 7)
        elif expression == Expression.ANNOYED:
            pygame.draw.arc(self.screen, (132, 74, 62), (x - 58, y - 2, 116, 50), math.pi + 0.1, math.tau - 0.1, 6)
        elif expression == Expression.HURT:
            pygame.draw.line(self.screen, (132, 74, 82), (x - 44, y + 10), (x + 44, y - 6), 6)
        elif expression == Expression.SPEAKING:
            h = 22 + int((math.sin(t * 17.0) + 1) * 18)
            pygame.draw.ellipse(self.screen, (104, 76, 54), (x - 46, y - h // 2, 92, h))
        elif expression == Expression.LISTENING:
            pygame.draw.circle(self.screen, (104, 76, 54), (x, y), 18, 5)
        elif expression == Expression.THINKING:
            pygame.draw.arc(self.screen, (104, 76, 54), (x - 54, y - 10, 108, 44), math.pi + 0.1, math.tau - 0.1, 6)
        elif expression == Expression.ERROR:
            pygame.draw.line(self.screen, (132, 74, 82), (x - 44, y - 15), (x + 44, y + 15), 6)
            pygame.draw.line(self.screen, (132, 74, 82), (x - 44, y + 15), (x + 44, y - 15), 6)
        else:
            pygame.draw.line(self.screen, color, (x - 48, y), (x + 48, y), 6)

    def _draw_overlay(self, text: str) -> None:
        size = 92 if text in ("3", "2", "1") else 34
        font = pygame.font.SysFont("arial", size, bold=True)
        surface = font.render(text, True, (64, 52, 42))
        rect = surface.get_rect(center=(self.config.width // 2, 54 if size < 80 else self.config.height // 2))
        self.screen.blit(surface, rect)
