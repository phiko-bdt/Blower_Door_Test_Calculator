# Blower Door Test Calculator

라즈베리파이5 + PyQt6 + 1280×800 터치스크린으로 건물 기밀성능 시험(KS L ISO 9972 준용)을
수행하고 성적서 PDF 를 발행하는 현장 계측 앱. 실행: `python3 -m bdt` (바탕화면 아이콘).

부팅하면 `~/.config/labwc/autostart` 가 앱을 자동으로 띄우고 **전체화면**으로 연다
(원본 사본은 저장소의 `labwc-autostart`, 로그는 `~/bdt-autostart.log`).
창 데코레이션이 없으므로 종료는 헤더 오른쪽 '종료' 버튼이 유일한 수단이다.
원격에서 볼 때는 `BDT_WINDOWED=1 python3 -m bdt` 로 창 모드.

## 아키텍처

- `bdt/paths.py` — 모든 파일 접근의 단일 소스 (절대경로). CWD 를 신뢰하지 말 것.
- `bdt/theme.py` — 앱 전체 색의 단일 소스. 화면(PyQt)·성적서 그래프(matplotlib)·
  성적서 HTML 이 전부 여기서 색을 가져간다. 성적서가 디자인 기준이다.
- `bdt/hardware.py` — 팬 PWM(sysfs)·압력센서(Modbus RTU). **pigpio 금지** (아래).
- `bdt/settings.py` — 측정 기준값(목표 압력·허용 오차·유지 시간·상한 등)의 단일
  소스. settings.json 에 저장되고 설정 페이지가 편집한다. **읽는 쪽은 항상
  `load()` 로 그때그때 읽는다** — 모듈 상수로 캐시하면 방금 바꾼 설정이 다음
  시험에 안 먹는다. 팬 보정식만은 예전부터 `fan_coefficients.json` 에 있고
  `calculation.py` 가 직접 읽으므로 파일을 옮기지 않는다 (기존 데이터·스크립트 호환).
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
- 안전장치 4중: config.txt 펌웨어 LOW → bdt-fan-stop.service(부팅) →
  .desktop 의 후행 `python3 -m bdt.fan_stop`(앱 크래시 대비) →
  **bdt-fan-guard.service(상시 감시)**. 앞 셋은 특정 시점에 한 번씩만 duty 0 을
  거는데, 앱이 측정 중 SIGKILL 로 죽거나 래퍼 없이 직접 실행한 앱이 비정상
  종료하면 팬이 도는 채 남을 수 있다. 감시는 1초마다 `bdt.fan_guard.app_running`
  으로 `-m bdt` 프로세스 유무를 확인해(정확 매칭 — fan_stop·fan_guard 자신은
  앱으로 오인 안 함), **앱이 없으면 duty 0 을 강제한다.** 앱이 있으면 손대지
  않는다(측정 중 팬이 도는 게 정상). 설치: `sudo cp bdt-fan-guard.service
  /etc/systemd/system/ && sudo systemctl enable --now bdt-fan-guard`.

## 운용 결정 (되돌리기 전에 사용자와 상의)

- **ISO 준용이지 엄밀 준수가 아니다**: 0 기류(baseline) 보정 생략, 온습도·대기압
  하드코딩(20°C/50%/101325Pa)은 빠른 측정·편의를 위한 의도적 결정.
- 측정 평균은 **산술평균 유지** (미디안 금지 — 바람은 노이즈가 아니라 신호,
  유령값은 CRC 검증이 원인 제거).
- 저압(10 Pa 미만) 측정점은 경고만 하고 **회귀에 포함한다** (제외하지 않기로 결정).
- 스윕 최저 지점은 `min_duty + 1` — duty_range 하한은 팬이 도는 경계라
  개체차에 따라 그 값에서 꺼질 수 있다. 측정점은 팬이 확실히 도는 자리여야 한다.
- 용어는 KS L ISO 9972 원문 기준: 누기량·보정 누기 계수 C₀·기류 지수 n·
  누기 면적·누기 그래프·압력차 Δp.
- 팬 커버 기능은 폐기 (UI 없음, 계산부는 "none" 폴백). 설정 페이지도 "none"
  커버만 편집하되, 저장 시 나머지 커버 항목은 손대지 않고 보존한다.
- **수렴 판정은 목표의 비율이다** (기본 10% → 목표 70 Pa 에서 ±7 Pa). 예전엔
  `target/10` 으로 코드에 박혀 있어 목표를 바꿔도 비율은 못 바꿨다.
- **팬 최소에서도 압력이 목표를 넘는 경우**(과도한 기밀·외풍)의 처리:
  - 압력이 시험 가능 상한(기본 100 Pa)을 넘으면 → `tasks.TestImpossible` →
    전용 "시험 불가" 화면. 장비 오류(`error`)와 **다른 시그널**(`impossible`)로
    구분한다 — 작업자가 장비를 의심하며 시간 쓰지 않게.
  - 상한 이내면 → `_find_upper_duty` 로 상한을 넘지 않는 가장 높은 팬 세기를
    실측 탐색해 거기서부터 최저 지점까지 훑는다. **최대 duty 로 올려 훑지 말 것**
    — 압력이 이미 목표를 넘었는데 팬을 더 돌리는 정반대 처리다 (실제 있던 버그).
- **성적서는 앱 안에서 보여준다** (외부 뷰어 금지). `report.pdf` 를 pdftoppm
  으로 이미지 렌더해 `ReportPage` 가 띄운다. 전체화면 단말에서 남의 창(evince)이
  위를 덮으면 작업자가 앱으로 못 돌아온다. 렌더는 reporting 작업이 백그라운드에
  미리 해 둔다. **성적서는 시험마다 바탕화면 `결과보고서/<연월일시>/` 에 사본을
  남긴다** — `report.pdf` 는 다음 시험이 덮어쓰므로. 파일명은 시각·시험 종류·
  체적(`202607171943_감압+가압_500㎥.pdf`). `paths.REPORTS_DIR` 은 정의만 있고
  아무도 안 써서 실제로 지난 성적서가 사라지던 걸 이 보관함이 메운다.
- **확인·알림 창은 `widgets.confirm`/`alert` (앱 자체 Dialog) 로만 띄운다.**
  QMessageBox 는 말풍선 아이콘·영문 Yes/No·창틀이 앱과 따로 놀아 전부 걷어냈다.
  버튼 문구는 '예/아니오'가 아니라 동작('종료'·'시험 중단'), 되돌릴 수 없는
  동작은 `danger=True`. 리뷰가 QMessageBox 를 다시 넣으려 하면 막을 것.
- **수렴 판정은 대기 루프가 압력 이동평균으로 실시간 센다** (`control.get_duty`,
  `SMOOTH_WINDOW=10`). 예전엔 루프당 한 번(약 5.5초 간격) 스냅샷으로만 판정해,
  delay 5초 동안 밴드를 들락거려도 카운트가 쌓여 '10초 연속 유지'가 사실은
  스냅샷 두 개였다. 이제 대기 중 읽는 값마다 최근 10점 평균을 밴드와 대조해
  세며, 벗어나면 0 으로 리셋한다. **화면 표시선도 같은 이동평균값**이라 선과
  판정이 어긋나지 않는다 (조절 화면 압력이 너무 들쭉날쭉해 도입). 단발
  스파이크는 평균이 흡수하고, PID 입력에는 원시 압력을 준다(제어는 지연 금지).
  측정 지점 확정값(measured_value)은 무관 — 그건 여전히 산술평균.
- **리버서블 팬 지원은 의도적으로 남긴 죽은 코드다 — 지우지 말 것.**
  `control.duty_transformation` 의 `min>max` 역방향 분기와
  `fan_coefficients.json` 의 forward/reverse 계수 분리가 해당한다. 현재 팬
  (9GV2048P0G201)은 비리버서블이라 duty_range 가 전부 [20,100]·forward==reverse
  라 도달하지 않지만, 리버서블 팬(구 OF-OD172SAP-Reversible)으로 돌아갈 여지를
  둔다. 리뷰가 '미사용 코드'로 지적하면 이 항목을 근거로 유지할 것.

## 검증 방법

- **회귀 스모크 (수정 후 항상)**: `QT_QPA_PLATFORM=offscreen python3 tests/smoke.py`
  — 하드웨어 모킹 종단 26검사, 약 1분, 전부 통과 시 종료코드 0.
  실데이터(conditions.json·raw·settings.json·fan_coefficients.json)와
  산출물 폴더(measurements/·conditions/·graphs/…)는 백업 후 복원하며, 스모크가
  새로 만든 파일은 지운다 (스모크용 가짜 측정이 실측 기록과 섞이지 않게).
  성적서 보관함도 가짜 바탕화면(임시 폴더)으로 돌려 실제 바탕화면을 안 건든다.
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

- **페이지의 최소 높이가 화면을 넘으면 전체화면이 조용히 풀린다.** 창이 화면보다
  커야 하는 상황이 되면 Qt/WM 이 fullscreen 을 포기한다 — 예외도 경고도 없이
  창틀과 작업표시줄이 그대로 남는다. 조건 입력 페이지가 최소 793 + 헤더 77 =
  870 > 800 이라 `stack.addWidget` 순간 풀렸다. 세로가 긴 페이지는 본문을
  QScrollArea 에 담아 최소 높이를 없앤다 (스모크가 페이지별 세로 예산을 검사).
- PyQt6 (apt 판)에는 **wayland 플랫폼 플러그인이 없다** — XWayland(xcb)로 뜬다.
  "Could not find the Qt platform plugin wayland" 로그는 정상이며, 전체화면·
  터치·차트 모두 xcb 에서 동작한다.
- `pkill -f "python3 -m bdt"` 는 **그 명령을 실행한 셸 자신도 죽인다** (명령줄에
  패턴이 들어 있다). PID 를 얻어 kill 하거나 패턴을 `bdt\.__main__` 로 좁힐 것.
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
