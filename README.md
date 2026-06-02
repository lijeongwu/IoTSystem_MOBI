# MOBI Raspberry Pi MVP

서보 1개로 머리를 좌우로 돌리고, 5인치 HDMI LCD에 표정을 띄우는 탁상형 반려로봇 MVP입니다.

## 목표 기능

- RGB 카메라로 얼굴의 좌우 위치를 감지합니다.
- SG-90 서보 1개로 머리를 좌우로 회전합니다.
- 5인치 HDMI LCD에 눈 표정과 상태를 표시합니다.
- TTP224 터치 센서 입력에 반응합니다.
- MPU6050 흔들림 입력에 반응합니다.
- 마이크/스피커 기능은 확장 지점으로 분리해 두었습니다.

## 파일 구성

```text
MOBI/
  README.md
  requirements.txt
  run_mobi.py
  mobi/
    __init__.py
    audio.py
    config.py
    face_ui.py
    imu.py
    main.py
    motion.py
    touch.py
    vision.py
```

## 배선 요약

### PCA9685 + SG-90

```text
PCA9685 VCC -> Raspberry Pi 3.3V
PCA9685 GND -> Raspberry Pi GND
PCA9685 SDA -> Raspberry Pi GPIO2 / SDA
PCA9685 SCL -> Raspberry Pi GPIO3 / SCL
PCA9685 V+  -> 외부 5V 서보 전원
SG-90       -> PCA9685 channel 0

외부 5V GND와 Raspberry Pi GND는 반드시 공통 접지
```

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

## 설치

라즈베리파이 OS에서:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

YOLO 인식을 사용할 경우:

```bash
pip install -r requirements-yolo.txt
```

I2C도 켜야 합니다.

```bash
sudo raspi-config
```

`Interface Options`에서 `I2C`를 활성화하세요.

## 실행

하드웨어 없이 PC에서 화면/로직만 확인:

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

카메라 번호가 다르면:

```bash
python run_mobi.py --camera-index 1
```

얼굴 인식 여부는 콘솔 로그로 확인할 수 있습니다.

```text
face detected: 얼굴을 처음 찾음
face tracking: 얼굴 위치와 서보 각도 추적 중
face lost: 얼굴을 놓침
```

더 자세히 보고 싶으면:

```bash
python run_mobi.py --log-level DEBUG
```

## 키보드 테스트

실행 중 키보드로 상태를 강제로 테스트할 수 있습니다.

```text
1: idle
2: happy
3: dizzy
4: listen
5: speak
Space: 정면으로 서보 복귀
Esc / Q: 종료
```

## 개발 순서 추천

1. `python run_mobi.py --mock`으로 표정 화면 확인
2. 라즈베리파이에서 LCD 출력 확인
3. PCA9685와 SG-90만 연결해서 서보 동작 확인
4. 카메라 연결 후 얼굴 추적 확인
5. TTP224 터치 반응 연결
6. MPU6050 흔들림 반응 연결
7. 음성 입출력 추가
