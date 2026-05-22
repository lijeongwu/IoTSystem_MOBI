from __future__ import annotations

import time
import math
from dataclasses import dataclass

import cv2

from .config import VisionConfig


@dataclass
class FaceDetection:
    x: int | None
    y: int | None
    w: int
    h: int
    frame_width: int
    frame_height: int
    seen: bool


class Vision:
    def __init__(self, config: VisionConfig, mock: bool = False):
        self.config = config
        self.mock = mock
        self._frame_count = 0
        self._last_detection = FaceDetection(None, None, 0, 0, config.width, config.height, False)
        self._last_seen_at = 0.0
        self._cap = None
        self._picamera2 = None

        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self._face_cascade = cv2.CascadeClassifier(cascade_path)

        if not mock:
            self._setup_camera()

    def _setup_camera(self) -> None:
        self._cap = cv2.VideoCapture(self.config.camera_index)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        if self._cap.isOpened():
            return

        self._cap.release()
        self._cap = None
        self._setup_picamera2()

    def _setup_picamera2(self) -> None:
        try:
            from picamera2 import Picamera2

            camera = Picamera2()
            config = camera.create_preview_configuration(main={"size": (self.config.width, self.config.height)})
            camera.configure(config)
            camera.start()
            self._picamera2 = camera
        except Exception as exc:
            print(f"[vision] camera unavailable, using mock vision: {exc}")
            self.mock = True
            self._cap = None

    def read(self) -> FaceDetection:
        if self.mock:
            return self._mock_detection()

        frame = self._read_frame()
        if frame is None:
            return self._mark_lost_if_needed()

        frame = cv2.resize(frame, (self.config.width, self.config.height))
        self._frame_count += 1

        if self._frame_count % self.config.detect_every_n_frames != 0:
            return self._mark_lost_if_needed()

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self._face_cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5, minSize=(45, 45))

        if len(faces) == 0:
            return self._mark_lost_if_needed()

        x, y, w, h = max(faces, key=lambda box: box[2] * box[3])
        detection = FaceDetection(
            x=int(x + w / 2),
            y=int(y + h / 2),
            w=int(w),
            h=int(h),
            frame_width=self.config.width,
            frame_height=self.config.height,
            seen=True,
        )
        self._last_detection = detection
        self._last_seen_at = time.monotonic()
        return detection

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
        if self._picamera2 is not None:
            self._picamera2.stop()

    def _read_frame(self):
        if self._cap is not None:
            ok, frame = self._cap.read()
            return frame if ok else None

        if self._picamera2 is not None:
            frame = self._picamera2.capture_array()
            return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        return None

    def _mark_lost_if_needed(self) -> FaceDetection:
        if time.monotonic() - self._last_seen_at > self.config.lost_after_s:
            return FaceDetection(None, None, 0, 0, self.config.width, self.config.height, False)
        return self._last_detection

    def _mock_detection(self) -> FaceDetection:
        t = time.monotonic()
        x = int((self.config.width / 2) + (self.config.width * 0.33) * math.sin(t * 0.7))
        return FaceDetection(x, self.config.height // 2, 80, 80, self.config.width, self.config.height, True)
