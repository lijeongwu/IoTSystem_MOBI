# MOBI Raspberry Pi MVP

라즈베리파이에서 실행하는 탁상형 AI 반려로봇 MVP입니다. 현재 하드웨어 범위는 카메라, MPU6050, 마이크, 스피커, TTP224 터치 센서, 5인치 HDMI LCD입니다.

## 현재 목표 기능

- RGB 카메라로 얼굴 또는 사람 위치를 감지합니다.
- 5인치 HDMI LCD에 로봇 표정을 표시합니다.
- 감지된 사람 위치에 따라 화면 속 눈동자가 좌우로 움직입니다.
- TTP224 터치 센서 입력에 반응합니다.
- MPU6050 흔들림 입력에 반응합니다.
- 마이크로 음성을 인식하고 LLM 답변을 생성합니다.
- 스피커로 로봇의 답변을 출력합니다.

## 파일 구성

```text
MOBI/
  README.md
  requirements.txt
  requirements-yolo.txt
  requirements-llm.txt
  run_mobi.py
  mobi/
    __init__.py
    audio.py
    config.py
    face_ui.py
    imu.py
    llm.py
    main.py
    touch.py
    vision.py
```

## 모듈 역할

```text
run_mobi.py
- 프로그램 시작점

mobi/main.py
- 전체 실행 루프
- 카메라, 화면, 터치, IMU, 오디오, LLM 연결
- 키보드 테스트 입력 처리

mobi/config.py
- 카메라 해상도
- GPIO 핀 번호
- 흔들림 기준값
- 음성 인식/LLM 설정값

mobi/vision.py
- RGB Camera 담당
- 기본 Haar Cascade 얼굴 인식
- 선택적으로 YOLO 사람/얼굴 인식
- 감지 대상의 중심 x/y 좌표 계산

mobi/face_ui.py
- 5인치 HDMI LCD 표정 UI 담당
- idle, happy, dizzy, listen, speak, sleep 표정 출력
- 카메라 감지 방향에 따라 눈동자 좌우 이동

mobi/touch.py
- TTP224 정전식 터치 센서 담당
- 터치 입력을 GPIO로 읽음

mobi/imu.py
- MPU6050 담당
- x/y/z 가속도로 흔들림 감지

mobi/audio.py
- Microphone 음성 인식(STT)
- Speaker 음성 출력(TTS)

mobi/llm.py
- LLM 챗봇 응답 생성
- OPENAI_API_KEY가 있으면 OpenAI API 사용
- API 키가 없으면 테스트용 fallback 응답
```

## 배선 요약

### MPU6050

```text
VCC -> 3.3V
GND -> GND
SDA -> GPIO2 / SDA
SCL -> GPIO3 / SCL
```

### TTP224

```text
VCC  -> 3.3V
GND  -> GND
OUT1 -> GPIO17
OUT2 -> GPIO27
OUT3 -> GPIO22
OUT4 -> GPIO23
```

### RGB Camera

USB 카메라라면 USB 포트에 연결합니다. Pi Camera Module이라면 카메라 포트에 연결하고 라즈베리파이 설정에서 카메라가 활성화되어 있는지 확인합니다.

### Microphone / Speaker

USB 마이크와 USB 스피커를 쓰는 구성이 가장 단순합니다. HDMI LCD 스피커를 쓰는 경우 라즈베리파이의 오디오 출력 장치를 HDMI로 설정해야 할 수 있습니다.

## 설치

라즈베리파이 OS에서:

```bash
git clone https://github.com/lijeongwu/IoTSystem_MOBI.git
cd IoTSystem_MOBI
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

YOLO 인식을 사용할 경우:

```bash
pip install -r requirements-yolo.txt
```

LLM 대화 기능을 사용할 경우:

```bash
pip install -r requirements-llm.txt
```

마이크 입력에서 PyAudio 오류가 나면:

```bash
sudo apt install portaudio19-dev
pip install PyAudio
```

I2C도 켜야 합니다.

```bash
sudo raspi-config
```

`Interface Options`에서 `I2C`를 활성화하세요.

## 실행

하드웨어 없이 화면/로직만 확인:

```bash
python run_mobi.py --mock
```

라즈베리파이에서 실제 하드웨어 사용:

```bash
python run_mobi.py
```

YOLO로 사람 또는 커스텀 얼굴 모델을 인식하려면:

```bash
python run_mobi.py --vision-backend yolo
```

별도 YOLO 얼굴 모델 파일을 사용할 때:

```bash
python run_mobi.py --vision-backend yolo --yolo-model models/face.pt
```

마이크와 스피커로 LLM 대화를 사용할 때:

```bash
export OPENAI_API_KEY="YOUR_API_KEY"
python run_mobi.py --audio --conversation
```

실행 중 `V` 키를 누르면 한 번 듣고, 답변을 생성한 뒤 스피커로 말합니다. 현재 STT는 `SpeechRecognition`의 Google 음성 인식을 사용하므로 인터넷 연결이 필요합니다.

카메라 번호가 다르면:

```bash
python run_mobi.py --camera-index 1
```

## 얼굴 인식 로그

얼굴 인식 여부는 콘솔 로그로 확인할 수 있습니다.

```text
camera opened with OpenCV index 0: OpenCV로 카메라 열림
camera opened with Picamera2: Picamera2로 카메라 열림
face detected: 얼굴을 처음 찾음
face tracking: 얼굴 위치 추적 중
no face/person detected: 감지 대상 없음
face lost: 얼굴을 놓침
```

더 자세히 보고 싶으면:

```bash
python run_mobi.py --log-level DEBUG
```

기본 실행은 Haar Cascade 얼굴 인식이라 정면 얼굴을 주로 찾습니다. 사람 전체를 기준으로 테스트하려면 YOLO를 사용하세요.

```bash
python run_mobi.py --vision-backend yolo
```

## 키보드 테스트

실행 중 키보드로 상태를 강제로 테스트할 수 있습니다.

```text
1: idle
2: happy
3: dizzy
4: listen
5: speak
V: 마이크로 한 번 듣고 LLM 답변 말하기
Esc / Q: 종료
```

## 센서 연결 테스트 추천 순서

```text
1. python run_mobi.py --mock 으로 표정 화면 확인
2. 5인치 HDMI LCD 출력 확인
3. 카메라 연결 후 얼굴/사람 인식 확인
4. TTP224 터치 반응 연결
5. MPU6050 흔들림 반응 연결
6. 스피커 출력 확인
7. 마이크 입력 확인
8. LLM 대화 기능 연결
```
