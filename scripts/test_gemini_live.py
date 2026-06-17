from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path
import sys
import time
import wave

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from google import genai
from google.genai import types

from mobi.config import MOBI_SYSTEM_PROMPT
from mobi.utils import load_env_file
from scripts.test_voice_chat import find_first_capture_device, play_wav


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test Gemini Live audio-to-audio conversation.")
    parser.add_argument("--env-file", default=str(REPO_ROOT / ".env"))
    parser.add_argument("--model", default="gemini-3.1-flash-live-preview")
    parser.add_argument("--record-device", default="auto", help="arecord device such as plughw:2,0 or auto.")
    parser.add_argument("--text", default=None, help="Send text to Live API instead of microphone audio.")
    parser.add_argument("--play-device", default="auto", help="Playback device for aplay fallback, or auto.")
    parser.add_argument("--player", default="auto", help="Playback command: auto, pw-play, paplay, or aplay.")
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--chunk-ms", type=int, default=100)
    parser.add_argument("--response-timeout", type=float, default=12.0)
    parser.add_argument("--voice", default="Puck")
    parser.add_argument("--output", default=str(REPO_ROOT / "tmp" / "mobi_live_reply.wav"))
    parser.add_argument("--no-play", action="store_true")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return parser.parse_args()


def write_pcm_wav(path: Path, pcm: bytes, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)


async def audio_chunks_from_arecord(device: str, seconds: float, chunk_ms: int):
    if device == "auto":
        found = find_first_capture_device()
        if found is None:
            raise RuntimeError("자동으로 마이크 장치를 찾지 못했습니다.")
        device = found
    print(f"[record] device: {device}", flush=True)
    print(f"{seconds:.1f}초 동안 말하세요...", flush=True)

    chunk_size = int(16000 * 2 * (chunk_ms / 1000.0))
    command = [
        "arecord",
        "-D",
        device,
        "-f",
        "S16_LE",
        "-r",
        "16000",
        "-c",
        "1",
        "-t",
        "raw",
        "-d",
        str(max(1, int(seconds))),
        "-q",
    ]
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdout is not None
    try:
        while True:
            chunk = await process.stdout.read(chunk_size)
            if not chunk:
                break
            yield chunk
    finally:
        return_code = await process.wait()
        if return_code != 0:
            stderr = b""
            if process.stderr is not None:
                stderr = await process.stderr.read()
            raise RuntimeError(stderr.decode(errors="replace").strip() or f"arecord failed: {return_code}")


async def run_live(args: argparse.Namespace) -> None:
    load_env_file(Path(args.env_file))
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY가 없습니다. .env 파일을 확인하세요.")

    client = genai.Client(api_key=api_key)
    output_path = Path(args.output)
    started_at = time.monotonic()
    first_audio_at: float | None = None
    audio_parts: list[bytes] = []
    text_parts: list[str] = []
    input_text_parts: list[str] = []
    output_text_parts: list[str] = []

    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        system_instruction=MOBI_SYSTEM_PROMPT,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=args.voice)
            )
        ),
        thinking_config=types.ThinkingConfig(thinking_budget=0),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )

    print(
        f"[config] model={args.model} voice={args.voice} "
        f"seconds={args.seconds} chunk_ms={args.chunk_ms}",
        flush=True,
    )
    async with client.aio.live.connect(model=args.model, config=config) as session:
        async def send_audio() -> None:
            if args.text:
                print(f"YOU: {args.text}", flush=True)
                await session.send_client_content(
                    turns={"role": "user", "parts": [{"text": args.text}]},
                    turn_complete=True,
                )
                return
            await session.send_realtime_input(activity_start=types.ActivityStart())
            async for chunk in audio_chunks_from_arecord(args.record_device, args.seconds, args.chunk_ms):
                await session.send_realtime_input(
                    audio=types.Blob(data=chunk, mime_type="audio/pcm")
                )
            await session.send_realtime_input(activity_end=types.ActivityEnd())
            await session.send_realtime_input(audio_stream_end=True)

        async def receive_audio() -> None:
            nonlocal first_audio_at
            async for message in session.receive():
                now = time.monotonic()
                server_content = message.server_content
                if server_content and server_content.input_transcription:
                    text = server_content.input_transcription.text or ""
                    if text:
                        input_text_parts.append(text)
                        print(f"[input] {text}", flush=True)
                if server_content and server_content.output_transcription:
                    text = server_content.output_transcription.text or ""
                    if text:
                        output_text_parts.append(text)
                        print(f"[output] {text}", flush=True)
                if message.data:
                    if first_audio_at is None:
                        first_audio_at = now
                        print(f"[timing] first_audio={first_audio_at - started_at:.2f}s", flush=True)
                    audio_parts.append(message.data)
                if message.text:
                    print(f"[text] {message.text}", flush=True)
                    text_parts.append(message.text)
                if server_content and server_content.turn_complete:
                    break

        send_task = asyncio.create_task(send_audio())
        receive_task = asyncio.create_task(receive_audio())
        try:
            await asyncio.wait_for(
                asyncio.gather(send_task, receive_task),
                timeout=args.seconds + args.response_timeout,
            )
        except asyncio.TimeoutError:
            print(f"[live] {args.response_timeout:.1f}초 동안 응답이 없어 종료합니다.", flush=True)
            receive_task.cancel()
            await session.close()

    await client.aio.aclose()

    pcm = b"".join(audio_parts)
    if not pcm:
        raise SystemExit("Live API에서 오디오 응답을 받지 못했습니다.")

    write_pcm_wav(output_path, pcm, sample_rate=24000)
    total = time.monotonic() - started_at
    if input_text_parts:
        print(f"YOU: {''.join(input_text_parts).strip()}")
    if output_text_parts:
        print(f"MOBI_TEXT: {''.join(output_text_parts).strip()}")
    if text_parts:
        print(f"TEXT: {''.join(text_parts).strip()}")
    print(f"Live wav: {output_path}")
    print(f"[timing] total={total:.2f}s audio_bytes={len(pcm)}")

    if not args.no_play:
        play_wav(output_path, args.player, args.play_device)


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    asyncio.run(run_live(args))


if __name__ == "__main__":
    main()
