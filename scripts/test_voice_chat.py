from __future__ import annotations

import argparse
import logging
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

import audioop
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import re

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mobi.audio import AudioIO
from mobi.config import AudioConfig, LlmConfig
from mobi.llm import LlmClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test MOBI voice chat: STT -> Gemini -> TTS wav -> playback.")
    parser.add_argument("--env-file", default=str(REPO_ROOT / ".env"))
    parser.add_argument("--language", default="ko-KR")
    parser.add_argument("--list-mics", action="store_true", help="List microphone device indexes and exit.")
    parser.add_argument("--list-speakers", action="store_true", help="List aplay playback devices and exit.")
    parser.add_argument("--mic-index", type=int, default=None, help="SpeechRecognition microphone device index.")
    parser.add_argument("--arecord-device", default=None, help="Use arecord device such as plughw:2,0 instead of PyAudio.")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--gain", type=float, default=4.0, help="Amplify arecord wav before STT.")
    parser.add_argument("--keep-recording", default=None, help="Keep the raw microphone wav at this path.")
    parser.add_argument("--listen-timeout", type=float, default=5.0)
    parser.add_argument("--phrase-limit", type=float, default=3.0)
    parser.add_argument("--ambient-duration", type=float, default=0.4)
    parser.add_argument("--max-tokens", type=int, default=120)
    parser.add_argument("--output", default=str(REPO_ROOT / "tmp" / "mobi_voice_reply.wav"))
    parser.add_argument("--typed", action="store_true", help="Type text instead of using the microphone.")
    parser.add_argument("--loop", action="store_true", help="Keep chatting until Ctrl+C.")
    parser.add_argument("--no-play", action="store_true", help="Generate wav without playing it.")
    parser.add_argument("--player", default="auto", help="Audio player command: auto, pw-play, paplay, or aplay.")
    parser.add_argument("--play-device", default="auto", help="aplay device such as plughw:3,0, auto, or none.")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return parser.parse_args()


def run_player(command: list[str]) -> bool:
    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL if quiet else None,
            stderr=subprocess.DEVNULL if quiet else None,
        )
        return True
    except subprocess.CalledProcessError as exc:
        print(f"[playback] 재생 실패: {exc}")
        return False


def playback_commands(path: Path, player: str, device: str | None = None) -> list[list[str]]:
    if device == "none":
        device = None

    if player == "auto":
        commands = []
        pipewire_target = None
        if device in (None, "auto"):
            pipewire_target = find_pipewire_playback_target()
        elif device:
            pipewire_target = device
        if shutil.which("pw-play") is not None and pipewire_target:
            print(f"[playback] pipewire target: {pipewire_target}")
            commands.append(["pw-play", "--target", pipewire_target, str(path)])
        if shutil.which("aplay") is not None:
            if device == "auto":
                found = find_first_playback_device()
                if found:
                    print(f"[playback] auto device: {found}")
                    commands.append(["aplay", "-D", found, str(path)])
            elif device:
                commands.append(["aplay", "-D", device, str(path)])
        return commands

    if shutil.which(player) is None:
        return []

    command = [player]
    player_name = Path(player).name
    original_device = device
    if player_name == "pw-play" and device:
        if device == "auto":
            device = find_pipewire_playback_target()
            if device is None:
                print("[playback] USB 또는 블루투스 PipeWire 출력 장치를 찾지 못했습니다.")
        if device:
            command.extend(["--target", device])
    if player_name == "aplay" and device:
        if device == "none":
            device = None
        elif device == "auto":
            device = find_first_playback_device()
            if device is None:
                print("[playback] USB 또는 블루투스 ALSA 출력 장치를 찾지 못했습니다.")
            else:
                print(f"[playback] auto device: {device}")
        if device:
            command.extend(["-D", device])
        elif original_device == "auto":
            return []
    command.append(str(path))
    return [command]


def play_wav(path: Path, player: str, device: str | None = None) -> bool:
    commands = playback_commands(path, player, device)
    if not commands:
        print(f"[playback] 사용할 수 있는 재생 명령을 찾지 못했습니다: {path}")
        return False

    for command in commands:
        print(f"[playback] command: {' '.join(command)}")
        if run_player(command):
            return True
    return False


def find_first_capture_device() -> str | None:
    try:
        result = subprocess.run(
            ["arecord", "-l"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    for line in result.stdout.splitlines():
        match = re.search(r"card\s+(\d+):.*device\s+(\d+):", line)
        if match:
            return f"plughw:{match.group(1)},{match.group(2)}"
    return None


def find_first_playback_device() -> str | None:
    try:
        result = subprocess.run(
            ["aplay", "-l"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    devices: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        match = re.search(r"card\s+(\d+):\s*([^,]+),\s*device\s+(\d+):", line)
        if match:
            card, name, device = match.groups()
            devices.append((name.lower(), f"plughw:{card},{device}"))

    for name, device in devices:
        if is_allowed_speaker_name(name):
            return device
    return None


def is_allowed_speaker_name(name: str) -> bool:
    lowered = name.lower()
    if "hdmi" in lowered or "vc4" in lowered:
        return False
    return any(keyword in lowered for keyword in ("usb", "bluez", "bluetooth", "bt", "headset", "speaker", "device"))


def find_pipewire_playback_target() -> str | None:
    try:
        result = subprocess.run(
            ["wpctl", "status"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

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
        if not match:
            continue
        node_id, name = match.groups()
        if is_allowed_speaker_name(name):
            return node_id
    pactl_target = find_pactl_playback_target()
    if pactl_target:
        return pactl_target
    return None


def find_pactl_playback_target() -> str | None:
    try:
        result = subprocess.run(
            ["pactl", "list", "sinks", "short"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        sink_name = parts[1]
        if is_allowed_speaker_name(sink_name):
            return sink_name
    return None


def list_playback_devices() -> list[str]:
    try:
        result = subprocess.run(
            ["aplay", "-l"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []

    devices = []
    for line in result.stdout.splitlines():
        match = re.search(r"card\s+(\d+):\s*([^,]+),\s*device\s+(\d+):\s*(.+)", line)
        if match:
            card, name, device, description = match.groups()
            status = "OK" if is_allowed_speaker_name(name) else "SKIP"
            devices.append(f"{status} plughw:{card},{device} - {name.strip()} - {description.strip()}")
    pipewire_target = find_pipewire_playback_target()
    if pipewire_target:
        devices.append(f"OK pipewire:{pipewire_target} - USB/Bluetooth target")
    return devices


def wav_rms(path: Path) -> int | None:
    try:
        import wave

        with wave.open(str(path), "rb") as wav_file:
            frames = wav_file.readframes(wav_file.getnframes())
            return audioop.rms(frames, wav_file.getsampwidth())
    except Exception:
        return None


def amplify_wav(source_path: Path, gain: float) -> Path:
    if gain <= 1.0:
        return source_path

    import wave

    amplified_path = source_path.with_name(f"{source_path.stem}_gain.wav")
    with wave.open(str(source_path), "rb") as source:
        params = source.getparams()
        frames = source.readframes(source.getnframes())
        amplified = audioop.mul(frames, source.getsampwidth(), gain)

    with wave.open(str(amplified_path), "wb") as output:
        output.setparams(params)
        output.writeframes(amplified)
    return amplified_path


def listen_with_arecord(
    device: str,
    seconds: float,
    sample_rate: int,
    language: str,
    keep_recording: str | None = None,
    gain: float = 1.0,
    quiet: bool = False,
) -> str | None:
    if shutil.which("arecord") is None:
        print("[record] arecord 명령을 찾을 수 없습니다.")
        return None
    if device == "auto":
        found_device = find_first_capture_device()
        if found_device is None:
            print("[record] 자동으로 마이크 장치를 찾지 못했습니다.")
            return None
        device = found_device
        print(f"[record] auto device: {device}")

    if keep_recording:
        wav_path = Path(keep_recording)
        wav_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            wav_path = Path(temp_file.name)

    command = [
        "arecord",
        "-D",
        device,
        "-f",
        "S16_LE",
        "-r",
        str(sample_rate),
        "-c",
        "1",
        "-d",
        str(max(1, int(seconds))),
        str(wav_path),
    ]
    if quiet:
        command.insert(1, "-q")

    try:
        if not quiet:
            print(f"{int(seconds)}초 동안 말하세요...")
        subprocess.run(command, check=True)
        rms = wav_rms(wav_path)
        if rms is not None and not quiet:
            print(f"[record] input rms: {rms}")
        stt_path = amplify_wav(wav_path, gain)
        if stt_path != wav_path and not quiet:
            boosted_rms = wav_rms(stt_path)
            print(f"[record] amplified rms: {boosted_rms}")

        import speech_recognition as sr

        recognizer = sr.Recognizer()
        with sr.AudioFile(str(stt_path)) as source:
            audio = recognizer.record(source)
        return recognizer.recognize_google(audio, language=language)
    except subprocess.CalledProcessError as exc:
        if not quiet:
            print(f"[record] 녹음 실패: {exc}")
    except Exception as exc:
        if not quiet:
            print(f"[stt] 음성 인식 실패: {type(exc).__name__}: {exc}")
    finally:
        if not keep_recording:
            try:
                wav_path.unlink()
            except OSError:
                pass
        try:
            if "stt_path" in locals() and stt_path != wav_path and not keep_recording:
                stt_path.unlink()
        except OSError:
            pass
    return None


def read_user_text(args: argparse.Namespace, audio: AudioIO | None) -> str | None:
    if args.typed:
        text = input("YOU> ").strip()
        return text or None

    if args.arecord_device:
        return listen_with_arecord(
            args.arecord_device,
            args.phrase_limit,
            args.sample_rate,
            args.language,
            args.keep_recording,
            args.gain,
        )

    print("마이크에 말하세요...")
    assert audio is not None
    return audio.listen_once()


def run_once(args: argparse.Namespace, audio: AudioIO | None, llm: LlmClient) -> bool:
    started_at = time.monotonic()
    user_text = read_user_text(args, audio)
    stt_done_at = time.monotonic()
    if not user_text:
        print("STT 결과가 없습니다. 다시 시도하세요.")
        return False

    print(f"YOU: {user_text}")
    reply = llm.reply(user_text)
    llm_done_at = time.monotonic()
    print(f"MOBI: {reply}")

    output = llm.synthesize_speech(reply, args.output)
    tts_done_at = time.monotonic()
    if output is None:
        print("TTS 생성 실패")
        return False

    print(f"TTS wav: {output}")
    if not args.no_play:
        play_wav(output, args.player, args.play_device)
    played_at = time.monotonic()
    print(
        "[timing] "
        f"stt={stt_done_at - started_at:.2f}s "
        f"llm={llm_done_at - stt_done_at:.2f}s "
        f"tts={tts_done_at - llm_done_at:.2f}s "
        f"play={played_at - tts_done_at:.2f}s "
        f"total={played_at - started_at:.2f}s"
    )
    return True


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.list_mics:
        names = AudioIO.microphone_names()
        if not names:
            print("마이크 목록을 읽지 못했습니다. PyAudio 설치를 확인하세요.")
            return
        for index, name in enumerate(names):
            print(f"{index}: {name}")
        return

    if args.list_speakers:
        devices = list_playback_devices()
        if not devices:
            print("스피커 출력 장치를 찾지 못했습니다.")
            return
        for device in devices:
            print(device)
        return

    audio = None
    if not args.typed and not args.arecord_device:
        audio = AudioIO(
            AudioConfig(
                enabled=True,
                language=args.language,
                microphone_device_index=args.mic_index,
                listen_timeout_s=args.listen_timeout,
                phrase_time_limit_s=args.phrase_limit,
                ambient_duration_s=args.ambient_duration,
            )
        )

    llm = LlmClient(LlmConfig(enabled=True, env_file=args.env_file, max_tokens=args.max_tokens))
    print(
        "[config] "
        f"llm_model={llm.model_name} "
        f"tts_model={llm.tts_model_name} "
        f"tts_voice={llm.tts_voice_name} "
        f"phrase_limit={args.phrase_limit}s "
        f"play_device={args.play_device} "
        f"max_tokens={args.max_tokens}"
    )

    try:
        while True:
            run_once(args, audio, llm)
            if not args.loop:
                break
    except KeyboardInterrupt:
        print("\n종료합니다.")


if __name__ == "__main__":
    main()
