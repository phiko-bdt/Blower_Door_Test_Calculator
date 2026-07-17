# Blower Door Test Calculator

라즈베리파이5 + PyQt6 + 1280×800 터치스크린으로 건물 기밀성능 시험(KS L ISO 9972 준용)을
수행하고 성적서 PDF 를 발행하는 현장 계측 앱. 실행: `python3 -m bdt` (바탕화면 아이콘).

## 아키텍처

- `bdt/paths.py` — 모든 파일 접근의 단일 소스 (절대경로). CWD 를 신뢰하지 말 것.
- `bdt/theme.py` — 앱 전체 색의 단일 소스. 화면(PyQt)·성적서 그래프(matplotlib)·
  성적서 HTML 이 전부 여기서 색을 가져간다. 성적서가 디자인 기준이다.
- `bdt/hardware.py` — 팬 PWM(sysfs)·압력센서(Modbus RTU). **pigpio 금지** (아래).
- `bdt/tasks.py` — QThread 작업. finished 는 성공/실패 무관하게 항상 오므로
  절대 finished 만으로 다음 단계로 넘어가지 말 것 (error/cancelled 로 판단).
- `bdt/flow.py` — 단일창 + QStackedWidget 페이지 전환. show_page 가 이전 페이지를
  deleteLater 한다 (파괴된 위젯으로 가던 시그널은 Qt 가 자동 해제).
- 시험 흐름: 조건 입력 → 준비(영기류 확인) → 목표 압력 조절(TargetingPage)
  → 측정(LiveMeasurementChart) → 계산 브리핑(CalculationSummary) → 성적서.

## 하드웨어 (라즈베리파이5)

- **pigpio 는 Pi5 에서 구조적으로 동작하지 않는다** ("unknown rev code c04171").
  GPIO 가 RP1 칩(PCIe 너머)에 있어서다. 커널 sysfs PWM(/sys/class/pwm)을 쓴다.
- 팬 PWM = **GPIO13 (물리핀 33)**. GPIO18·12 는 과거 TACH선 오배선으로 손상돼 폐기.
- PWM 컨트롤러는 **번호가 아니라 장치 이름으로** 찾는다: 팬 = `1f00098000.pwm`,
  CPU 쿨링팬 = `1f0009c000.pwm`(채널 3 — 건드리면 냉각 상실). 재부팅에 pwmchip
  번호가 실제로 뒤바뀐 적 있다.
- `/boot/firmware/config.txt` 필수 유지: `gpio=13=op,dl` (부팅 초기 LOW),
  `dtoverlay=pwm-2chan,pin=12,func=4,pin2=13,func2=4`, `dtparam=audio=off`
  (아날로그 오디오가 PWM 채널을 점유해 팬이 오작동하던 이력).
- 핀 레벨 확인은 `pinctrl get 13` (raspi-gpio 는 Pi5 미지원).
- 압력센서: /dev/ttyUSB0, Modbus RTU. 응답 CRC 검증 필수 유지 — 프레임 어긋남이
  -3174 Pa 같은 유령값의 원인이었다.
- 팬 전원은 수동 공급. duty 0 은 항상 안전, **duty>0 은 실제 팬이 돌므로 주의**.
- 안전장치 3중: config.txt 펌웨어 LOW → bdt-fan-stop.service(부팅) →
  .desktop 의 후행 `python3 -m bdt.fan_stop`(앱 크래시 대비).

## 운용 결정 (되돌리기 전에 사용자와 상의)

- **ISO 준용이지 엄밀 준수가 아니다**: 0 기류(baseline) 보정 생략, 온습도·대기압
  하드코딩(20°C/50%/101325Pa)은 빠른 측정·편의를 위한 의도적 결정.
- 측정 평균은 **산술평균 유지** (미디안 금지 — 바람은 노이즈가 아니라 신호,
  유령값은 CRC 검증이 원인 제거).
- 저압(10 Pa 미만) 측정점은 경고만 하고 회귀에 포함 (제외는 미결정).
- 용어는 KS L ISO 9972 원문 기준: 누기량·보정 누기 계수 C₀·기류 지수 n·
  누기 면적·누기 그래프·압력차 Δp.
- 팬 커버 기능은 폐기 (UI 없음, 계산부는 "none" 폴백).

## 검증 방법

- **회귀 스모크 (수정 후 항상)**: `QT_QPA_PLATFORM=offscreen python3 tests/smoke.py`
  — 하드웨어 모킹 종단 10검사, 약 30초, 전부 통과 시 종료코드 0.
- 문법·임포트: `python3 -m py_compile bdt/**/*.py` + `python3 -c "import bdt.flow"`
- GUI 캡처(하드웨어 미접촉): `QT_QPA_PLATFORM=offscreen` + hardware.pressure_read/
  duty_set 모킹 + `widget.grab().save(...)`. QChart 애니메이션은 실제 이벤트 루프
  시간이 필요하므로 QEventLoop+QTimer 로 기다릴 것 (processEvents 반복은 무효).
- 실화면 스크린샷: `WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 grim x.png`
  (scrot 은 검게 나옴).
- 성적서: `pdfinfo report.pdf`(Pages: 1), `pdftoppm -png` 후 Read 로 육안 확인.
  색 토큰 변경 시 graph.png md5 와 PDF 렌더 픽셀 비교로 불변 증명.
- 테스트가 conditions.json 등 실데이터를 만지면 **반드시 백업 후 복원**할 것
  (성적서에 test_period 가 실려 픽셀 비교가 깨진다).

## 함정 (실제로 겪은 것)

- QLineSeries 는 NaN 을 무시한다 — 선 끊기 트릭 불가, 시리즈를 나눠라.
- QLogValueAxis 는 10^n 에만 라벨 — 한 십진 구간(20~70 Pa) 데이터면 라벨이
  전혀 없다. 실시간 화면은 선형축 사용.
- QChartView 는 전역 스타일시트 배경을 받는다 — 차트가 직접 표면색을 칠할 것.
- SeriesAnimations + 주기적 replace() = 선이 영영 안 그려짐. 실시간 차트는
  NoAnimation.
- sysfs PWM export 직후 udev 권한 부여까지 ~50ms — 쓰기 가능해질 때까지 대기.
- 센서 읽기 실패를 매번 print 하면 터미널이 수만 줄로 뒤덮인다 (Terminal=true).
- 시험 데이터 형식: measured_value 는 [압력, duty] 쌍 — 계산부가 그대로 언팩
  하므로 형식을 바꾸지 말고 부가 정보는 별도 키(pressure_spread)로.

## git

- 커밋 작성자: `J Hong <128202933+JuhyuckHong@users.noreply.github.com>` (repo-local).
- 복귀 지점: 태그 `납품용-안전-마진`. 주 브랜치: main, 작업: rpi5.
- 성적서 출력을 바꾸는 변경은 커밋 메시지에 명시할 것 (픽셀 불변이 기본 기대).
