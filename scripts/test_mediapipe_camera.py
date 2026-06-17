from __future__ import annotations

import argparse
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test PiCamera2 + MediaPipe face detection.")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=360)
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--min-confidence", type=float, default=0.55)
    parser.add_argument("--no-preview", action="store_true", help="Print detections without opening a preview window.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    import cv2
    import mediapipe as mp
    from picamera2 import Picamera2

    try:
        camera = Picamera2()
        config = camera.create_preview_configuration(
            main={"format": "RGB888", "size": (args.width, args.height)}
        )
        camera.configure(config)
        camera.start()
        time.sleep(0.3)
    except Exception as exc:
        print(f"Picamera2 start failed: {exc}")
        print("Check: rpicam-hello --list-cameras")
        return

    detector = mp.solutions.face_detection.FaceDetection(
        model_selection=0,
        min_detection_confidence=args.min_confidence,
    )

    print("MediaPipe camera test started.")
    print(f"Resolution: {args.width}x{args.height}")
    print("Press q in the preview window to quit.")

    started_at = time.monotonic()
    frame_count = 0
    last_report_at = 0.0

    try:
        while time.monotonic() - started_at < args.seconds:
            frame = camera.capture_array()
            frame_count += 1

            results = detector.process(frame)
            detections = results.detections or []

            now = time.monotonic()
            if detections and now - last_report_at >= 0.5:
                best = max(detections, key=lambda item: item.score[0] if item.score else 0.0)
                box = best.location_data.relative_bounding_box
                score = best.score[0] if best.score else 0.0
                center_x = box.xmin + box.width / 2
                center_y = box.ymin + box.height / 2
                print(
                    "face detected "
                    f"score={score:.2f} "
                    f"center=({center_x:.2f}, {center_y:.2f}) "
                    f"box=({box.xmin:.2f}, {box.ymin:.2f}, {box.width:.2f}, {box.height:.2f})"
                )
                last_report_at = now
            elif not detections and now - last_report_at >= 1.0:
                print("no face")
                last_report_at = now

            if not args.no_preview:
                preview = frame.copy()
                for detection in detections:
                    box = detection.location_data.relative_bounding_box
                    x = int(box.xmin * args.width)
                    y = int(box.ymin * args.height)
                    w = int(box.width * args.width)
                    h = int(box.height * args.height)
                    score = detection.score[0] if detection.score else 0.0
                    cv2.rectangle(preview, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    cv2.putText(
                        preview,
                        f"{score:.2f}",
                        (x, max(18, y - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 255, 0),
                        2,
                    )
                cv2.imshow("MOBI MediaPipe Camera Test", preview)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        detector.close()
        camera.stop()
        if not args.no_preview:
            cv2.destroyAllWindows()

    elapsed = max(0.001, time.monotonic() - started_at)
    print(f"Done. frames={frame_count} fps={frame_count / elapsed:.1f}")


if __name__ == "__main__":
    main()
