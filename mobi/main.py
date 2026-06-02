from __future__ import annotations

import argparse
import logging
import time

import pygame

from .audio import AudioIO
from .config import AudioConfig, RobotConfig, VisionConfig
from .face_ui import FaceState, FaceUI
from .imu import ImuSensor
from .motion import HeadServo
from .touch import TouchSensor
from .vision import Vision


def build_config(args: argparse.Namespace) -> RobotConfig:
    return RobotConfig(
        mock=args.mock,
        vision=VisionConfig(
            camera_index=args.camera_index,
            backend=args.vision_backend,
            yolo_model=args.yolo_model,
            yolo_confidence=args.yolo_confidence,
        ),
        audio=AudioConfig(enabled=args.audio),
    )


class MobiApp:
    def __init__(self, config: RobotConfig):
        self.logger = logging.getLogger("mobi")
        self.config = config
        self.ui = FaceUI(config.display)
        self.vision = Vision(config.vision, mock=config.mock)
        self.servo = HeadServo(config.servo, mock=config.mock)
        self.touch = TouchSensor(config.touch, mock=config.mock)
        self.imu = ImuSensor(config.imu, mock=config.mock)
        self.audio = AudioIO(config.audio, mock=config.mock)

        self.mood = "idle"
        self.message = "mock mode" if config.mock else "ready"
        self._mood_until = 0.0
        self._last_face_seen = False
        self._last_tracking_log_at = 0.0

    def run(self) -> None:
        try:
            while not self.ui.closed:
                events = self.ui.tick()
                self._handle_keys(events)
                self._poll_sensors()
                self._update_from_camera()
                self._expire_temporary_mood()
        finally:
            self.close()

    def close(self) -> None:
        self.vision.close()
        self.touch.close()
        self.ui.close()

    def _handle_keys(self, events: list[pygame.event.Event]) -> None:
        for event in events:
            if event.type != pygame.KEYDOWN:
                continue
            if event.key == pygame.K_1:
                self._set_mood("idle", "idle")
            elif event.key == pygame.K_2:
                self._set_mood("happy", "touch")
            elif event.key == pygame.K_3:
                self._set_mood("dizzy", "shake", duration=1.8)
            elif event.key == pygame.K_4:
                self._set_mood("listen", "listening")
            elif event.key == pygame.K_5:
                self._set_mood("speak", "speaking", duration=1.5)
            elif event.key == pygame.K_SPACE:
                self.servo.center()

    def _poll_sensors(self) -> None:
        if self.touch.touched():
            self._set_mood("happy", "touch", duration=1.3)
            self.audio.say("좋아.")

        if self.imu.shaken():
            self._set_mood("dizzy", "shake", duration=1.8)
            self.audio.say("어지러워.")

    def _update_from_camera(self) -> None:
        detection = self.vision.read()
        self.servo.track_face_x(detection.x, detection.frame_width)

        looking_x = 0.0
        if detection.x is not None:
            looking_x = (detection.x - detection.frame_width / 2) / (detection.frame_width / 2)

        if detection.seen and not self._last_face_seen:
            self._set_mood("happy", "face detected", duration=0.9)
            self.logger.info(
                "face detected: x=%s y=%s size=%sx%s",
                detection.x,
                detection.y,
                detection.w,
                detection.h,
            )
        elif not detection.seen and self._last_face_seen:
            self.logger.info("face lost")

        now = time.monotonic()
        if detection.seen and now - self._last_tracking_log_at > 1.0:
            self.logger.info("face tracking: x=%s servo_angle=%.1f", detection.x, self.servo.angle)
            self._last_tracking_log_at = now

        self._last_face_seen = detection.seen

        mood = self.mood
        message = self.message
        if not detection.seen and time.monotonic() > self._mood_until:
            mood = "sleep"
            message = "waiting"

        self.ui.set_state(
            FaceState(
                mood=mood,
                looking_x=looking_x,
                face_seen=detection.seen,
                message=message,
            )
        )

    def _set_mood(self, mood: str, message: str, duration: float = 0.0) -> None:
        self.mood = mood
        self.message = message
        self._mood_until = time.monotonic() + duration if duration else 0.0

    def _expire_temporary_mood(self) -> None:
        if self._mood_until and time.monotonic() > self._mood_until:
            self.mood = "idle"
            self.message = "ready"
            self._mood_until = 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run MOBI tabletop robot MVP.")
    parser.add_argument("--mock", action="store_true", help="Run without real GPIO/I2C/camera hardware.")
    parser.add_argument("--camera-index", type=int, default=0, help="OpenCV camera index.")
    parser.add_argument("--vision-backend", default="haar", choices=("haar", "yolo"), help="Camera detector backend.")
    parser.add_argument("--yolo-model", default="yolov8n.pt", help="YOLO model path or name.")
    parser.add_argument("--yolo-confidence", type=float, default=0.45, help="YOLO confidence threshold.")
    parser.add_argument("--audio", action="store_true", help="Enable pyttsx3 text-to-speech.")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    config = build_config(args)
    app = MobiApp(config)
    app.run()
