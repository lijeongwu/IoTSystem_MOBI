from __future__ import annotations

import time
import math
import logging
from dataclasses import dataclass
from typing import Any

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
        self.logger = logging.getLogger("mobi.vision")
        self.config = config
        self.mock = mock
        self._frame_count = 0
        self._last_detection = FaceDetection(None, None, 0, 0, config.width, config.height, False)
        self._last_seen_at = 0.0
        self._cap = None
        self._picamera2 = None
        self._camera_backend = "mock" if mock else "none"
        self._read_failures = 0
        self._yolo = None

        self._face_cascade = None
        if config.backend == "haar":
            self._setup_haar()
        elif config.backend == "yolo":
            self._setup_yolo()
        else:
            raise ValueError(f"Unsupported vision backend: {config.backend}")

        if not mock:
            self._setup_camera()

    def _setup_haar(self) -> None:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self._face_cascade = cv2.CascadeClassifier(cascade_path)

    def _setup_yolo(self) -> None:
        try:
            from ultralytics import YOLO

            self._yolo = YOLO(self.config.yolo_model)
        except Exception as exc:
            print(f"[vision] YOLO unavailable, falling back to Haar Cascade: {exc}")
            self.config = VisionConfig(
                camera_index=self.config.camera_index,
                width=self.config.width,
                height=self.config.height,
                detect_every_n_frames=self.config.detect_every_n_frames,
                lost_after_s=self.config.lost_after_s,
                backend="haar",
            )
            self._setup_haar()

    def _setup_camera(self) -> None:
        self._cap = cv2.VideoCapture(self.config.camera_index)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        if self._cap.isOpened() and self._opencv_can_read_frame():
            self._camera_backend = f"opencv:{self.config.camera_index}"
            self.logger.info("camera opened with OpenCV index %s", self.config.camera_index)
            return

        if self._cap is not None:
            self._cap.release()
        self._cap = None
        self._setup_picamera2()

    def _opencv_can_read_frame(self) -> bool:
        if self._cap is None:
            return False
        for _ in range(3):
            ok, frame = self._cap.read()
            if ok and frame is not None:
                return True
        self.logger.warning("OpenCV camera index %s opened but did not return frames", self.config.camera_index)
        return False

    def _setup_picamera2(self) -> None:
        try:
            from picamera2 import Picamera2

            camera = Picamera2()
            config = camera.create_preview_configuration(main={"size": (self.config.width, self.config.height)})
            camera.configure(config)
            camera.start()
            self._picamera2 = camera
            self._camera_backend = "picamera2"
            self.logger.info("camera opened with Picamera2")
        except Exception as exc:
            print(f"[vision] camera unavailable, using mock vision: {exc}")
            self.mock = True
            self._cap = None
            self._camera_backend = "mock"

    def read(self) -> FaceDetection:
        if self.mock:
            return self._mock_detection()

        frame = self._read_frame()
        if frame is None:
            self._read_failures += 1
            if self._read_failures == 1 or self._read_failures % 30 == 0:
                self.logger.warning("camera frame unavailable from %s", self._camera_backend)
            return self._mark_lost_if_needed()
        self._read_failures = 0

        frame = cv2.resize(frame, (self.config.width, self.config.height))
        self._frame_count += 1

        if self._frame_count % self.config.detect_every_n_frames != 0:
            return self._mark_lost_if_needed()

        if self.config.backend == "yolo":
            return self._detect_with_yolo(frame)
        return self._detect_with_haar(frame)

    def _detect_with_haar(self, frame) -> FaceDetection:
        if self._face_cascade is None:
            return self._mark_lost_if_needed()

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self._face_cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5, minSize=(45, 45))
        if len(faces) == 0:
            return self._mark_lost_if_needed()

        x, y, w, h = max(faces, key=lambda box: box[2] * box[3])
        return self._save_detection(x, y, w, h)

    def _detect_with_yolo(self, frame) -> FaceDetection:
        if self._yolo is None:
            return self._mark_lost_if_needed()

        results = self._yolo.predict(frame, conf=self.config.yolo_confidence, verbose=False)
        if not results:
            return self._mark_lost_if_needed()

        result = results[0]
        names = getattr(result, "names", None) or getattr(self._yolo, "names", {})
        best_box = None
        best_area = 0.0

        for box in getattr(result, "boxes", []):
            class_id = int(box.cls[0])
            class_name = self._class_name(names, class_id)
            if class_name not in self.config.yolo_target_classes:
                continue

            x1, y1, x2, y2 = [float(value) for value in box.xyxy[0]]
            area = (x2 - x1) * (y2 - y1)
            if area > best_area:
                best_area = area
                best_box = (x1, y1, x2, y2)

        if best_box is None:
            return self._mark_lost_if_needed()

        x1, y1, x2, y2 = best_box
        return self._save_detection(int(x1), int(y1), int(x2 - x1), int(y2 - y1))

    def _class_name(self, names: Any, class_id: int) -> str:
        if isinstance(names, dict):
            return str(names.get(class_id, class_id))
        if isinstance(names, list) and 0 <= class_id < len(names):
            return str(names[class_id])
        return str(class_id)

    def _save_detection(self, x: int, y: int, w: int, h: int) -> FaceDetection:
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
