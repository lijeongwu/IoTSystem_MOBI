from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from enum import Enum

from mobi.config import LiveConversationConfig, MOBI_SYSTEM_PROMPT


class LiveEventType(str, Enum):
    INPUT_TEXT = "input_text"
    OUTPUT_TEXT = "output_text"
    SPEAKING_STARTED = "speaking_started"
    SPEAKING_ENDED = "speaking_ended"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass(frozen=True)
class LiveEvent:
    type: LiveEventType
    text: str = ""


def load_env_file(path: str | Path) -> None:
    env_path = Path(path)
    if not env_path.is_absolute():
        env_path = Path.cwd() / env_path
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def is_allowed_speaker_name(name: str) -> bool:
    lowered = name.lower()
    if "hdmi" in lowered or "vc4" in lowered:
        return False
    return any(keyword in lowered for keyword in ("usb", "bluez", "bluetooth", "bt", "headset", "speaker", "device"))


def find_first_capture_device() -> str | None:
    try:
        result = subprocess.run(["arecord", "-l"], check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    for line in result.stdout.splitlines():
        match = re.search(r"card\s+(\d+):.*device\s+(\d+):", line)
        if match:
            return f"plughw:{match.group(1)},{match.group(2)}"
    return None


def find_pipewire_playback_target() -> str | None:
    try:
        result = subprocess.run(["wpctl", "status"], check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError):
        result = None

    if result is not None:
        in_sinks = False
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("Sinks:"):
                in_sinks = True
                continue
            if in_sinks and stripped.endswith(":") and not stripped.startswith("Sinks:"):
                in_sinks = False
            if not in_sinks:
                continue
            match = re.search(r".*?\*?\s*(\d+)\.\s+(.+?)(?:\s+\[|$)", stripped)
            if match and is_allowed_speaker_name(match.group(2)):
                return match.group(1)

    try:
        pactl = subprocess.run(["pactl", "list", "sinks", "short"], check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    for line in pactl.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and is_allowed_speaker_name(parts[1]):
            return parts[1]
    return None


class GeminiLiveController:
    def __init__(self, config: LiveConversationConfig, mock: bool = False):
        self.logger = logging.getLogger("mobi.live")
        self.config = config
        self.mock = mock
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._mic_muted = threading.Event()
        self._running = threading.Event()
        self._speaking = threading.Event()
        self._events: queue.Queue[LiveEvent] = queue.Queue()
        self._say_queue: queue.Queue[str] = queue.Queue()
        self._suppress_output_until = 0.0
        self.last_activity_at = time.monotonic()

    @property
    def running(self) -> bool:
        return self._running.is_set()

    @property
    def speaking(self) -> bool:
        return self._speaking.is_set()

    @property
    def mic_muted(self) -> bool:
        return self._mic_muted.is_set()

    def mark_activity(self, now: float | None = None) -> None:
        self.last_activity_at = now if now is not None else time.monotonic()

    def start(self, intro_text: str | None = None) -> None:
        if self.mock or not self.config.enabled or self.running:
            return
        self.last_activity_at = time.monotonic()
        self._mic_muted.clear()
        self._speaking.clear()
        while True:
            try:
                self._events.get_nowait()
            except queue.Empty:
                break
        if intro_text:
            self._say_queue.put(intro_text)
        self._thread = threading.Thread(target=self._thread_main, name="mobi-gemini-live", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._loop is not None and self._stop_event is not None:
            self._loop.call_soon_threadsafe(self._stop_event.set)

    def join(self, timeout: float = 2.0) -> None:
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def mute_mic(self, muted: bool) -> None:
        if muted:
            self._mic_muted.set()
            self.mark_activity()
        else:
            self._mic_muted.clear()

    def suppress_output(self, duration_s: float) -> None:
        self._suppress_output_until = max(self._suppress_output_until, time.monotonic() + duration_s)
        self.mark_activity()

    def say(self, text: str) -> None:
        if text:
            self._say_queue.put(text)

    def drain_events(self) -> list[LiveEvent]:
        events: list[LiveEvent] = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                return events

    def _emit(self, event_type: LiveEventType, text: str = "") -> None:
        self.last_activity_at = time.monotonic()
        self._events.put(LiveEvent(event_type, text))

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception as exc:
            self._events.put(LiveEvent(LiveEventType.ERROR, str(exc)))
        finally:
            self._running.clear()
            self._speaking.clear()
            self._events.put(LiveEvent(LiveEventType.STOPPED))

    async def _run(self) -> None:
        load_env_file(self.config.env_file)
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY가 없습니다.")

        try:
            from google import genai
            from google.genai import types
        except Exception as exc:
            raise RuntimeError(f"Gemini Live 라이브러리를 불러오지 못했습니다: {exc}") from exc

        record_device = self._resolve_record_device()
        play_target = self._resolve_play_target()
        client = genai.Client(api_key=api_key)

        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            system_instruction=MOBI_SYSTEM_PROMPT,
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.config.voice)
                )
            ),
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                    silence_duration_ms=self.config.silence_ms,
                ),
                activity_handling=types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
                turn_coverage=types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY,
            ),
        )

        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        self._running.set()
        arecord = await self._start_arecord(record_device)
        player: asyncio.subprocess.Process | None = None

        async with client.aio.live.connect(model=self.config.model, config=config) as session:
            async def send_mic() -> None:
                chunk_size = int(16000 * 2 * (self.config.chunk_ms / 1000.0))
                assert arecord.stdout is not None
                try:
                    while self._stop_event is not None and not self._stop_event.is_set():
                        chunk = await arecord.stdout.read(chunk_size)
                        if not chunk:
                            break
                        if self._mic_muted.is_set() or self._speaking.is_set():
                            continue
                        await session.send_realtime_input(audio=types.Blob(data=chunk, mime_type="audio/pcm"))
                finally:
                    try:
                        await session.send_realtime_input(audio_stream_end=True)
                    except Exception:
                        pass

            async def send_text_commands() -> None:
                while self._stop_event is not None and not self._stop_event.is_set():
                    try:
                        text = await asyncio.to_thread(self._say_queue.get, True, 0.1)
                    except queue.Empty:
                        continue
                    await session.send_client_content(
                        turns={"role": "user", "parts": [{"text": f"다음 문장만 그대로 말해. {text}"}]},
                        turn_complete=True,
                    )

            async def receive_and_play() -> None:
                nonlocal player
                while self._stop_event is not None and not self._stop_event.is_set():
                    async for message in session.receive():
                        if self._stop_event is not None and self._stop_event.is_set():
                            break
                        server_content = message.server_content
                        if server_content and server_content.input_transcription:
                            text = server_content.input_transcription.text or ""
                            if text:
                                self._emit(LiveEventType.INPUT_TEXT, text)
                        if server_content and server_content.output_transcription:
                            text = server_content.output_transcription.text or ""
                            if text:
                                self._emit(LiveEventType.OUTPUT_TEXT, text)
                        if message.data:
                            if time.monotonic() < self._suppress_output_until:
                                continue
                            if not self._speaking.is_set():
                                self._speaking.set()
                                self._emit(LiveEventType.SPEAKING_STARTED)
                            if player is None or player.returncode is not None:
                                player = await self._start_player(play_target)
                            assert player.stdin is not None
                            player.stdin.write(message.data)
                            await player.stdin.drain()
                        if server_content and server_content.turn_complete:
                            if player and player.stdin:
                                player.stdin.close()
                                await player.wait()
                                player = None
                            if self._speaking.is_set():
                                self._speaking.clear()
                                self._emit(LiveEventType.SPEAKING_ENDED)
                            break

            tasks = [
                asyncio.create_task(send_mic()),
                asyncio.create_task(send_text_commands()),
                asyncio.create_task(receive_and_play()),
                asyncio.create_task(self._stop_event.wait()),
            ]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                if not task.cancelled() and task.exception():
                    raise task.exception()

        await self._stop_process(arecord)
        if player is not None:
            await self._stop_process(player)
        await client.aio.aclose()

    def _resolve_record_device(self) -> str:
        if self.config.record_device != "auto":
            return self.config.record_device
        device = find_first_capture_device()
        if device is None:
            raise RuntimeError("마이크 장치를 자동으로 찾지 못했습니다.")
        self.logger.info("Live microphone: %s", device)
        return device

    def _resolve_play_target(self) -> str | None:
        if self.config.play_target == "none":
            return None
        if self.config.play_target != "auto":
            return self.config.play_target
        target = find_pipewire_playback_target()
        if target is None:
            raise RuntimeError("USB 또는 블루투스 PipeWire 출력 장치를 찾지 못했습니다.")
        self.logger.info("Live speaker target: %s", target)
        return target

    async def _start_arecord(self, device: str) -> asyncio.subprocess.Process:
        process = await asyncio.create_subprocess_exec(
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
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if process.stdout is None:
            raise RuntimeError("arecord stdout을 열지 못했습니다.")
        return process

    async def _start_player(self, target: str | None) -> asyncio.subprocess.Process:
        if shutil.which("pw-play") is None:
            raise RuntimeError("pw-play 명령을 찾지 못했습니다.")
        command = ["pw-play", "--rate", "24000", "--channels", "1", "--format", "s16"]
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

    async def _stop_process(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
