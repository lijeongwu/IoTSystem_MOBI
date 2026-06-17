from __future__ import annotations

import argparse
from signal import pause
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mobi.config import TouchConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test TTP224 touch sensor GPIO inputs.")
    parser.add_argument("--head", type=int, default=22, help="TTP224 OUT3, head touch.")
    parser.add_argument("--back", type=int, default=23, help="TTP224 OUT4, back touch.")
    parser.add_argument("--bounce-time", type=float, default=TouchConfig.bounce_time_s)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        from gpiozero import Button
    except Exception as exc:
        raise SystemExit(f"gpiozero를 불러오지 못했습니다: {exc}")

    mapping = (
        ("OUT3 머리 happy", args.head),
        ("OUT4 등 happy", args.back),
    )

    buttons = []
    for label, pin in mapping:
        button = Button(pin, pull_up=False, bounce_time=args.bounce_time)
        button.when_pressed = lambda name=label, gpio=pin: print(f"TOUCH {name} GPIO{gpio}", flush=True)
        button.when_released = lambda name=label, gpio=pin: print(f"RELEASE {name} GPIO{gpio}", flush=True)
        buttons.append(button)

    print("TTP224 터치 테스트 시작. Ctrl+C로 종료.", flush=True)
    print("OUT3=머리 happy, OUT4=등 happy, OUT1/OUT2=사용 안 함", flush=True)
    try:
        pause()
    except KeyboardInterrupt:
        print("\n종료합니다.")
    finally:
        for button in buttons:
            button.close()


if __name__ == "__main__":
    main()
