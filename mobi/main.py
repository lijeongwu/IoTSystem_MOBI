from __future__ import annotations

import argparse
import logging

import pygame

from mobi.camera.camera_face_tracker import CameraFaceTracker, FaceTrackResult
from mobi.config import BehaviorConfig, CameraConfig, DisplayConfig, MpuConfig, RobotConfig
from mobi.core.behavior_manager import BehaviorManager
from mobi.display.expressions import Expression
from mobi.display.mobi_face import MobiFace
from mobi.sensors.mpu6050_reader import MPU6050Reader


class MobiApp:
    def __init__(self, config: RobotConfig):
        self.logger = logging.getLogger("mobi")
        self.config = config
        self.face = MobiFace(config.display)
        self.camera = CameraFaceTracker(config.camera, mock=config.mock)
        self.mpu = MPU6050Reader(config.mpu, mock=config.mock)
        self.behavior = BehaviorManager(config.behavior)
        self._manual_gaze_mode = False

    def run(self) -> None:
        try:
            while not self.face.closed:
                events = self.face.tick()
                self._handle_keys(events)

                face_result = self.camera.read()
                shake = self.mpu.shake_detected()
                expression, gaze_x, gaze_y = self.behavior.update(face_result, shake)

                self.face.set_expression(expression)
                self.face.set_gaze(gaze_x, gaze_y)
                self._dispatch_expression_triggers(expression, face_result)
        finally:
            self.close()

    def close(self) -> None:
        self.camera.close()
        self.face.close()

    def _handle_keys(self, events: list[pygame.event.Event]) -> None:
        for event in events:
            if event.type != pygame.KEYDOWN:
                continue

            key_map = {
                pygame.K_1: Expression.IDLE,
                pygame.K_2: Expression.LOOK,
                pygame.K_3: Expression.HAPPY,
                pygame.K_4: Expression.LISTENING,
                pygame.K_5: Expression.THINKING,
                pygame.K_6: Expression.SPEAKING,
                pygame.K_7: Expression.DIZZY,
                pygame.K_8: Expression.SURPRISED,
                pygame.K_9: Expression.SLEEPY,
                pygame.K_0: Expression.ERROR,
            }
            if event.key in key_map:
                self._manual_gaze_mode = event.key == pygame.K_2
                expression = key_map[event.key]
                if expression == Expression.DIZZY:
                    self.behavior.trigger(Expression.DIZZY, self.config.behavior.dizzy_duration_s)
                elif expression == Expression.HAPPY:
                    self.behavior.trigger_happy()
                elif expression == Expression.SURPRISED:
                    self.behavior.trigger_surprised()
                else:
                    self.behavior.set_expression(expression)
                continue

            if event.key == pygame.K_SPACE:
                if self.behavior.expression == Expression.SPEAKING:
                    self.behavior.stop_speaking()
                else:
                    self.behavior.start_speaking()
                continue

            if event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
                self._manual_gaze_mode = True
                gx = self.behavior.gaze_x
                gy = self.behavior.gaze_y
                if event.key == pygame.K_LEFT:
                    gx -= 0.15
                elif event.key == pygame.K_RIGHT:
                    gx += 0.15
                elif event.key == pygame.K_UP:
                    gy -= 0.15
                elif event.key == pygame.K_DOWN:
                    gy += 0.15
                self.behavior.set_expression(Expression.LOOK)
                self.behavior.set_gaze(gx, gy)

    def _dispatch_expression_triggers(self, expression: Expression, face_result: FaceTrackResult) -> None:
        if expression == Expression.LOOK and face_result.seen:
            self.face.trigger_face_detected(face_result.gaze_x, face_result.gaze_y)
        elif expression == Expression.DIZZY:
            self.face.trigger_shake_dizzy()
        elif expression == Expression.LISTENING:
            self.face.trigger_listening()
        elif expression == Expression.THINKING:
            self.face.trigger_thinking()
        elif expression == Expression.SPEAKING:
            self.face.start_speaking()
        elif expression == Expression.HAPPY:
            self.face.trigger_touch_happy()
        elif expression == Expression.SURPRISED:
            self.face.trigger_surprised()
        elif expression == Expression.ERROR:
            self.face.trigger_error()


def build_config(args: argparse.Namespace) -> RobotConfig:
    return RobotConfig(
        mock=args.mock,
        display=DisplayConfig(fullscreen=args.fullscreen),
        camera=CameraConfig(
            width=args.camera_width,
            height=args.camera_height,
            detect_every_n_frames=args.detect_every,
            min_detection_confidence=args.min_face_confidence,
        ),
        mpu=MpuConfig(shake_threshold_g=args.shake_threshold),
        behavior=BehaviorConfig(sleepy_after_s=args.sleepy_after),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run MOBI PiCamera2 + MediaPipe face display.")
    parser.add_argument("--mock", action="store_true", help="Run without camera and MPU6050 hardware.")
    parser.add_argument("--fullscreen", action="store_true", help="Run pygame display fullscreen.")
    parser.add_argument("--camera-width", type=int, default=640)
    parser.add_argument("--camera-height", type=int, default=360)
    parser.add_argument("--detect-every", type=int, default=2)
    parser.add_argument("--min-face-confidence", type=float, default=0.55)
    parser.add_argument("--shake-threshold", type=float, default=1.65)
    parser.add_argument("--sleepy-after", type=float, default=20.0)
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    app = MobiApp(build_config(args))
    app.run()
