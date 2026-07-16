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
- Temperature and humidity sensor
- PWM controllable fan(s) with a control board (tested with pigpio on Raspberry Pi)

## Usage
Execute the graphical interface (the `bdt` package) which guides you through the complete workflow:
```bash
cd Blower_Door_Test_Calculator
python3 -m bdt
```
`python3 -m bdt` must be run from the repository root (or with the working directory / `PYTHONPATH` pointing at it) so that Python can import the `bdt` package.

The program proceeds in the following order:
1. **Measurement** – collect pressure data
2. **Calculation** – compute flow rates and ACH
3. **Graph** – plot the pressure–flow relationship
4. **Report** – generate an HTML/PDF report

For headless environments or additional options refer to the source code under `bdt/`.

## Running on Raspberry Pi
To control the fan using `pigpio` on a Raspberry Pi:

1. Clone this repository and enter the project directory:
   ```bash
   git clone <repo-url>
   cd Blower_Door_Test_Calculator
   ```
2. Install the `pigpio` daemon and enable it to start automatically:
   ```bash
   sudo apt update
   sudo apt install pigpio
   sudo systemctl enable pigpiod
   sudo systemctl start pigpiod
   ```
3. Install the Python dependencies using apt:
   ```bash
   sudo ./install_deps_apt.sh
   ```
4. Run the GUI with root privileges so the program can access GPIO and serial ports:
   ```bash
   sudo python3 -m bdt
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
5. Any additional `.deb` packages such as `pigpio` must also be copied beforehand and installed using `sudo dpkg -i package.deb`.

After installation run the GUI normally:
```bash
cd ~/Blower_Door_Test_Calculator
sudo python3 -m bdt
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
- `bdt/pages/` – the individual screens: `input_initial_values.py` (test condition input), `live_pressure.py` (pre-test live pressure view), `live_chart.py` (live measurement progress + pressure–flow scatter chart), `progress.py` (progress display).
- `bdt/hardware.py` – sensor input and fan PWM output hardware control.
- `bdt/control.py` – PWM–pressure PID control.
- `bdt/tasks.py` – background worker threads that run the measurement.
- `bdt/calculation.py` – fits the measured data to the power-law model and computes Q50/ACH50/leakage area (see below).
- `bdt/report/` – `graph.py` plots the pressure–flow relationship; `html.py` renders the HTML test report and converts it to a PDF via Chromium.
- `bdt/paths.py` – absolute paths for all resource and output files, independent of the current working directory.
- `bdt/config.py`, `bdt/theme.py`, `bdt/widgets.py` – runtime configuration, the shared design theme, and common widgets.

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
- 온도 및 습도 센서
- PWM 제어가 가능한 팬(테스트는 Raspberry Pi의 pigpio 기반)

### 사용 방법
`bdt` 패키지로 구현된 그래픽 인터페이스를 실행하여 전체 워크플로우를 진행합니다.
```bash
cd Blower_Door_Test_Calculator
python3 -m bdt
```
`python3 -m bdt`는 `bdt` 패키지를 import 할 수 있도록 반드시 저장소 루트에서(또는 작업 디렉터리·`PYTHONPATH`가 저장소를 가리키게 하여) 실행해야 합니다.

프로그램은 다음 순서로 진행됩니다.
1. **측정** – 압력 데이터를 수집합니다.
2. **계산** – 유량과 ACH를 계산합니다.
3. **그래프** – 압력과 유량 관계를 플로팅합니다.
4. **보고서** – HTML/PDF 보고서를 생성합니다.

GUI 없이 사용하거나 추가 옵션이 필요한 경우 `bdt/` 아래 소스 코드를 참고하세요.

### 라즈베리 파이에서 실행
Raspberry Pi에서 `pigpio`를 사용해 팬을 제어하려면 다음 단계를 따르세요.

1. 저장소를 클론한 후 디렉터리로 이동합니다.
   ```bash
   git clone <repo-url>
   cd Blower_Door_Test_Calculator
   ```
2. `pigpio` 데몬을 설치하고 자동 시작되도록 설정합니다.
   ```bash
   sudo apt update
   sudo apt install pigpio
   sudo systemctl enable pigpiod
   sudo systemctl start pigpiod
   ```
3. 의존성은 `apt`로 설치합니다:
   ```bash
   sudo ./install_deps_apt.sh
   ```
4. GPIO와 시리얼 포트 접근을 위해 루트 권한으로 GUI를 실행합니다.
   ```bash
   sudo python3 -m bdt
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
5. `pigpio` 같은 추가 `.deb` 패키지도 미리 복사해 `sudo dpkg -i package.deb`로 설치해야 합니다.

설치 후 GUI를 다음과 같이 실행합니다.
```bash
cd ~/Blower_Door_Test_Calculator
sudo python3 -m bdt
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
- `bdt/pages/` – 각 화면 모듈. `input_initial_values.py`(시험 조건 입력), `live_pressure.py`(측정 시작 전 실시간 압력 확인), `live_chart.py`(측정 진행 상황 + 압력-누기량 산점도), `progress.py`(진행 상황 표시).
- `bdt/hardware.py` – 센서 입력·팬 PWM 출력 하드웨어 제어.
- `bdt/control.py` – PWM-압력 PID 제어.
- `bdt/tasks.py` – 측정을 담당하는 백그라운드 작업 스레드.
- `bdt/calculation.py` – 측정 데이터를 거듭제곱 법칙 모델에 맞춰 Q50, ACH50, 누설 면적 등을 계산합니다 (아래 참고).
- `bdt/report/` – `graph.py`는 압력-유량 관계를 그래프로 저장하고, `html.py`는 HTML 성적서를 그린 뒤 Chromium으로 PDF를 생성합니다.
- `bdt/paths.py` – 작업 디렉터리와 무관하게 모든 리소스·산출물의 절대경로를 관리합니다.
- `bdt/config.py`, `bdt/theme.py`, `bdt/widgets.py` – 실행 환경 설정, 공통 디자인 테마, 공용 위젯.

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
