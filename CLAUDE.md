# Blower Door Test Calculator

라즈베리파이5 + PyQt6 + 1280×800 터치스크린으로 건물 기밀성능 시험(KS L ISO 9972
준용)을 수행하고 성적서 PDF 를 발행하는 현장 계측 앱. 실행 `python3 -m bdt`,
창 모드 `BDT_WINDOWED=1 python3 -m bdt`.

## 실행·부팅

- 부팅 시 `~/.config/labwc/autostart`(사본 `labwc-autostart`)가 앱을 `while`
  루프로 감싸 자동 실행. 로그 `~/bdt-autostart.log`.
- 데코레이션 없음 — 종료는 헤더 오른쪽 '종료' 버튼이 유일.
- 전체화면은 앱이 `showFullScreen()`(`bdt/__main__.py`)으로 건다. **resize 를
  먼저 부르지 말 것.** 뜬 뒤 `isFullScreen()` 을 몇 번 재확인해 재적용한다.
- WM(`~/.config/labwc/rc.xml`, 사본 `labwc-rc.xml`)의 windowRule 은 제목표시줄·
  작업표시줄만 없앤다. **rc.xml 에서 전체화면 토글 금지**(앱과 서로 토글됨).
- 크래시 재시작은 종료 코드로 판정: 정상 종료(종료 버튼·중복 실행)=`exit 0`
  (재시작 안 함), 크래시·SIGKILL·미처리 예외=`≠0`(재시작). 반복 크래시 30초
  백오프. 매 반복 후행 `fan_stop`.

## 아키텍처

- `paths.py` — 모든 파일 경로의 단일 소스(절대경로). CWD 신뢰 금지.
- `theme.py` — 앱·성적서 그래프(matplotlib)·성적서 HTML 색의 단일 소스. 성적서가
  디자인 기준.
- `hardware.py` — 팬 PWM(sysfs)·압력센서(Modbus RTU). **pigpio 금지**(하드웨어 참조).
- `settings.py` — 측정 기준값의 단일 소스(settings.json). **읽는 쪽은 항상
  `load()`**(모듈 상수 캐시 금지). 팬 보정식만은 `fan_coefficients.json` 에 있고
  `calculation.py` 가 직접 읽는다(옮기지 말 것).
- `tasks.py` — QThread 작업. finished 는 성공/실패 무관하게 오므로 **finished
  만으로 다음 단계로 넘어가지 말 것**(error/cancelled 로 판단).
- `keyboard.py` — 앱이 직접 그리는 온스크린 키보드(Qt 가상 키보드는 QtWidgets 에
  자동 팝업 안 됨). 한글 두벌식 오토마타. 입력창 `property("numeric")` 참이면 숫자
  키패드. 키는 NoFocus. 페이지 동작 버튼은 PageHeader actions(헤더 오른쪽)에 둔다.
- `flow.py` — 단일창 + QStackedWidget. show_page 가 이전 페이지 deleteLater.
- 시험 흐름: 조건 입력 → 준비(영기류 확인) → 목표 압력 조절(TargetingPage) →
  측정(LiveMeasurementChart) → 계산(CalculationSummary) → 성적서.

## 하드웨어 (Pi5)

- **pigpio 금지**(Pi5 미동작 — GPIO 가 RP1 칩). 커널 sysfs PWM(/sys/class/pwm).
- 팬 PWM = **GPIO13(핀 33)**. GPIO18·12 는 손상돼 폐기.
- PWM 컨트롤러는 **장치 이름으로** 찾는다: 팬 `1f00098000.pwm`, CPU 쿨링팬
  `1f0009c000.pwm`(채널 3 — 건드리면 냉각 상실). pwmchip 번호는 재부팅에 바뀔 수
  있음.
- `/boot/firmware/config.txt` 유지: `gpio=13=op,dl`,
  `dtoverlay=pwm-2chan,pin=12,func=4,pin2=13,func2=4`, `dtparam=audio=off`
  (오디오가 PWM 채널 점유).
- 핀 확인 `pinctrl get 13`(raspi-gpio 는 Pi5 미지원).
- 압력센서 /dev/ttyUSB0, Modbus RTU. **응답 CRC 검증 필수**(유령값 방지).
- 팬 전원 수동 공급. duty 0 은 안전, **duty>0 은 실제 팬 회전 — 주의**.
- 안전장치 5중: config.txt LOW → bdt-fan-stop.service(부팅) → 후행
  `python3 -m bdt.fan_stop` → 앱 atexit → **bdt-fan-guard.service(상시)**.
  fan_guard·fan_stop 은 `bdt.fan_guard.app_running` 으로 `-m bdt` 유무를 정확
  매칭해 **앱이 없을 때만 duty 0 을 강제**한다(측정 중엔 손대지 않음). 설치
  `sudo cp bdt-fan-guard.service /etc/systemd/system/ && sudo systemctl enable
  --now bdt-fan-guard`.

## 운용 규칙 (되돌리기 전 사용자와 상의)

- **ISO 준용**: 영기류 보정 생략, 온습도·대기압 하드코딩(20°C/50%/101325Pa) —
  의도적.
- 측정 평균은 **산술평균 유지**(미디안 금지).
- 저압(10 Pa 미만) 측정점은 경고만 하고 **회귀에 포함**.
- 스윕 최저 지점은 `min_duty + 1`(하한은 팬이 꺼질 수 있는 경계).
- 용어는 KS L ISO 9972: 누기량·보정 누기 계수 C₀·기류 지수 n·누기 면적·압력차 Δp.
- 팬 커버 기능 폐기(UI 없음, 계산부 "none" 폴백). 설정 저장 시 나머지 커버 항목은
  보존.
- **수렴 판정은 목표의 비율**(기본 10% → 70 Pa 에서 ±7 Pa). 대기 루프가 압력
  **이동평균**으로 실시간 카운트(`control.get_duty`, `SMOOTH_WINDOW=10`), 밴드
  이탈 시 0 리셋. 화면 표시선도 같은 이동평균. PID 입력엔 원시 압력(제어 지연
  금지). measured_value 는 산술평균.
- **시험 불가**는 장비 오류(`error`)와 다른 시그널(`impossible`)로 구분한다:
  - 팬 최소에서도 압력이 상한(기본 100 Pa) 초과 → `TestImpossible`. 상한 이내면
    `_find_upper_duty` 로 상한 안 넘는 최고 세기부터 훑는다(**최대 duty 로 올리지
    말 것**).
  - 팬 최대에서도 하한(`settings.min_pressure`, 기본 15 Pa) 미달 →
    `TestImpossible`. 하한 이상이면 최대 duty 부터 정상 스윕. 하한은 목표보다
    낮아야 함(settings 검증).
- **성적서는 앱 안에서**(외부 뷰어 금지). `report.pdf` 를 pdftoppm 렌더해
  `ReportPage` 표시. 시험마다 바탕화면 `결과보고서/<연월일시>/` 에 사본 보관
  (파일명 시각·종류·체적).
- **확인·알림은 `widgets.confirm`/`alert` 만**(QMessageBox 금지). 버튼 문구는
  동작('종료'·'시험 중단'), 되돌릴 수 없으면 `danger=True`.
- **리버서블 팬 지원은 죽은 코드지만 지우지 말 것**: `control.duty_transformation`
  의 `min>max` 분기, `fan_coefficients.json` 의 forward/reverse 분리. 현재 팬은
  비리버서블이라 미도달.

## 네트워크·성적서 공유

- **공유 = USB 복사 + 자체 AP 웹**(둘 다 성적서 화면). USB 버튼은 `/media/<user>/`
  마운트가 있을 때만(`paths.usb_mounts`, 2초 폴링).
- **폰 공유 2단계 QR = 공용 위젯 `pages/share_panel.SharePanel`**(성적서·이전
  보고서 화면 공유). 갱신·상태 로직(refresh)은 공유, 배치만 `wide` 분기(성적서
  =compact 120px, 시작 화면=wide 260px 좌우). 2초마다 AP·망 상태로 자신을 켜고
  끔(`available`·`state_changed`). 시작 화면은 숨을 때 '준비 안 됨' 표시.
- **QR 흐름은 두 단계 수동**: ① WiFi 접속 QR → ② 목록 주소 QR. **캡티브 자동
  열림에 의존하지 않는다**(인터넷 상단·Private DNS 로 안 뜰 수 있음). dnsmasq·
  nftables(bdt-captive)는 남겨 둠(납품 현장 도움).
- **'이전 보고서'는 시작 화면 헤더 버튼**(`reports_requested` →
  `TestFlow.show_reports`, 닫으면 `start()`). 목록은 `bdt.web` 이 서빙하는 바탕화면
  `결과보고서` 폴더.
- **AP 인터페이스 = 내장 wlan0 전용**(개발·납품 공통). 내장은 기존 WiFi 를 잡지
  않는다(client 프로파일 autoconnect 끔). 인터넷은 개발 시 USB 동글 wlan1
  (2.4GHz WiFi), 납품 현장엔 없음. `bdt-share` 는 `connection.interface-name
  wlan0` autoconnect·priority 10. wlan0 을 AP 로 올리면 내장 WiFi 인터넷이 끊기니
  전환 전 인터넷을 동글/유선으로 옮길 것.
  - 동글(rtl8192cu/RTL8188CUS) 개체차: client 스캔이 안 되는 불량 개체 있음(교체).
    2.4GHz 전용(5GHz WiFi 불가). NM 저장 64자 비번은 SSID 전용 원시 PSK(재사용 불가).
- `bdt.web`(Flask, bdt-web.service, 8080)이 `결과보고서` 서빙. QR: ①
  `web.wifi_qr_payload` → ② `web.base_url`(AP IP 10.42.0.1 우선). QR 은 segno
  (apt python3-segno), 없으면 주소 텍스트.
- AP 설정 재현 `setup-hotspot.sh [인터페이스] [SSID] [비번]`(기본 wlan0).
  인터페이스 고정. web.py 는 인터페이스 무관(`bdt-share` 에서 읽음).
- LAN 전용·인증 없음(AP 비번으로만 막음). 포트 8080 중복 점유 시 서비스 크래시
  루프 — 수동 `python3 -m bdt.web` 를 띄웠다면 정리.

## 검증

- **회귀 스모크(수정 후 항상)**: `QT_QPA_PLATFORM=offscreen python3 tests/smoke.py`
  (하드웨어 모킹 종단, 통과 시 exit 0). 실데이터·루트 산출물(report.pdf·graph.png·
  report_page.png = 픽셀 기준선)·산출물 폴더는 백업 후 복원.
- 문법·임포트: `python3 -m py_compile bdt/**/*.py` + `python3 -c "import bdt.flow"`.
- GUI 캡처: `QT_QPA_PLATFORM=offscreen` + hardware.pressure_read/duty_set 모킹 +
  `grab().save`. QChart 애니메이션은 QEventLoop+QTimer 로 대기(processEvents 무효).
- 실화면 스크린샷: `WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 grim
  x.png`(scrot 은 검게 나옴).
- 성적서: `pdfinfo report.pdf`(Pages:1), `pdftoppm -png` 후 육안. 색 토큰 변경 시
  graph.png md5·PDF 픽셀 비교.
- 테스트가 실데이터(conditions.json 등) 만지면 **백업 후 복원**(성적서 test_period
  로 픽셀 비교 깨짐).

## 함정

- **페이지 최소 높이/폭이 화면(1280×800)을 넘으면 전체화면이 조용히 풀린다.**
  세로 긴 페이지는 본문을 QScrollArea 에. 가변 길이 한 줄 라벨은
  `widgets.ElidedLabel`(최소 폭 0, 넘치면 … 생략). 최후 안전망
  `MainWindow.changeEvent` 가 키오스크에서 풀리면 재적용.
- PyQt6(apt)에 **wayland 플랫폼 플러그인 없음** — XWayland(xcb)로 뜸("Could not
  find the Qt platform plugin wayland" 로그 정상).
- `pkill -f "python3 -m bdt"` 는 **실행 셸도 죽인다** — PID 로 kill 하거나 패턴을
  `bdt\.__main__` 로 좁힐 것.
- QLineSeries 는 NaN 무시(선 끊기 불가 — 시리즈 분할). QLogValueAxis 는 10^n 에만
  라벨(단일 십진 구간이면 라벨 없음 — 실시간은 선형축). QChartView 는 전역
  스타일시트 배경을 받음(차트가 표면색 직접 칠). SeriesAnimations + 주기 replace()
  = 선 안 그려짐(실시간은 NoAnimation).
- sysfs PWM export 후 udev 권한까지 ~50ms 대기.
- 센서 읽기 실패 print 금지(터미널 폭주).
- measured_value 는 [압력, duty] 쌍 — 형식 바꾸지 말고 부가 정보는 별도
  키(pressure_spread).

## git

- 커밋 작성자 `BDT Bot <bdt@users.noreply.github.com>`(repo-local, 익명).
- 단일 브랜치 `main`. 복귀 지점 태그 `납품용-안전-마진`.
- 원격 `origin` = `github.com/phiko-bdt/...`. 인증은 SSH deploy key
  (`~/.ssh/bdt_org_deploy`, `core.sshCommand` 지정) — 개인 gh 로그인 안 씀. 개인
  사본 `github.com/JuhyuckHong/...`(private)는 이 머신과 분리.
- 성적서 출력을 바꾸는 변경은 커밋 메시지에 명시(픽셀 불변이 기본 기대).
