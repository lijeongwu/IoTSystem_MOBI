from __future__ import annotations

import math
import time
from dataclasses import dataclass

import pygame

from .config import DisplayConfig


@dataclass
class FaceState:
    mood: str = "idle"
    looking_x: float = 0.0
    face_seen: bool = False
    message: str = ""


class FaceUI:
    def __init__(self, config: DisplayConfig):
        self.config = config
        self._started_at = time.monotonic()
        self._state = FaceState()
        self._closed = False

        pygame.init()
        flags = pygame.FULLSCREEN if config.fullscreen else 0
        self.screen = pygame.display.set_mode((config.width, config.height), flags)
        pygame.display.set_caption("MOBI")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 26)

    @property
    def closed(self) -> bool:
        return self._closed

    def set_state(self, state: FaceState) -> None:
        self._state = state

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

    def _draw(self) -> None:
        state = self._state
        t = time.monotonic() - self._started_at

        bg = {
            "idle": (18, 21, 25),
            "happy": (17, 35, 29),
            "dizzy": (34, 25, 42),
            "listen": (22, 30, 42),
            "speak": (36, 28, 18),
            "sleep": (14, 16, 20),
        }.get(state.mood, (18, 21, 25))

        self.screen.fill(bg)

        cx = self.config.width // 2
        cy = self.config.height // 2 - 20
        eye_gap = 185
        eye_y = cy - 25
        pupil_offset = int(max(-1.0, min(1.0, state.looking_x)) * 22)

        if state.mood == "sleep":
            self._draw_sleep_eye(cx - eye_gap // 2, eye_y)
            self._draw_sleep_eye(cx + eye_gap // 2, eye_y)
        elif state.mood == "dizzy":
            self._draw_spiral_eye(cx - eye_gap // 2, eye_y, t)
            self._draw_spiral_eye(cx + eye_gap // 2, eye_y, t + 0.6)
        else:
            self._draw_eye(cx - eye_gap // 2, eye_y, pupil_offset, state.mood, t)
            self._draw_eye(cx + eye_gap // 2, eye_y, pupil_offset, state.mood, t)

        self._draw_mouth(cx, cy + 140, state.mood, t)
        self._draw_status(state)

    def _draw_eye(self, x: int, y: int, pupil_offset: int, mood: str, t: float) -> None:
        blink = (int(t * 1.4) % 7) == 0 and (t % 1.0) < 0.08
        eye_w = 118
        eye_h = 78 if not blink else 12
        rect = pygame.Rect(0, 0, eye_w, eye_h)
        rect.center = (x, y)

        color = (235, 246, 255)
        if mood == "happy":
            color = (239, 255, 230)
        elif mood == "listen":
            color = (226, 241, 255)
        elif mood == "speak":
            color = (255, 239, 215)

        pygame.draw.ellipse(self.screen, color, rect)

        if not blink:
            iris = pygame.Rect(0, 0, 46, 58)
            iris.center = (x + pupil_offset, y + 3)
            pygame.draw.ellipse(self.screen, (80, 156, 130), iris)

            highlight = pygame.Rect(0, 0, 12, 16)
            highlight.center = (x + pupil_offset - 9, y - 15)
            pygame.draw.ellipse(self.screen, (210, 255, 236), highlight)

            slit = pygame.Rect(0, 0, 9, 55)
            slit.center = (x + pupil_offset, y + 3)
            pygame.draw.ellipse(self.screen, (12, 16, 18), slit)

    def _draw_sleep_eye(self, x: int, y: int) -> None:
        pygame.draw.arc(self.screen, (210, 225, 235), (x - 62, y - 24, 124, 64), 0.15, math.pi - 0.15, 8)

    def _draw_spiral_eye(self, x: int, y: int, t: float) -> None:
        points = []
        for i in range(95):
            r = 2 + i * 0.55
            a = i * 0.33 + t * 5
            points.append((x + math.cos(a) * r, y + math.sin(a) * r))
        if len(points) > 1:
            pygame.draw.lines(self.screen, (245, 232, 255), False, points, 5)

    def _draw_mouth(self, x: int, y: int, mood: str, t: float) -> None:
        if mood == "happy":
            pygame.draw.arc(self.screen, (245, 255, 245), (x - 72, y - 46, 144, 82), 0.1, math.pi - 0.1, 7)
        elif mood == "dizzy":
            pygame.draw.line(self.screen, (245, 232, 255), (x - 42, y), (x + 42, y), 6)
        elif mood == "speak":
            h = 24 + int((math.sin(t * 16) + 1) * 15)
            pygame.draw.ellipse(self.screen, (255, 235, 205), (x - 42, y - h // 2, 84, h))
        elif mood == "listen":
            pygame.draw.circle(self.screen, (226, 241, 255), (x, y), 18, 5)
        else:
            pygame.draw.line(self.screen, (225, 235, 242), (x - 46, y), (x + 46, y), 6)

    def _draw_status(self, state: FaceState) -> None:
        if not state.message:
            return
        text = self.font.render(state.message, True, (180, 190, 200))
        rect = text.get_rect(center=(self.config.width // 2, self.config.height - 38))
        self.screen.blit(text, rect)
