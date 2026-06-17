from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mobi.config import LlmConfig
from mobi.llm import LlmClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test MOBI Gemini text reply and optional Puck TTS.")
    parser.add_argument("--env-file", default=str(REPO_ROOT / ".env"))
    parser.add_argument("--prompt", default="안녕 모비야. 지금 기분이 어때?")
    parser.add_argument("--max-tokens", type=int, default=120)
    parser.add_argument("--tts", action="store_true", help="Also generate a wav file with Gemini TTS.")
    parser.add_argument("--output", default=str(REPO_ROOT / "tmp" / "mobi_gemini_tts.wav"))
    parser.add_argument("--show-raw", action="store_true", help="Print repr(reply) for truncated-text debugging.")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    client = LlmClient(LlmConfig(enabled=True, env_file=args.env_file, max_tokens=args.max_tokens))
    reply = client.reply(args.prompt)
    print(f"MOBI: {reply}")
    if args.show_raw:
        print(f"RAW: {reply!r}")

    if args.tts:
        output = client.synthesize_speech(reply, args.output)
        if output is None:
            raise SystemExit("TTS generation failed")
        print(f"TTS wav: {output}")


if __name__ == "__main__":
    main()
