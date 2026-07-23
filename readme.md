# Blower_Door_Test_Calculator

The Blower Door Test Calculator is a project aimed at calculating the air leakage of a building using the Blower Door Test method. This repository contains the necessary files and scripts to perform the calculations and generate useful visualizations.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Installation

1. Clone the repository
   ```bash
   git clone <repo-url>
   cd Blower_Door_Test_Calculator
   ```
2. Install dependencies (Raspberry Pi)
   ```bash
   sudo ./install_deps_apt.sh
   ```
   On other systems you may still use pip:
   ```bash
   pip3 install -r requirements.txt
   ```

## Hardware Requirements
- Differential pressure sensor capable of Modbus/serial communication
- PWM controllable fan(s) with a control board (Raspberry Pi 5 hardware PWM via kernel sysfs)

Temperature, humidity and barometric pressure are intentionally fixed
(20 °C / 50 % / 101325 Pa) — no environmental sensor is read.

## Usage
Execute the graphical interface (the `bdt` package) which guides you through the complete workflow:
```bash
cd Blower_Door_Test_Calculator
python3 -m bdt
```
`python3 -m bdt` must be run from the repository root (or with the working directory / `PYTHONPATH` pointing at it) so that Python can import the `bdt` package.

The program walks through the full field workflow:
1. **Condition input** – interior volume, fan count, and depressurisation / pressurisation selection
2. **Preparation** – confirm the zero-flow (baseline) pressure with the fan stopped
3. **Target adjustment** – auto-drive the fan (PID) to the target pressure (default 70 Pa)
4. **Measurement** – sweep several pressure points and record the arithmetic mean at each
5. **Calculation** – power-law regression → Q50 / ACH50 / leakage area
6. **Report** – an A4 PDF shown in-app, archived to the desktop `결과보고서` folder, and shareable by USB copy or phone QR

Depressurisation and pressurisation, when both are selected, run back to back (steps 2–4 repeat per direction). If the fan cannot reach a usable pressure (too airtight/draughty, or the space is too large, or the sensor is mis-wired) the app shows a dedicated *test-impossible* screen instead of measuring.

For headless environments or additional options refer to the source code under `bdt/`.

## Running on Raspberry Pi
The fan PWM uses the Raspberry Pi 5 hardware PWM through the kernel sysfs
interface (`/sys/class/pwm`). `pigpio` is **not** used — it does not work on
the Pi 5 (its GPIO lives on the RP1 chip across PCIe), so do not install or
enable `pigpiod`.

1. Clone this repository and enter the project directory:
   ```bash
   git clone <repo-url>
   cd Blower_Door_Test_Calculator
   ```
2. Map GPIO13 to the hardware PWM and keep it LOW from the first boot stage —
   add to `/boot/firmware/config.txt`, then reboot:
   ```
   gpio=13=op,dl
   dtoverlay=pwm-2chan,pin=12,func=4,pin2=13,func2=4
   dtparam=audio=off
   ```
   `dtparam=audio=off` is **required**: the analog audio driver claims the same
   PWM block and the fan misbehaves with audio enabled (this actually happened).
3. Install the Python dependencies using apt:
   ```bash
   sudo ./install_deps_apt.sh
   ```
4. Run the GUI as the normal desktop user (**not** with `sudo` — root-owned
   settings/report files would break later runs). The account must belong to
   the `gpio` and `dialout` groups for PWM and serial access:
   ```bash
   python3 -m bdt
   ```

## Offline Installation via USB
If the Raspberry Pi cannot connect to the internet, prepare the software on a PC and transfer it with a USB drive.

1. On a computer with internet access clone the repository and download the dependencies:
   ```bash
   git clone <repo-url>
   cd Blower_Door_Test_Calculator
   pip download -r requirements.txt -d packages
   ```
2. Copy the project directory and the `packages` folder to a USB drive.
3. Attach the USB to the Raspberry Pi and copy the files:
   ```bash
   sudo mount /dev/sda1 /mnt  # adjust device path as needed
   cp -r /mnt/Blower_Door_Test_Calculator ~/
   cp -r /mnt/packages ~/
   ```
4. Install the dependencies offline:
   ```bash
   pip install --no-index --find-links ~/packages -r ~/Blower_Door_Test_Calculator/requirements.txt
   ```
5. Any additional `.deb` packages must also be copied beforehand and installed using `sudo dpkg -i package.deb`.

After installation run the GUI normally:
```bash
cd ~/Blower_Door_Test_Calculator
python3 -m bdt
```

## GUI Launch Shortcut on Raspberry Pi
The repository ships a ready-made `BlowerDoorTest.desktop` launcher (`Exec=/usr/bin/python3 -m bdt`, `Path=` set to the repository root) so the GUI can be started by double-clicking a desktop icon:

1. Copy the launcher to the desktop and make it executable:
   ```bash
   cp /home/phiko/Blower_Door_Test_Calculator/BlowerDoorTest.desktop ~/Desktop/BlowerDoorTest.desktop
   chmod +x ~/Desktop/BlowerDoorTest.desktop
   ```
2. On Raspberry Pi OS the file manager may still show the icon as "untrusted" until it is marked trusted:
   ```bash
   gio set ~/Desktop/BlowerDoorTest.desktop metadata::trusted true
   ```
   (or right-click the icon → "Allow Launching")
3. Double-click the icon to run the GUI. The launcher's `Path=` entry sets the working directory to the repository root, which `python3 -m bdt` needs in order to find the `bdt` package.

If the repository lives somewhere other than `/home/phiko/Blower_Door_Test_Calculator`, edit the `Exec`/`Path`/`Icon` paths in `BlowerDoorTest.desktop` (both the copy in the repo and the one on the desktop) accordingly.


## bdt Package Structure
The program is organized as the `bdt` Python package, run as `python3 -m bdt`:

- `bdt/__main__.py` – entry point; sets up the Qt application, loads the font/theme, and starts the test flow.
- `bdt/flow.py` – the single `MainWindow` and `TestFlow`, which walks through the pages of the test in order.
- `bdt/pages/` – the individual screens: `input_initial_values.py` (test condition input), `settings_page.py` (measurement criteria + fan calibration editor), `live_pressure.py` (pre-test live pressure view), `targeting.py` (target pressure adjustment), `live_chart.py` (live measurement progress + pressure–flow scatter chart), `summary.py` (calculation briefing), `report_view.py` (in-app report viewer with USB copy and phone-share QR), `past_reports.py` (share past reports from the start screen without a new test), `share_panel.py` (shared 2-stage phone-share QR widget used by both the report and past-reports screens), `progress.py` (progress display and the error / test-impossible screens).
- `bdt/hardware.py` – sensor input and fan PWM output hardware control.
- `bdt/control.py` – PWM–pressure PID control.
- `bdt/tasks.py` – background worker threads that run the measurement.
- `bdt/calculation.py` – fits the measured data to the power-law model and computes Q50/ACH50/leakage area (see below).
- `bdt/report/` – `graph.py` plots the pressure–flow relationship; `html.py` renders the HTML test report and converts it to a PDF via Chromium.
- `bdt/settings.py` – measurement criteria (target pressure, tolerance, …) persisted in `settings.json`.
- `bdt/keyboard.py` – on-screen keyboard (Korean two-set automaton + numeric keypad) for the touch-only terminal.
- `bdt/web.py` – Flask file-share server (`bdt-web.service`) behind the built-in hotspot; serves the report archive to phones.
- `bdt/fan_stop.py`, `bdt/fan_guard.py` – fan-safety helpers: one-shot duty-0 at boot/app-exit, and a watchdog that forces duty 0 whenever the app is not running.
- `bdt/paths.py` – absolute paths for all resource and output files, independent of the current working directory.
- `bdt/config.py`, `bdt/theme.py`, `bdt/widgets.py`, `bdt/scale.py` – runtime configuration, the shared design theme, common widgets, and axis-scaling helpers.

Korean development notes (architecture decisions, hardware pitfalls, operating
rules) live in `CLAUDE.md`; the field manual is `MANUAL.md`, and a formatted,
illustrated PDF manual is generated at `docs/manual.pdf` by
`docs/build_manual.py` (screenshots via `docs/capture_screens.py`).

Running `python3 -m bdt` executes the full flow: measurement data are stored as JSON, then processed to produce a final HTML/PDF report along with graphs for documentation.


## Calculation Derivation
`bdt/calculation.py` fits the measured data to the power-law model:

$$
\dot{V} = C_0\,\Delta P^n
$$

The steps are:
1. Convert each pressure difference $\Delta P$ and flow rate $\dot{V}$ to natural-log form. Least-squares regression of $\ln\Delta P$ versus $\ln\dot{V}$ yields the exponent $n$ and intercept $\ln C$.
2. Compute air density and viscosity from temperature, humidity and barometric pressure. These correct $C$ to $C_0$ via
   $\displaystyle \frac{C_0}{C} = \left( \frac{\mu}{\mu_{\text{STP}}} \right)^{2n-1} \left( \frac{\rho}{\rho_{\text{STP}}} \right)^{1-n}$.

3. Estimate the standard errors of `n` and `ln(C)` and apply the Student t-distribution to provide 95% confidence limits.
4. Use the resulting coefficients to compute
   * `Q50` – the volumetric flow rate at 50 Pa,
   * `ACH50` – air changes per hour based on the interior volume, and
   * `AL50` – effective leakage area at 50 Pa.

The module also returns prediction bounds and `R^2` so the report includes uncertainty metrics.

## 한국어 안내

Blower Door Test Calculator는 블로어 도어 테스트를 통해 건물의 공기 누설량을 계산하기 위한 프로젝트입니다. 이 저장소에는 계산 수행과 시각화에 필요한 파일과 스크립트가 들어 있습니다.

### 라이선스
이 프로젝트는 MIT 라이선스로 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 확인하세요.

### 설치
1. 저장소를 클론합니다.
   ```bash
   git clone <repo-url>
   cd Blower_Door_Test_Calculator
   ```
2. 의존성을 설치합니다 (Raspberry Pi 기준)
   ```bash
   sudo ./install_deps_apt.sh
   ```
   다른 시스템에서는 pip 사용도 가능합니다:
   ```bash
   pip3 install -r requirements.txt
   ```

### 하드웨어 요구 사항
- Modbus/직렬 통신이 가능한 차압 센서
- PWM 제어가 가능한 팬 (Raspberry Pi 5 하드웨어 PWM, 커널 sysfs 사용 — pigpio 불필요)

온도·습도·대기압은 의도적으로 고정값(20°C/50%/101325Pa)을 쓰며 환경 센서를 읽지 않습니다.

### 사용 방법
`bdt` 패키지로 구현된 그래픽 인터페이스를 실행하여 전체 워크플로우를 진행합니다.
```bash
cd Blower_Door_Test_Calculator
python3 -m bdt
```
`python3 -m bdt`는 `bdt` 패키지를 import 할 수 있도록 반드시 저장소 루트에서(또는 작업 디렉터리·`PYTHONPATH`가 저장소를 가리키게 하여) 실행해야 합니다.

프로그램은 현장 시험 전 과정을 순서대로 안내합니다.
1. **조건 입력** – 실내 체적, 팬 수량, 감압/가압 선택
2. **준비** – 팬 정지 상태에서 영기류(baseline) 압력 확인
3. **목표 압력 조절** – 팬을 자동(PID) 제어해 목표 압력(기본 70 Pa)에 맞춤
4. **측정** – 여러 압력점을 순차 측정하고 각 지점의 산술평균을 기록
5. **계산** – 거듭제곱 법칙 회귀 → Q50 / ACH50 / 누기 면적
6. **성적서** – 앱 안에서 보는 A4 PDF. 바탕화면 `결과보고서` 폴더에 보관되며 USB 복사·폰 QR 로 공유

감압·가압을 모두 선택하면 방향별로 이어서(2~4단계 반복) 수행합니다. 팬으로 유효한 압력을 만들 수 없으면(과도한 기밀·외풍, 공간 과대, 센서 오배선) 측정 대신 전용 **시험 불가** 화면을 띄웁니다.

GUI 없이 사용하거나 추가 옵션이 필요한 경우 `bdt/` 아래 소스 코드를 참고하세요.

### 라즈베리 파이에서 실행
팬 PWM 은 Raspberry Pi 5 의 하드웨어 PWM 을 커널 sysfs(`/sys/class/pwm`)로
사용합니다. `pigpio` 는 쓰지 않습니다 — Pi 5 에서는 동작하지 않으므로
(GPIO 가 PCIe 너머 RP1 칩에 있음) 설치·활성화하지 마세요.

1. 저장소를 클론한 후 디렉터리로 이동합니다.
   ```bash
   git clone <repo-url>
   cd Blower_Door_Test_Calculator
   ```
2. GPIO13 을 하드웨어 PWM 에 물리고 부팅 첫 단계부터 LOW 로 고정합니다 —
   `/boot/firmware/config.txt` 에 아래 세 줄을 추가하고 재부팅하세요.
   ```
   gpio=13=op,dl
   dtoverlay=pwm-2chan,pin=12,func=4,pin2=13,func2=4
   dtparam=audio=off
   ```
   `dtparam=audio=off` 는 **필수**입니다 — 아날로그 오디오 드라이버가 같은
   PWM 블록을 점유해 팬이 오작동한 실제 이력이 있습니다.
3. 의존성은 `apt`로 설치합니다:
   ```bash
   sudo ./install_deps_apt.sh
   ```
4. GUI 는 일반 데스크톱 계정으로 실행합니다 (**`sudo` 금지** — settings.json·
   성적서가 root 소유가 되어 이후 일반 실행이 깨집니다). 실행 계정은 PWM·
   시리얼 접근을 위해 `gpio`·`dialout` 그룹에 속해 있어야 합니다.
   ```bash
   python3 -m bdt
   ```

### USB를 이용한 오프라인 설치
라즈베리 파이가 인터넷에 연결될 수 없다면 PC에서 소프트웨어를 준비해 USB로 옮길 수 있습니다.

1. 인터넷이 되는 PC에서 저장소를 클론하고 의존성을 다운로드합니다.
   ```bash
   git clone <repo-url>
   cd Blower_Door_Test_Calculator
   pip download -r requirements.txt -d packages
   ```
2. 프로젝트 디렉터리와 `packages` 폴더를 USB 드라이브에 복사합니다.
3. 라즈베리 파이에 USB를 연결해 파일을 복사합니다.
   ```bash
   sudo mount /dev/sda1 /mnt  # 필요에 따라 경로 수정
   cp -r /mnt/Blower_Door_Test_Calculator ~/
   cp -r /mnt/packages ~/
   ```
4. 오프라인으로 의존성을 설치합니다.
   ```bash
   pip install --no-index --find-links ~/packages -r ~/Blower_Door_Test_Calculator/requirements.txt
   ```
5. 추가 `.deb` 패키지도 미리 복사해 `sudo dpkg -i package.deb`로 설치해야 합니다.

설치 후 GUI를 다음과 같이 실행합니다.
```bash
cd ~/Blower_Door_Test_Calculator
python3 -m bdt
```

### 라즈베리 파이 바탕화면에서 GUI 실행
저장소에는 바로 사용 가능한 `BlowerDoorTest.desktop` 런처가 포함되어 있습니다 (`Exec=/usr/bin/python3 -m bdt`, `Path=`는 저장소 루트). 바탕화면에서 두 번 클릭해 GUI를 시작하려면:

1. 런처를 바탕화면에 복사하고 실행 권한을 부여합니다.
   ```bash
   cp /home/phiko/Blower_Door_Test_Calculator/BlowerDoorTest.desktop ~/Desktop/BlowerDoorTest.desktop
   chmod +x ~/Desktop/BlowerDoorTest.desktop
   ```
2. 라즈베리 파이 OS 파일관리자에서 아이콘이 "신뢰할 수 없음"으로 표시되면 신뢰 표시를 추가합니다.
   ```bash
   gio set ~/Desktop/BlowerDoorTest.desktop metadata::trusted true
   ```
   (또는 아이콘 우클릭 → "실행 허용")
3. 아이콘을 더블 클릭하면 GUI가 실행됩니다. 런처의 `Path=` 항목이 작업 디렉터리를 저장소 루트로 지정해주기 때문에 `python3 -m bdt`가 `bdt` 패키지를 찾을 수 있습니다.

저장소 위치가 `/home/phiko/Blower_Door_Test_Calculator`가 아니라면 `BlowerDoorTest.desktop`의 `Exec`/`Path`/`Icon` 경로를(저장소 내 파일과 바탕화면에 복사한 파일 모두) 상황에 맞게 수정하세요.

### bdt 패키지 구조
이 프로그램은 `bdt` 파이썬 패키지로 구성되어 있으며 `python3 -m bdt`로 실행합니다.

- `bdt/__main__.py` – 진입점. Qt 애플리케이션·폰트·테마를 준비하고 시험 절차를 시작합니다.
- `bdt/flow.py` – 단일 창(`MainWindow`)과 시험 절차 진행(`TestFlow`). 페이지를 순서대로 전환합니다.
- `bdt/pages/` – 각 화면 모듈. `input_initial_values.py`(시험 조건 입력), `settings_page.py`(측정 기준값·팬 보정식 편집), `live_pressure.py`(측정 시작 전 실시간 압력 확인), `targeting.py`(목표 압력 조절), `live_chart.py`(측정 진행 상황 + 압력-누기량 산점도), `summary.py`(계산 브리핑), `report_view.py`(앱 내 성적서 화면 — USB 복사·폰 공유 QR), `past_reports.py`(시험 없이 시작 화면에서 지난 성적서 공유), `share_panel.py`(성적서·이전 보고서 화면이 공유하는 2단계 폰 공유 QR 위젯), `progress.py`(진행 표시 및 오류·시험 불가 화면).
- `bdt/hardware.py` – 센서 입력·팬 PWM 출력 하드웨어 제어.
- `bdt/control.py` – PWM-압력 PID 제어.
- `bdt/tasks.py` – 측정을 담당하는 백그라운드 작업 스레드.
- `bdt/calculation.py` – 측정 데이터를 거듭제곱 법칙 모델에 맞춰 Q50, ACH50, 누설 면적 등을 계산합니다 (아래 참고).
- `bdt/report/` – `graph.py`는 압력-유량 관계를 그래프로 저장하고, `html.py`는 HTML 성적서를 그린 뒤 Chromium으로 PDF를 생성합니다.
- `bdt/settings.py` – 측정 기준값(목표 압력·허용 오차 등)의 단일 소스, `settings.json` 에 저장.
- `bdt/keyboard.py` – 온스크린 키보드 (한글 두벌식 오토마타 + 숫자 키패드).
- `bdt/web.py` – 성적서 공유 Flask 서버(`bdt-web.service`). 자체 핫스팟으로 폰에 성적서 목록을 서빙합니다.
- `bdt/fan_stop.py`, `bdt/fan_guard.py` – 팬 안전장치: 부팅·앱 종료 시 duty 0 일회 설정과, 앱이 없을 때 duty 0 을 강제하는 상시 감시.
- `bdt/paths.py` – 작업 디렉터리와 무관하게 모든 리소스·산출물의 절대경로를 관리합니다.
- `bdt/config.py`, `bdt/theme.py`, `bdt/widgets.py`, `bdt/scale.py` – 실행 환경 설정, 공통 디자인 테마, 공용 위젯, 축 눈금 보조.

개발 결정·하드웨어 함정·운용 규칙은 `CLAUDE.md`, 현장 사용 설명서는 `MANUAL.md` 에 있으며, 서식이 적용된 그림 포함 PDF 설명서는 `docs/build_manual.py`(스크린샷은 `docs/capture_screens.py`)가 `docs/manual.pdf` 로 생성합니다.

`python3 -m bdt`를 실행하면 이 단계들이 순차적으로 진행되며, 측정된 데이터는 JSON으로 저장되고 최종 HTML/PDF 보고서와 그래프가 생성됩니다.

### 계산 로직(`bdt/calculation.py`)
`bdt/calculation.py`는 측정 데이터를 다음의 거듭제곱 법칙 모델에 맞춥니다.

$$
\dot{V} = C_0\,\Delta P^n
$$

절차는 다음과 같습니다.
1. 각 압력 차이 $\Delta P$와 유량 $\dot{V}$를 자연로그로 변환하여 회귀 분석을 수행해 지수 $n$과 절편 $\ln C$를 구합니다.
2. 온도, 습도, 기압으로부터 공기 밀도와 점도를 계산하여 다음 식을 이용해 $C$를 $C_0$로 보정합니다.
   $\displaystyle \frac{C_0}{C} = \left( \frac{\mu}{\mu_{\text{STP}}} \right)^{2n-1} \left( \frac{\rho}{\rho_{\text{STP}}} \right)^{1-n}.$
3. `n`과 `ln(C)`의 표준 오차를 추정하고 t-분포를 사용해 95% 신뢰 구간을 제공합니다.
4. 얻어진 계수를 활용해
   * `Q50` – 50 Pa에서의 유량,
   * `ACH50` – 실내 부피를 기준으로 한 시간당 공기 교환 횟수,
   * `AL50` – 50 Pa에서의 등가 누설 면적
   을 계산합니다.

이 모듈은 예측 구간과 결정 계수 `R^2`도 반환하여 보고서에 불확실성을 표시합니다.
