from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from enum import Enum

from mobi.config import CameraConfig


@dataclass(frozen=True)
class FaceTrackResult:
    seen: bool
    gaze_x: float = 0.0
    gaze_y: float = 0.0
    confidence: float = 0.0
    frame_width: int = 0
    frame_height: int = 0


class HandGesture(str, Enum):
    UNKNOWN = "unknown"
    ROCK = "rock"
    PAPER = "paper"
    SCISSORS = "scissors"
    GUN = "gun"


class CameraFaceTracker:
    def __init__(self, config: CameraConfig, mock: bool = False):
        self.logger = logging.getLogger("mobi.camera")
        self.config = config
        self.mock = mock
        self._camera = None
        self._face_detector = None
        self._hand_detector = None
        self._frame_count = 0
        self._last_seen_at = 0.0
        self._last_result = FaceTrackResult(False, frame_width=config.width, frame_height=config.height)
        self._last_hand_gesture = HandGesture.UNKNOWN
        self._started_at = time.monotonic()

        if mock:
            self.logger.info("camera tracker running in mock mode")
            return

        self._setup_camera()
        self._setup_mediapipe()

    def _setup_camera(self) -> None:
        try:
            from picamera2 import Picamera2

            camera = Picamera2()
            camera_config = camera.create_preview_configuration(
                main={"format": "RGB888", "size": (self.config.width, self.config.height)}
            )
            camera.configure(camera_config)
            camera.start()
            self._camera = camera
            self.logger.info("Picamera2 started at %sx%s", self.config.width, self.config.height)
        except Exception as exc:
            self.logger.warning("Picamera2 unavailable; camera tracking disabled: %s", exc)
            self._camera = None

    def _setup_mediapipe(self) -> None:
        try:
            import mediapipe as mp

            self._face_detector = mp.solutions.face_detection.FaceDetection(
                model_selection=0,
                min_detection_confidence=self.config.min_detection_confidence,
            )
            self.logger.info("MediaPipe Face Detection initialized")
        except Exception as exc:
            self.logger.warning("MediaPipe unavailable; face tracking disabled: %s", exc)
            self._face_detector = None

        try:
            import mediapipe as mp

            self._hand_detector = mp.solutions.hands.Hands(
                static_image_mode=False,
                max_num_hands=1,
                model_complexity=0,
                min_detection_confidence=self.config.min_hand_confidence,
                min_tracking_confidence=self.config.min_hand_confidence,
            )
            self.logger.info("MediaPipe Hands initialized")
        except Exception as exc:
            self.logger.warning("MediaPipe Hands unavailable; hand gesture detection disabled: %s", exc)
            self._hand_detector = None

    def read(self) -> FaceTrackResult:
        if self.mock:
            return self._mock_result()

        if self._camera is None:
            return self._mark_lost_if_needed()

        frame = self._camera.capture_array()
        self._frame_count += 1
        if self._frame_count % self.config.detect_every_n_frames != 0:
            return self._mark_lost_if_needed()

        self._last_hand_gesture = self._detect_hand_gesture(frame)

        if self._face_detector is None:
            return self._mark_lost_if_needed()

        results = self._face_detector.process(frame)
        detections = getattr(results, "detections", None)
        if not detections:
            return self._mark_lost_if_needed()

        detection = max(detections, key=lambda item: item.score[0] if item.score else 0.0)
        box = detection.location_data.relative_bounding_box
        center_x = box.xmin + box.width / 2
        center_y = box.ymin + box.height / 2

        gaze_x = self._normalize(center_x)
        gaze_y = self._normalize(center_y)
        confidence = float(detection.score[0]) if detection.score else 0.0
        result = FaceTrackResult(
            seen=True,
            gaze_x=gaze_x,
            gaze_y=gaze_y,
            confidence=confidence,
            frame_width=self.config.width,
            frame_height=self.config.height,
        )
        self._last_result = result
        self._last_seen_at = time.monotonic()
        return result

    def hand_gesture(self) -> HandGesture:
        if self.mock:
            return HandGesture.UNKNOWN
        return self._last_hand_gesture

    def close(self) -> None:
        if self._face_detector is not None:
            self._face_detector.close()
        if self._hand_detector is not None:
            self._hand_detector.close()
        if self._camera is not None:
            self._camera.stop()

    def _mark_lost_if_needed(self) -> FaceTrackResult:
        if time.monotonic() - self._last_seen_at <= self.config.face_hold_s:
            return self._last_result
        return FaceTrackResult(False, frame_width=self.config.width, frame_height=self.config.height)

    def _mock_result(self) -> FaceTrackResult:
        t = time.monotonic() - self._started_at
        return FaceTrackResult(
            seen=True,
            gaze_x=math.sin(t * 0.8) * 0.75,
            gaze_y=math.sin(t * 0.45) * 0.35,
            confidence=1.0,
            frame_width=self.config.width,
            frame_height=self.config.height,
        )

    def _normalize(self, value: float) -> float:
        return max(-1.0, min(1.0, value * 2.0 - 1.0))

    def _detect_hand_gesture(self, frame) -> HandGesture:
        if self._hand_detector is None:
            return HandGesture.UNKNOWN

        results = self._hand_detector.process(frame)
        hands = getattr(results, "multi_hand_landmarks", None)
        if not hands:
            return HandGesture.UNKNOWN

        landmarks = hands[0].landmark
        xs = [point.x for point in landmarks]
        ys = [point.y for point in landmarks]
        min_x = max(0.0, min(xs))
        max_x = min(1.0, max(xs))
        min_y = max(0.0, min(ys))
        max_y = min(1.0, max(ys))
        width = max_x - min_x
        height = max_y - min_y
        area = width * height
        if area < self.config.min_hand_area_ratio:
            return HandGesture.UNKNOWN

        extended = self._extended_fingers(landmarks)
        gesture = self._classify_rps_gesture(extended, landmarks)
        self.logger.debug("hand gesture: %s fingers=%s area=%.2f", gesture.value, extended, area)
        return gesture

    def _classify_rps_gesture(self, extended: dict[str, bool], landmarks) -> HandGesture:
        thumb = extended["thumb"]
        index = extended["index"]
        middle = extended["middle"]
        ring = extended["ring"]
        pinky = extended["pinky"]
        non_thumb_count = sum((index, middle, ring, pinky))

        if thumb and index and not middle and not ring and not pinky and self._looks_like_finger_gun(landmarks):
            return HandGesture.GUN
        if non_thumb_count <= 1:
            return HandGesture.ROCK
        if index and middle and not ring and not pinky:
            return HandGesture.SCISSORS
        if non_thumb_count >= 3:
            return HandGesture.PAPER
        return HandGesture.UNKNOWN

    def _extended_fingers(self, landmarks) -> dict[str, bool]:
        wrist = landmarks[0]
        fingers = {
            "thumb": (4, 2),
            "index": (8, 5),
            "middle": (12, 9),
            "ring": (16, 13),
            "pinky": (20, 17),
        }
        extended = {}
        for name, (tip_index, base_index) in fingers.items():
            tip_distance = self._landmark_distance(wrist, landmarks[tip_index])
            base_distance = self._landmark_distance(wrist, landmarks[base_index])
            extended[name] = tip_distance >= base_distance * self.config.finger_extension_ratio
        return extended

    def _count_extended_fingers(self, landmarks) -> int:
        return sum(self._extended_fingers(landmarks).values())

    def _landmark_distance(self, a, b) -> float:
        dz = getattr(a, "z", 0.0) - getattr(b, "z", 0.0)
        return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + dz**2)

    def _looks_like_finger_gun(self, landmarks) -> bool:
        wrist = landmarks[0]
        thumb_tip = landmarks[4]
        thumb_mcp = landmarks[2]
        index_tip = landmarks[8]
        index_mcp = landmarks[5]
        middle_tip = landmarks[12]
        ring_tip = landmarks[16]
        pinky_tip = landmarks[20]
        middle_mcp = landmarks[9]
        ring_mcp = landmarks[13]
        pinky_mcp = landmarks[17]

        index_vec = self._vector(index_mcp, index_tip)
        thumb_vec = self._vector(thumb_mcp, thumb_tip)
        index_len = self._vector_length(index_vec)
        thumb_len = self._vector_length(thumb_vec)
        palm_width = max(0.001, self._landmark_distance(index_mcp, pinky_mcp))
        if index_len < palm_width * 0.72 or thumb_len < palm_width * 0.45:
            return False

        angle = self._angle_between(index_vec, thumb_vec)
        if not 45.0 <= angle <= 125.0:
            return False

        folded_tips = (middle_tip, ring_tip, pinky_tip)
        folded_bases = (middle_mcp, ring_mcp, pinky_mcp)
        folded_close = 0
        for tip, base in zip(folded_tips, folded_bases):
            if self._landmark_distance(tip, wrist) <= self._landmark_distance(base, wrist) * 1.15:
                folded_close += 1
        if folded_close < 2:
            return False

        thumb_index_gap = self._landmark_distance(thumb_tip, index_tip)
        if thumb_index_gap < palm_width * 0.45:
            return False

        palm_height = max(0.001, self._landmark_distance(wrist, middle_mcp))
        palm_aspect = palm_width / palm_height
        if palm_aspect > 1.75:
            return False

        return True

    def _vector(self, a, b) -> tuple[float, float, float]:
        return (
            b.x - a.x,
            b.y - a.y,
            getattr(b, "z", 0.0) - getattr(a, "z", 0.0),
        )

    def _vector_length(self, vector: tuple[float, float, float]) -> float:
        return math.sqrt(vector[0] ** 2 + vector[1] ** 2 + vector[2] ** 2)

    def _angle_between(self, a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
        len_a = self._vector_length(a)
        len_b = self._vector_length(b)
        if len_a <= 0.0001 or len_b <= 0.0001:
            return 0.0
        dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
        cosine = max(-1.0, min(1.0, dot / (len_a * len_b)))
        return math.degrees(math.acos(cosine))
