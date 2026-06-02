# MOBI Raspberry Pi MVP

MOBI는 책상 위에 놓이는 AI 반려로봇 MVP입니다. 현재 단계는 **PiCamera2 + MediaPipe 얼굴 추적**, **MPU6050 흔들림 감지**, **pygame 기반 800x480 표정 디스플레이**를 구현합니다.

서보 모터, SEN-12787, 하이파이브, 손 제스처, 총 맞기 제스처는 이번 단계에서 사용하지 않습니다. 화면에는 텍스트, 말풍선, 자막을 표시하지 않고 표정만 표시합니다.

## 현재 구현 목표

- PiCamera2에서 RGB 프레임을 읽습니다.
- MediaPipe Face Detection으로 사용자의 얼굴을 감지합니다.
- 얼굴 중심 좌표를 `gaze_x`, `gaze_y` 값으로 변환합니다.
- LCD의 MOBI 눈동자가 사용자의 얼굴 방향을 바라봅니다.
- MPU6050에서 흔들림이 감지되면 `dizzy` 표정을 표시합니다.
- 카메라나 센서 초기화가 실패해도 pygame 표정 화면은 계속 실행됩니다.
- 추후 LLM, TTS, 터치 센서, 손 제스처를 연결하기 쉽도록 public trigger 함수 구조를 둡니다.

## 파일 구성

```text
MOBI/
  README.md
  requirements.txt
  requirements-llm.txt
  run_mobi.py
  mobi/
    __init__.py
    main.py
    config.py
    audio.py
    llm.py
    camera/
      camera_face_tracker.py
    sensors/
      mpu6050_reader.py
    display/
      mobi_face.py
      expressions.py
      effects.py
    core/
      behavior_manager.py
```

## 모듈 역할

```text
run_mobi.py
- 프로그램 시작점

mobi/main.py
- 전체 실행 루프
- PiCamera2 얼굴 추적 결과 읽기
- MPU6050 흔들림 이벤트 읽기
- BehaviorManager와 MobiFace 연결
- 키보드 테스트 모드 제공

mobi/config.py
- 화면 크기, FPS, fullscreen 여부
- 카메라 해상도, MediaPipe confidence
- MPU6050 흔들림 threshold/cooldown
- 상태 지속 시간 설정

mobi/camera/camera_face_tracker.py
- PiCamera2 초기화
- MediaPipe Face Detection 실행
- 얼굴 중심 좌표를 gaze_x, gaze_y로 변환
- gaze_x/gaze_y는 -1.0에서 1.0 사이 값

mobi/sensors/mpu6050_reader.py
- MPU6050 초기화
- 가속도 값 읽기
- 흔들림 이벤트 판단

mobi/display/mobi_face.py
- pygame 화면 생성
- MOBI 눈, 동공, 입, 표정 그리기
- set_expression()
- set_gaze()
- trigger 함수 제공

mobi/display/expressions.py
- 표정 이름과 우선순위 정의

mobi/display/effects.py
- 깜빡임, 호흡, 흔들림, 반짝임 효과

mobi/core/behavior_manager.py
- 카메라/센서 이벤트를 바탕으로 어떤 표정을 보여줄지 결정
- 상태 지속 시간과 우선순위 관리

mobi/audio.py
- 추후 마이크 STT와 스피커 TTS 확장용

mobi/llm.py
- 추후 LLM 챗봇 응답 확장용
```

## 표정 상태

```text
idle       기본 대기 상태
look       얼굴을 인식하고 바라보는 상태
listening  추후 음성을 듣는 상태
thinking   추후 LLM 응답을 기다리는 상태
speaking   추후 TTS로 말하는 상태
dizzy      MPU6050 흔들림 반응
happy      추후 터치/긍정 이벤트 반응
surprised  추후 갑작스러운 이벤트 반응
sleepy     오랫동안 입력이 없을 때
error      카메라나 센서 오류 표현
```

## 필수 Public 함수

[mobi/display/mobi_face.py](mobi/display/mobi_face.py)의 `MobiFace`는 아래 함수를 제공합니다.

```python
set_expression(expression: str)
set_gaze(x: float, y: float)
trigger_face_detected(gaze_x: float, gaze_y: float)
trigger_face_lost()
trigger_shake_dizzy()
trigger_listening()
trigger_thinking()
start_speaking()
stop_speaking()
trigger_touch_happy()
trigger_surprised()
trigger_error()
trigger_highfive()
trigger_gun_hit()
```

`trigger_highfive()`와 `trigger_gun_hit()`은 이번 단계에서는 stub입니다.

## 설치

라즈베리파이에서 처음 받을 때:

```bash
git clone https://github.com/lijeongwu/IoTSystem_MOBI.git
cd IoTSystem_MOBI
```

PiCamera2는 라즈베리파이 OS 패키지로 설치합니다.

```bash
sudo apt update
sudo apt install python3-picamera2
```

가상환경은 시스템 PiCamera2 패키지를 볼 수 있게 만듭니다.

```bash
python -m venv --system-site-packages .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

I2C를 켭니다.

```bash
sudo raspi-config
```

`Interface Options`에서 `I2C`를 활성화하세요.

## 실행

카메라/MPU6050 없이 표정만 테스트:

```bash
python run_mobi.py --mock
```

실제 PiCamera2와 MPU6050으로 실행:

```bash
python run_mobi.py
```

LCD 전체 화면:

```bash
python run_mobi.py --fullscreen
```

더 자세한 로그:

```bash
python run_mobi.py --log-level DEBUG
```

## 키보드 테스트

센서나 카메라가 정상 동작하지 않아도 표정을 확인할 수 있습니다.

```text
1: idle
2: look
3: happy
4: listening
5: thinking
6: speaking
7: dizzy
8: surprised
9: sleepy
0: error
Arrow keys: gaze 이동
Space: speaking 시작/종료
Esc / Q: 종료
```

## 센서 연결 테스트 순서

```text
1. python run_mobi.py --mock
   - pygame 표정 화면과 키보드 테스트 확인

2. LCD 연결
   - 800x480 화면에 MOBI 얼굴이 잘 나오는지 확인

3. PiCamera2 확인
   - rpicam-hello --list-cameras
   - rpicam-hello
   - python run_mobi.py
   - 얼굴을 보이면 look 상태로 전환되는지 확인

4. MPU6050 확인
   - i2cdetect -y 1
   - 0x68 주소 확인
   - 흔들면 dizzy 표정이 나오는지 확인

5. 추후 마이크/스피커/LLM 연결
   - audio.py, llm.py, MobiFace의 listening/thinking/speaking trigger에 연결
```
