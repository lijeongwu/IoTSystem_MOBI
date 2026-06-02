from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass

from mobi.config import CameraConfig


@dataclass(frozen=True)
class FaceTrackResult:
    seen: bool
    gaze_x: float = 0.0
    gaze_y: float = 0.0
    confidence: float = 0.0
    frame_width: int = 0
    frame_height: int = 0


class CameraFaceTracker:
    def __init__(self, config: CameraConfig, mock: bool = False):
        self.logger = logging.getLogger("mobi.camera")
        self.config = config
        self.mock = mock
        self._camera = None
        self._detector = None
        self._frame_count = 0
        self._last_seen_at = 0.0
        self._last_result = FaceTrackResult(False, frame_width=config.width, frame_height=config.height)
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

            self._detector = mp.solutions.face_detection.FaceDetection(
                model_selection=0,
                min_detection_confidence=self.config.min_detection_confidence,
            )
            self.logger.info("MediaPipe Face Detection initialized")
        except Exception as exc:
            self.logger.warning("MediaPipe unavailable; face tracking disabled: %s", exc)
            self._detector = None

    def read(self) -> FaceTrackResult:
        if self.mock:
            return self._mock_result()

        if self._camera is None or self._detector is None:
            return self._mark_lost_if_needed()

        frame = self._camera.capture_array()
        self._frame_count += 1
        if self._frame_count % self.config.detect_every_n_frames != 0:
            return self._mark_lost_if_needed()

        results = self._detector.process(frame)
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

    def close(self) -> None:
        if self._detector is not None:
            self._detector.close()
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

