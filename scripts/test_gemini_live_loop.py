from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path
import select
import signal
import sys
import termios
import time
import tty

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from google import genai
from google.genai import types

from mobi.config import MOBI_SYSTEM_PROMPT
from mobi.utils import load_env_file
from scripts.test_voice_chat import find_first_capture_device, find_pipewire_playback_target, listen_with_arecord


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Continuous Gemini Live audio loop test.")
    parser.add_argument("--env-file", default=str(REPO_ROOT / ".env"))
    parser.add_argument("--model", default="gemini-3.1-flash-live-preview")
    parser.add_argument("--record-device", default="auto", help="arecord device such as plughw:2,0 or auto.")
    parser.add_argument("--play-target", default="auto", help="pw-play target node/name, auto, or none.")
    parser.add_argument("--chunk-ms", type=int, default=80)
    parser.add_argument("--voice", default="Puck")
    parser.add_argument("--silence-ms", type=int, default=650)
    parser.add_argument("--trigger", choices=("immediate", "space", "wake", "either"), default="immediate")
    parser.add_argument("--wake-word", default="모비야")
    parser.add_argument("--wake-alias", action="append", default=["모비"])
    parser.add_argument("--wake-window", type=float, default=2.0)
    parser.add_argument("--wake-gain", type=float, default=4.0)
    parser.add_argument("--trigger-settle", type=float, default=0.35)
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return parser.parse_args()


def resolve_record_device(device: str) -> str:
    if device != "auto":
        return device
    found = find_first_capture_device()
    if found is None:
        raise SystemExit("마이크 장치를 자동으로 찾지 못했습니다.")
    return found


def resolve_play_target(target: str) -> str | None:
    if target == "none":
        return None
    if target != "auto":
        return target
    found = find_pipewire_playback_target()
    if found is None:
        raise SystemExit("USB 또는 블루투스 PipeWire 출력 장치를 찾지 못했습니다.")
    return found


async def start_arecord(device: str) -> asyncio.subprocess.Process:
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
        "-q",
    ]
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if process.stdout is None:
        raise RuntimeError("arecord stdout을 열지 못했습니다.")
    return process


async def start_player(target: str | None) -> asyncio.subprocess.Process:
    command = [
        "pw-play",
        "--rate",
        "24000",
        "--channels",
        "1",
        "--format",
        "s16",
    ]
    if target:
        command.extend(["--target", target])
    command.append("-")
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if process.stdin is None:
        raise RuntimeError("pw-play stdin을 열지 못했습니다.")
    return process


async def stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()


async def wait_for_space(stop: asyncio.Event) -> str:
    if not sys.stdin.isatty():
        raise RuntimeError("스페이스바 트리거는 TTY 터미널에서만 사용할 수 있습니다.")

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    try:
        print("[trigger] 스페이스바를 누르면 Live 대화가 시작됩니다.", flush=True)
        while not stop.is_set():
            readable, _, _ = select.select([sys.stdin], [], [], 0.1)
            if not readable:
                await asyncio.sleep(0)
                continue
            char = sys.stdin.read(1)
            if char == " ":
                print("[trigger] space", flush=True)
                return "space"
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    raise asyncio.CancelledError


async def wait_for_wake_word(args: argparse.Namespace, record_device: str, stop: asyncio.Event) -> str:
    wake_words = [args.wake_word, *args.wake_alias]
    normalized_wake_words = {word.replace(" ", "") for word in wake_words if word}
    display_words = ", ".join(sorted(normalized_wake_words))
    print(f"[trigger] wake words: {display_words}", flush=True)
    while not stop.is_set():
        text = await asyncio.to_thread(
            listen_with_arecord,
            record_device,
            args.wake_window,
            16000,
            "ko-KR",
            None,
            args.wake_gain,
            True,
        )
        if not text:
            continue
        print(f"[trigger input] {text}", flush=True)
        normalized_text = text.replace(" ", "")
        matched = next((word for word in normalized_wake_words if word in normalized_text), None)
        if matched:
            print(f"[trigger] wake word: {matched}", flush=True)
            return "wake"
    raise asyncio.CancelledError


async def wait_for_trigger(args: argparse.Namespace, record_device: str, stop: asyncio.Event) -> None:
    if args.trigger == "immediate":
        print("[trigger] immediate", flush=True)
        return

    trigger_stop = asyncio.Event()
    tasks = []
    if args.trigger in ("space", "either"):
        tasks.append(asyncio.create_task(wait_for_space(trigger_stop)))
    if args.trigger in ("wake", "either"):
        tasks.append(asyncio.create_task(wait_for_wake_word(args, record_device, trigger_stop)))
    tasks.append(asyncio.create_task(stop.wait()))

    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    trigger_stop.set()
    if stop.is_set():
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        return
    trigger_name = "unknown"
    for task in done:
        if task.cancelled():
            continue
        exc = task.exception()
        if exc:
            raise exc
        trigger_name = task.result()
    if pending:
        if trigger_name == "space":
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        else:
            print("[trigger] releasing trigger listener...", flush=True)
            await asyncio.gather(*pending, return_exceptions=True)
        if args.trigger_settle > 0:
            await asyncio.sleep(args.trigger_settle)
        print("[trigger] ready", flush=True)


async def run_loop(args: argparse.Namespace) -> None:
    load_env_file(Path(args.env_file))
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY가 없습니다. .env 파일을 확인하세요.")

    record_device = resolve_record_device(args.record_device)
    play_target = resolve_play_target(args.play_target)
    print(f"[record] device: {record_device}", flush=True)
    print(f"[playback] target: {play_target or 'default'}", flush=True)
    print("실시간 Live 대화 준비. Ctrl+C로 종료.", flush=True)

    client = genai.Client(api_key=api_key)
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
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                silence_duration_ms=args.silence_ms,
            ),
            activity_handling=types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
            turn_coverage=types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY,
        ),
    )

    speaking = asyncio.Event()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    await wait_for_trigger(args, record_device, stop)
    if stop.is_set():
        await client.aio.aclose()
        print("종료합니다.", flush=True)
        return
    print("실시간 Live 대화 시작. 말하면 모비가 답합니다.", flush=True)

    arecord = await start_arecord(record_device)
    player: asyncio.subprocess.Process | None = None
    player_started_at = 0.0

    async with client.aio.live.connect(model=args.model, config=config) as session:
        async def send_mic() -> None:
            chunk_size = int(16000 * 2 * (args.chunk_ms / 1000.0))
            assert arecord.stdout is not None
            try:
                while not stop.is_set():
                    chunk = await arecord.stdout.read(chunk_size)
                    if not chunk:
                        stderr = b""
                        if arecord.stderr is not None:
                            stderr = await arecord.stderr.read()
                        message = stderr.decode(errors="replace").strip()
                        raise RuntimeError(message or "마이크 스트림이 종료되었습니다.")
                    if speaking.is_set():
                        continue
                    await session.send_realtime_input(
                        audio=types.Blob(data=chunk, mime_type="audio/pcm")
                    )
            finally:
                await session.send_realtime_input(audio_stream_end=True)

        async def receive_and_play() -> None:
            nonlocal player, player_started_at
            turn_audio_bytes = 0
            turn_started_at = 0.0
            while not stop.is_set():
                async for message in session.receive():
                    if stop.is_set():
                        break

                    server_content = message.server_content
                    if server_content and server_content.input_transcription:
                        text = server_content.input_transcription.text or ""
                        if text:
                            print(f"[input] {text}", flush=True)

                    if server_content and server_content.output_transcription:
                        text = server_content.output_transcription.text or ""
                        if text:
                            print(f"[output] {text}", flush=True)

                    if message.data:
                        if not speaking.is_set():
                            speaking.set()
                            turn_started_at = time.monotonic()
                            turn_audio_bytes = 0
                            print("[state] speaking: mic muted", flush=True)
                        if player is None or player.returncode is not None:
                            player = await start_player(play_target)
                            player_started_at = time.monotonic()
                            print(f"[timing] first_audio={player_started_at - turn_started_at:.2f}s", flush=True)
                        assert player.stdin is not None
                        player.stdin.write(message.data)
                        await player.stdin.drain()
                        turn_audio_bytes += len(message.data)

                    if server_content and server_content.turn_complete:
                        if player and player.stdin:
                            player.stdin.close()
                            await player.wait()
                            player = None
                        if speaking.is_set():
                            elapsed = time.monotonic() - turn_started_at if turn_started_at else 0.0
                            print(
                                f"[state] listening: mic unmuted audio_bytes={turn_audio_bytes} "
                                f"turn={elapsed:.2f}s",
                                flush=True,
                            )
                        speaking.clear()
                        print("[state] waiting for next turn", flush=True)
                        break

        tasks = [
            asyncio.create_task(send_mic()),
            asyncio.create_task(receive_and_play()),
            asyncio.create_task(stop.wait()),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        stop.set()
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            if task.cancelled():
                continue
            exc = task.exception()
            if exc:
                raise exc

    await stop_process(arecord)
    if player is not None:
        await stop_process(player)
    await client.aio.aclose()
    print("종료합니다.", flush=True)


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    asyncio.run(run_loop(args))


if __name__ == "__main__":
    main()
