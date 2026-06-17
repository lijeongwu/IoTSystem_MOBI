from __future__ import annotations

import argparse
import logging
import time

import pygame

from mobi.actuators.tail_servo import TailServo
from mobi.audio_live import GeminiLiveController, LiveEventType
from mobi.camera.camera_face_tracker import CameraFaceTracker, FaceTrackResult, HandGesture
from mobi.config import BehaviorConfig, CameraConfig, DisplayConfig, LiveConversationConfig, MpuConfig, RobotConfig, TailConfig, TouchConfig
from mobi.core.behavior_manager import BehaviorManager
from mobi.core.rps_game import RpsGame
from mobi.display.expressions import Expression
from mobi.display.mobi_face import MobiFace
from mobi.sensors.mpu6050_reader import MPU6050Reader
from mobi.sensors.touch_reader import TTP224TouchReader, TouchAction


class MobiApp:
    def __init__(self, config: RobotConfig):
        self.logger = logging.getLogger("mobi")
        self.config = config
        self.face = MobiFace(config.display)
        self.camera = CameraFaceTracker(config.camera, mock=config.mock)
        self.mpu = MPU6050Reader(config.mpu, mock=config.mock)
        self.touch = TTP224TouchReader(config.touch, mock=config.mock)
        self.tail = TailServo(config.tail, mock=config.mock)
        self.behavior = BehaviorManager(config.behavior)
        self.rps = RpsGame()
        self.live = GeminiLiveController(config.live, mock=config.mock)
        self._sleeping = True
        self._wake_touch_started_at: float | None = None
        self._palm_seen_at: list[float] = []
        self._wake_block_until = 0.0
        self._space_handled_at = 0.0
        self._gun_aim_until = 0.0
        self._gun_hit_until = 0.0
        self._manual_gaze_mode = False
        self.face.set_expression(Expression.SLEEPY)
        self.behavior.set_expression(Expression.SLEEPY)

    def run(self) -> None:
        try:
            while not self.face.closed:
                events = self.face.tick()
                self._handle_keys(events)

                face_result = self.camera.read()
                shake = self.mpu.shake_detected()
                hand_gesture = self.camera.hand_gesture()
                now = time.monotonic()
                self._handle_live_events(now)

                if self._sleeping:
                    self.tail.center()
                    if self._wake_requested(hand_gesture, now):
                        self._wake_up(face_result)
                    else:
                        self.face.set_overlay(None)
                        self.face.set_expression(Expression.SLEEPY)
                        self.face.set_gaze(0.0, 0.0)
                        continue

                if self.live.running and (self.live.speaking or self.live.mic_muted or self.rps.active or now < self._gun_hit_until):
                    self.live.mark_activity(now)

                if self.live.running and now - self.live.last_activity_at >= self.config.live.sleep_after_s:
                    self.logger.info("Live conversation idle for %.1fs; sleeping", self.config.live.sleep_after_s)
                    self._go_to_sleep()
                    continue

                if not self.rps.active and hand_gesture == HandGesture.GUN:
                    self._gun_aim_until = now + 3.0
                    self.behavior.trigger(Expression.DIZZY, 0.35)

                if self.rps.active and hand_gesture == HandGesture.GUN:
                    hand_gesture = HandGesture.SCISSORS

                if now < self._gun_hit_until:
                    self.face.set_overlay(None)
                    self.live.mute_mic(True)
                    expression = Expression.DEAD
                    gaze_x = self.behavior.gaze_x
                    gaze_y = self.behavior.gaze_y
                else:
                    if not self.rps.active:
                        self.live.mute_mic(False)
                    self.tail.wag(now)
                    touch_event = self.touch.read_event()
                    if touch_event is not None:
                        self.behavior.trigger_touch(
                            touch_event,
                            self.config.touch.happy_duration_s,
                            self.config.touch.angry_duration_s,
                        )
                    was_rps_active = self.rps.active
                    rps_state = self.rps.update(hand_gesture)
                    if rps_state.active:
                        self.live.mute_mic(True)
                        if rps_state.speech_text:
                            self.live.say(rps_state.speech_text)
                        expression = rps_state.expression or Expression.THINKING
                        gaze_x = self.behavior.gaze_x
                        gaze_y = self.behavior.gaze_y
                        self.face.set_overlay(rps_state.overlay_text)
                    else:
                        if was_rps_active:
                            self.live.mute_mic(False)
                        self.face.set_overlay(None)
                        expression, gaze_x, gaze_y = self.behavior.update(face_result, shake)
                        if self.live.speaking:
                            expression = Expression.SPEAKING

                self.face.set_expression(expression)
                self.face.set_gaze(gaze_x, gaze_y)
                self._dispatch_expression_triggers(expression, face_result)
        finally:
            self.close()

    def close(self) -> None:
        self.live.stop()
        self.live.join()
        self.camera.close()
        self.touch.close()
        self.tail.close()
        self.face.close()

    def _handle_keys(self, events: list[pygame.event.Event]) -> None:
        for event in events:
            if event.type != pygame.KEYDOWN:
                continue

            if event.key == pygame.K_SPACE:
                now = time.monotonic()
                if now - self._space_handled_at < 0.6:
                    continue
                self._space_handled_at = now
                if self._sleeping:
                    self._wake_up(self.camera.read())
                else:
                    self._go_to_sleep()
                return

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

    def _wake_requested(self, hand_gesture: HandGesture, now: float) -> bool:
        if now < self._wake_block_until:
            return False

        if hand_gesture == HandGesture.PAPER:
            self._palm_seen_at.append(now)
            self._palm_seen_at = [seen_at for seen_at in self._palm_seen_at if now - seen_at <= 2.5]
            if len(self._palm_seen_at) >= 3:
                self._palm_seen_at.clear()
                self.logger.info("wake requested by palm gesture")
                return True
        elif self._palm_seen_at and now - self._palm_seen_at[-1] > 2.5:
            self._palm_seen_at.clear()

        if self.touch.is_active(TouchAction.BACK):
            if self._wake_touch_started_at is None:
                self._wake_touch_started_at = now
            elif now - self._wake_touch_started_at >= 2.0:
                self._wake_touch_started_at = None
                self.logger.info("wake requested by OUT4 touch hold")
                return True
        else:
            self._wake_touch_started_at = None
        return False

    def _wake_up(self, face_result: FaceTrackResult) -> None:
        if not self._sleeping:
            return
        self.logger.info("MOBI waking up")
        self._sleeping = False
        self._wake_touch_started_at = None
        self._palm_seen_at.clear()
        self.behavior.set_expression(Expression.IDLE)
        self.face.set_expression(Expression.LOOK if face_result.seen else Expression.IDLE)
        self.face.set_gaze(face_result.gaze_x if face_result.seen else 0.0, face_result.gaze_y if face_result.seen else 0.0)
        self.live.start(self.config.live.intro_text)

    def _go_to_sleep(self) -> None:
        if self._sleeping:
            return
        self.logger.info("MOBI going to sleep")
        self._sleeping = True
        self._wake_block_until = time.monotonic() + 1.2
        self.rps = RpsGame()
        self._gun_aim_until = 0.0
        self._gun_hit_until = 0.0
        self.live.stop()
        self.live.join(timeout=1.0)
        self.live.mute_mic(False)
        self.tail.center()
        self.face.set_overlay(None)
        self.behavior.set_expression(Expression.SLEEPY)
        self.face.set_expression(Expression.SLEEPY)
        self.face.set_gaze(0.0, 0.0)

    def _handle_live_events(self, now: float) -> None:
        for event in self.live.drain_events():
            if event.type == LiveEventType.ERROR:
                self.logger.warning("Gemini Live error: %s", event.text)
            elif event.type == LiveEventType.STOPPED:
                self.logger.info("Gemini Live stopped")
            elif event.type == LiveEventType.INPUT_TEXT:
                text = event.text.replace(" ", "")
                self.logger.info("Live input: %s", event.text)
                if "가위바위보" in text and not self.rps.active and not self._sleeping:
                    self.logger.info("starting RPS from voice")
                    self.behavior.stop_speaking()
                    self.live.suppress_output(1.2)
                    self.rps.start()
                    self.live.mute_mic(True)
                if ("빵" in text or "탕" in text) and now <= self._gun_aim_until and not self._sleeping:
                    self.logger.info("bang/tang detected after gun gesture; playing dead")
                    self.live.suppress_output(1.0)
                    self._gun_aim_until = 0.0
                    self._gun_hit_until = now + 2.0
                    self.behavior.trigger(Expression.DEAD, 2.0)
                    self.tail.droop()

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
        elif expression in (Expression.HAPPY_PET, Expression.HAPPY_BLISS, Expression.ANNOYED, Expression.HURT, Expression.SAD):
            self.face.set_expression(expression)
        elif expression == Expression.DEAD:
            self.face.trigger_gun_hit()
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
            min_hand_confidence=args.min_hand_confidence,
            min_hand_area_ratio=args.min_hand_area,
            finger_extension_ratio=args.finger_extension,
        ),
        mpu=MpuConfig(shake_threshold_g=args.shake_threshold),
        touch=TouchConfig(
            head_pin=args.touch_head,
            back_pin=args.touch_back,
            left_ear_pin=args.touch_left_ear,
            right_ear_pin=args.touch_right_ear,
        ),
        tail=TailConfig(
            pin=args.tail_pin,
            center_angle=args.tail_center,
            wag_amplitude=args.tail_wag_amplitude,
            wag_period_s=args.tail_wag_period,
            dead_angle=args.tail_dead_angle,
        ),
        live=LiveConversationConfig(
            enabled=args.live,
            env_file=args.live_env_file,
            model=args.live_model,
            voice=args.live_voice,
            record_device=args.live_record_device,
            play_target=args.live_play_target,
            sleep_after_s=args.live_sleep_after,
            intro_text=args.live_intro,
        ),
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
    parser.add_argument("--min-hand-confidence", type=float, default=0.6)
    parser.add_argument("--min-hand-area", type=float, default=0.04)
    parser.add_argument("--finger-extension", type=float, default=1.2)
    parser.add_argument("--shake-threshold", type=float, default=1.65)
    parser.add_argument("--touch-head", type=int, default=22)
    parser.add_argument("--touch-back", type=int, default=23)
    parser.add_argument("--touch-left-ear", type=int, default=None)
    parser.add_argument("--touch-right-ear", type=int, default=None)
    parser.add_argument("--tail-pin", type=int, default=18)
    parser.add_argument("--tail-center", type=float, default=90.0)
    parser.add_argument("--tail-wag-amplitude", type=float, default=45.0)
    parser.add_argument("--tail-wag-period", type=float, default=0.8)
    parser.add_argument("--tail-dead-angle", type=float, default=30.0)
    parser.add_argument("--sleepy-after", type=float, default=20.0)
    parser.add_argument("--live", action="store_true", help="Enable Gemini Live conversation after wake triggers.")
    parser.add_argument("--live-env-file", default=".env")
    parser.add_argument("--live-model", default="gemini-3.1-flash-live-preview")
    parser.add_argument("--live-voice", default="Puck")
    parser.add_argument("--live-record-device", default="auto")
    parser.add_argument("--live-play-target", default="auto")
    parser.add_argument("--live-sleep-after", type=float, default=10.0)
    parser.add_argument("--live-intro", default="오랜만이야 주인")
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
