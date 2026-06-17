from __future__ import annotations

import argparse
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test SG-90 tail servo sweep.")
    parser.add_argument("--pin", type=int, default=18, help="BCM GPIO pin connected to the servo signal wire.")
    parser.add_argument("--center", type=float, default=90.0, help="Center angle in degrees.")
    parser.add_argument("--sweep", type=float, default=120.0, help="Total left-right sweep angle in degrees.")
    parser.add_argument("--cycles", type=int, default=8, help="Number of left-right cycles.")
    parser.add_argument("--step", type=float, default=4.0, help="Degrees to move per update.")
    parser.add_argument("--delay", type=float, default=0.012, help="Delay between updates in seconds.")
    parser.add_argument("--min-pulse", type=float, default=0.0005, help="Servo min pulse width in seconds.")
    parser.add_argument("--max-pulse", type=float, default=0.0025, help="Servo max pulse width in seconds.")
    parser.add_argument("--hold-center", type=float, default=0.4, help="Seconds to hold center before/after test.")
    return parser.parse_args()


def angle_range(start: float, stop: float, step: float):
    if step <= 0:
        raise ValueError("--step must be greater than 0")
    current = start
    if start <= stop:
        while current <= stop:
            yield current
            current += step
    else:
        while current >= stop:
            yield current
            current -= step


def main() -> None:
    args = parse_args()

    from gpiozero import AngularServo

    half_sweep = args.sweep / 2.0
    left = max(0.0, args.center - half_sweep)
    right = min(180.0, args.center + half_sweep)

    servo = AngularServo(
        args.pin,
        min_angle=0,
        max_angle=180,
        min_pulse_width=args.min_pulse,
        max_pulse_width=args.max_pulse,
        initial_angle=args.center,
    )

    print(f"SG-90 tail servo test on GPIO{args.pin}")
    print(f"Sweeping {left:.1f} deg <-> {right:.1f} deg around center {args.center:.1f} deg")
    print("Press Ctrl+C to stop.")

    try:
        servo.angle = args.center
        time.sleep(args.hold_center)

        for cycle in range(args.cycles):
            print(f"cycle {cycle + 1}/{args.cycles}: right")
            for angle in angle_range(left, right, args.step):
                servo.angle = angle
                time.sleep(args.delay)

            print(f"cycle {cycle + 1}/{args.cycles}: left")
            for angle in angle_range(right, left, args.step):
                servo.angle = angle
                time.sleep(args.delay)

        servo.angle = args.center
        time.sleep(args.hold_center)
    finally:
        servo.angle = args.center
        time.sleep(args.hold_center)
        servo.detach()
        servo.close()
        print(f"Servo returned to center {args.center:.1f} deg.")
        print("Servo test finished.")


if __name__ == "__main__":
    main()
