"""백그라운드 작업 스레드.

측정(감압/가압)·계산·그래프·성적서 생성처럼 UI를 멈추면 안 되는 작업을
별도 QThread에서 수행하고, 진행 상황·측정점·현재 위치를 시그널로 알린다.
"""

import os
import json
import time
import shutil
import platform
import statistics
import traceback
from datetime import datetime

from PyQt6.QtCore import QThread, pyqtSignal

from bdt import hardware
from bdt import control
from bdt import calculation
from bdt.report import graph, html
from bdt import paths
from bdt.config import TEST_MODE


# 시험 조건
TARGET_PRESSURE = 70      # 측정 시작점으로 삼을 목표 압력차 (Pa)
MEASURE_SECONDS = 10      # 한 지점에서 압력을 평균낼 시간 (초)
# duty 를 1 옮길 때마다 기다릴 안정화 시간 (초).
# duty 차가 클수록 압력이 자리 잡는 데 오래 걸려 차이에 비례해 기다린다.
SETTLE_SECONDS_PER_DUTY = 2


class BackgroundTask(QThread):
    finished = pyqtSignal()  # 작업 완료 시그널
    error = pyqtSignal(str)  # 작업 오류 시그널
    progress = pyqtSignal(str)  # 진행 상황 시그널 (측정 중 창에 표시)
    # (풍량, 압력차, 압력 표준편차, 시험종류) 확정 측정점 → 마커 + 변동폭 가로선
    point = pyqtSignal(float, float, float, str)
    position = pyqtSignal(float, float)  # (풍량, 압력차) 현재 위치 → 십자 포인터

    def __init__(self, task_type):
        super().__init__()
        self.task_type = task_type
        self.result = 0 # Initialize the result attribute
        # duty→풍량 변환에 쓰는 팬 계수 (blower_door_test 에서 설정)
        self.fan_coeff = None
        self.num_fans = 1

    def report(self, message):
        """진행 상황을 터미널과 GUI 양쪽에 알린다."""
        print(message)
        self.progress.emit(message)

    def duty_flow(self, duty):
        """duty 를 풍량(㎥/h)으로 바꾼다. 팬 계수가 없으면 None."""
        if not self.fan_coeff:
            return None
        return calculation.duty_to_flow(duty, self.fan_coeff, self.num_fans,
                                        self.task_type)

    def report_point(self, duty, pressure, sigma=0.0):
        """확정된 측정점을 마커로 찍는다. sigma 는 측정 중 압력 변동폭."""
        flow = self.duty_flow(duty)
        if flow is not None:
            self.point.emit(flow, abs(pressure), sigma, self.task_type)

    def report_position(self, duty, pressure):
        """제어 중 현재 위치를 십자 포인터로만 표시한다 (마커는 찍지 않음)."""
        flow = self.duty_flow(duty)
        if flow is not None:
            self.position.emit(flow, abs(pressure))

    def _read_pressure(self, average_time):
        """압력을 한 번 읽는다. 센서가 끊기면 None."""
        try:
            return hardware.pressure_read(
                average_time=average_time, test=TEST_MODE)
        except hardware.SensorTimeout as exc:
            print(exc)
            return None

    def live_wait(self, duty, seconds):
        """seconds 동안 대기하면서 현재 압력을 십자 포인터로 실시간 갱신한다."""
        deadline = time.time() + seconds
        while time.time() < deadline:
            p = self._read_pressure(0.1)
            if p is not None:
                self.report_position(duty, p)

    def live_measure(self, duty, seconds):
        """seconds 동안 압력을 읽어 평균과 변동폭을 반환한다.

        그 사이 십자 포인터도 실시간 갱신한다.
        반환: (평균, 표준편차, 최소, 최대). 표본이 없으면 전부 0.

        0 기류 보정을 생략하는 운용이라 바람의 영향이 결과에 그대로 들어온다.
        변동폭을 함께 남겨 어느 지점이 흔들린 상태에서 측정됐는지 그래프와
        기록으로 확인할 수 있게 한다.
        """
        samples = []
        deadline = time.time() + seconds
        while time.time() < deadline:
            p = self._read_pressure(0.3)
            if p is not None:
                samples.append(p)
                self.report_position(duty, p)
        if not samples:
            return 0.0, 0.0, 0.0, 0.0
        mean = sum(samples) / len(samples)
        # 표본 1개면 stdev 가 예외를 낸다
        sigma = statistics.stdev(samples) if len(samples) > 1 else 0.0
        return mean, sigma, min(samples), max(samples)

    def run(self):
        try:
            if self.task_type == "depressurization":
                self.blower_door_test(self.task_type)
            elif self.task_type == "pressurization":
                self.blower_door_test(self.task_type)
            elif self.task_type == "calculation":
                self.calculation()
            elif self.task_type == "graph_plotting":
                self.graph_plotting()
            elif self.task_type == "reporting":
                self.reporting()
        except Exception as exc:
            # 측정/계산 중 예외가 나도 GUI가 멈추지 않도록 로그를 남기고 시그널로 알림
            traceback.print_exc()
            # 측정 작업 중 오류면 팬을 반드시 정지시켜 안전 상태로 둔다
            if self.task_type in ("depressurization", "pressurization"):
                try:
                    hardware.duty_set(0, test=TEST_MODE)
                except Exception:
                    traceback.print_exc()
            self.error.emit(str(exc))
        finally:
            # 성공/실패와 무관하게 항상 완료 시그널을 보내 대기 창이 닫히도록 한다
            self.finished.emit()  # 작업 완료 시그널 발생

    @staticmethod
    def measuring_pressure(total_duration, local_duration):
        # 압력 측정
        pressure = []
        # 측정 시간
        pressure_size = total_duration
        while pressure_size:
            measuring_duration = local_duration
            pressure.append(hardware.
                            pressure_read(average_time=
                                          measuring_duration,
                                          test=TEST_MODE))
            pressure_size -= measuring_duration
        # 측정 평균값 저장
        return sum(pressure)/len(pressure)

    def blower_door_test(self, test):

        # 측정 모드에 따른 변수 설정
        # 9GV2048P0G201 fan only (formerly OF-OD172SAP-Reversible)
        zero_duty = 0

        with open(paths.CONDITIONS_JSON, 'r') as f:
            conditions = json.load(f)
        cover = conditions.get("fan_cover", "none").lower()
        fan_coeffs = calculation.load_fan_coefficients()
        coeff = fan_coeffs.get(cover, fan_coeffs.get("none", {}))
        # 실시간 그래프에서 duty 를 풍량으로 바꾸는 데 사용한다
        self.fan_coeff = coeff
        self.num_fans = int(conditions.get("fan_count", 1))

        duty_range = coeff.get("duty_range", [20, 100])
        min_duty, max_duty = duty_range
        initial_duty = min_duty - 1

        # 측정
        measuring = {}
        measuring["measured_value"] = []
        # 지점별 압력 변동폭. measured_value 의 [압력, duty] 형식은 계산부가
        # 그대로 언팩하므로 건드리지 않고, 부가 정보는 여기에 따로 남긴다.
        measuring["pressure_spread"] = []
        # 온습도, 대기압
        measuring["temperature"] = 20
        measuring["relative_humidity"] = 50
        measuring["atmospheric_pressure"] = 101325
        # 테스트 기록
        measuring["test"] = test
        # 시험 시작 시간
        time_start = datetime.now().strftime("%H:%M:%S")

        # 시작 0 기류 압력 측정 # 현재 버전에서는 생략
        # measuring["initial_zero_pressure"] = self.measuring_pressure(10, 1)

        # 시험 시작
        self.report(f"팬 속도를 조절해 목표 압력({TARGET_PRESSURE} Pa)을 맞추는 중…")
        # 목표 압력에 해당하는 PWM duty 값 추출
        (duty, success, pressure) = control.get_duty(target=TARGET_PRESSURE,
                                                     delay=5,
                                                     average_time=0.5,
                                                     control_limit=10,
                                                     duty_min=min_duty,
                                                     duty_max=max_duty,
                                                     test=TEST_MODE,
                                                     progress=self.report,
                                                     on_point=self.report_position)
        # get_duty 가 팬에 마지막으로 건 duty. 첫 측정 지점의 안정화 시간을
        # 계산할 기준이며, 실패 시 duty 를 max 로 덮어써도 팬의 실제 상태는
        # 이 값이므로 따로 들고 있어야 한다.
        fan_duty = duty

        if success:
            self.report(f"목표 압력 도달 — 팬 세기 {duty}%, 압력 {pressure:.1f} Pa")
        else:
            # 목표 압력 도달 실패 = 누기량/침기량 대비 압력형성을 위한 풍량 부족.
            # 최대 duty 부터 min duty 전까지 훑는다.
            self.report(f"{TARGET_PRESSURE} Pa 도달 실패 — "
                        f"최대 팬 세기({max_duty}%)로 측정을 진행합니다")
            duty = max_duty

        # 측정 범위 설정 — duty 지점에서 min_duty 직전까지 10등분
        num_to_measure = 10
        step = (duty - initial_duty) / (num_to_measure - 1)  # 간격 계산
        duty_range = [round(duty - i * step) for i in range(num_to_measure)]

        # 데이터 측정.
        # get_duty 가 이미 잰 값을 여기에 미리 넣지 않는다. 넣으면 첫 지점의
        # duty 를 아래 루프가 한 번 더 재서 같은 duty 가 두 번 들어가고(N=11),
        # get_duty 는 내부에서 abs() 를 쓰므로 그 점만 부호가 뒤집힌 채
        # 저장됐다. 또 도달 실패 시엔 다른 duty 에서 잰 압력이 max_duty 와
        # 짝지어져 들어갔다. 모든 점을 이 루프에서 같은 방식으로 잰다.
        before = fan_duty
        total = len(duty_range)
        for i, d in enumerate(duty_range, start=1):
            hardware.duty_set(d, test=TEST_MODE)
            # duty 를 많이 움직일수록 압력이 자리 잡는 데 오래 걸린다
            settle = abs(before - d) * SETTLE_SECONDS_PER_DUTY
            self.report(f"[{i}/{total}] 팬 세기 {d}% — 압력 안정화 대기 중… ({settle}초)")
            # 대기·측정 내내 실시간으로 십자 포인터를 갱신한다
            self.live_wait(d, settle)
            self.report(f"[{i}/{total}] 팬 세기 {d}% — 압력 측정 중… ({MEASURE_SECONDS}초)")
            p, sigma, p_min, p_max = self.live_measure(d, MEASURE_SECONDS)
            self.report(f"[{i}/{total}] 팬 세기 {d}% — 측정 완료: "
                        f"{p:.1f} Pa (변동 ±{sigma:.1f})")
            measuring["measured_value"].append([p, d])
            measuring["pressure_spread"].append(
                {"duty": d, "std": sigma, "min": p_min, "max": p_max})
            self.report_point(d, p, sigma)
            before = d

        # 종료 0 기류 압력 측정 # 현재 버전에서는 생략
        # measuring["final_zero_pressure"] = self.measuring_pressure(10, 1)
        # 시험 종료 — 팬 정지 후 실제로 멈췄는지 확인한다
        self.report("측정 완료 — 팬을 정지하는 중…")
        if hardware.duty_set(zero_duty, test=TEST_MODE) != 0:
            self.report("⚠ 팬 정지 실패 — PWM 핀 손상이 의심됩니다. 전원을 수동으로 차단하세요.")
        # 시험 종료 시간 기록
        time_end = datetime.now().strftime("%H:%M:%S")
        measuring["test time"] = [time_start, time_end]

        # Raw data 백업 저장
        now = datetime.now().strftime("%y%m%d-%H%M%S")
        backup_path = os.path.join(paths.ensure_dir(paths.MEASUREMENTS_DIR),
                                   f"{test}_{now}.json")
        with open(backup_path, 'w') as file:
            json.dump(measuring, file, indent=4)
        # 데이터 저장
        with open(paths.raw_json(test), 'w') as file:
            json.dump(measuring, file, indent=4)

    def calculation(self):
        # 시험 조건 불러오기
        with open(paths.CONDITIONS_JSON, 'r') as file:
            data = json.load(file)

        # 아무 시험 결과 없는 경우, Just in case.
        if not data.get("depressurization") and not data.get("pressurization"):
            pass

        # 결과 저장 변수 선언
        calculation_raw = {}
        # 보고서 용 값 저장
        calculation_raw["report"] = {}

        # 저장 할 값 지정
        need_to_save = ["C0",
                        "n",
                        "C0 range",
                        "n range",
                        "t",
                        "variance of n",
                        "variance of x",
                        "mean x",
                        "N",
                        "measured values",
                        "margin of error of y",
                        "Q50",
                        "ACH50",
                        "AL50",
                        "r^2",
                        "Q50+-",
                        "ACH50+-",
                        "n+-",
                        "C0+-",
                        "interior_volume"]

        need_to_report = ["Q50",
                          "ACH50",
                          "AL50",
                          "C0",
                          "n",
                          "Q50+-",
                          "C0+-",
                          "n+-",
                          "r^2",
                          "interior_volume"]

        # 감압 시험을 수행 한 경우
        if data.get("depressurization"):
            # 파일 불러오기
            depressureization = calculation.BlowerDoorTestCalculator.from_file(
                paths.DEPRESSURIZATION_RAW_JSON, paths.CONDITIONS_JSON)
            # 결과 계산
            results_depr = depressureization.calculate_results()
            # Raw data 저장
            now = datetime.now().strftime("%y%m%d-%H%M%S")
            depr_path = os.path.join(paths.ensure_dir(paths.CALCULATIONS_DIR),
                                     f"depressurization_{now}.json")
            with open(depr_path, 'w') as file:
                json.dump(results_depr, file, indent=4)
            # 결과 값 변수 저장
            calculation_raw['depressurization'] = {}
            for i in results_depr.keys():
                if i in need_to_save:
                    calculation_raw['depressurization'][i]=results_depr[i]

            for i in need_to_report:
                report_key = i + "-"
                calculation_raw["report"][report_key] = calculation_raw["depressurization"][i]

        # 가압 시험을 수행 한 경우
        if data.get("pressurization"):
            # 파일 불러오기
            pressureization = calculation.BlowerDoorTestCalculator.from_file(
                paths.PRESSURIZATION_RAW_JSON, paths.CONDITIONS_JSON)
            # 결과 계산
            results_pres = pressureization.calculate_results()
            # Raw data 저장
            now = datetime.now().strftime("%y%m%d-%H%M%S")
            pres_path = os.path.join(paths.ensure_dir(paths.CALCULATIONS_DIR),
                                     f"pressurization_{now}.json")
            with open(pres_path, 'w') as file:
                json.dump(results_pres, file, indent=4)
            # 결과 값 변수 저장
            calculation_raw['pressurization'] = {}
            for i in results_pres.keys():
                if i in need_to_save:
                    calculation_raw['pressurization'][i]=results_pres[i]

            for i in need_to_report:
                report_key = i + "+"
                calculation_raw["report"][report_key] = calculation_raw["pressurization"][i]

        # 감/가압 시험 모두 수행 한 경우, 평균 값 계산
        if data.get("depressurization") and data.get("pressurization"):
            calculation_raw["average"] = {}
            for i in ["Q50", "ACH50", "AL50"]:
                calculation_raw["report"][i + "_avg"] = (calculation_raw["depressurization"][i] \
                                                        + calculation_raw["pressurization"][i])/2

        with open(paths.CALCULATION_RAW_JSON, 'w') as file:
            json.dump(calculation_raw, file, indent=4)

        self.report("시험 결과 계산 완료")

    def graph_plotting(self):
        # 시험 조건 불러오기
        with open(paths.CONDITIONS_JSON, 'r') as file:
            conditions = json.load(file)

        # 계산 결과 불러오기
        with open(paths.CALCULATION_RAW_JSON, 'r') as file:
            calculation_raw = json.load(file)

        self.report("압력-유량 그래프를 그리는 중…")

        if conditions.get("depressurization") and conditions.get("pressurization"):
            graph.plot_graph(calculation_raw['depressurization'],
                             calculation_raw['pressurization'],
                             calculation_raw['report'])
        elif conditions.get("depressurization"):
            graph.plot_graph(calculation_raw['depressurization'],
                             False,
                             calculation_raw['report'])
        elif conditions.get("pressurization"):
            graph.plot_graph(False,
                             calculation_raw['pressurization'],
                             calculation_raw['report'])

    def reporting(self):
        with open(paths.CONDITIONS_JSON, 'r') as f:
            conditions = json.load(f)
        with open(paths.CALCULATION_RAW_JSON, 'r') as f:
            report_data = json.load(f).get("report", {})

        self.report("성적서를 만드는 중…")
        pdf_path = paths.REPORT_PDF
        result = html.make_report_pdf(
            conditions, report_data, pdf_path,
            graph_path=paths.GRAPH_PNG, font_path=paths.FONT_PATH)

        if not result:
            self.report("성적서 PDF 생성 실패 (chromium 확인 필요)")
            return
        self.report("성적서 생성 완료: report.pdf")
        if platform.system() == "Linux":
            self.open_pdf(pdf_path)

    def open_pdf(self, pdf_path):
        """생성된 PDF를 뷰어로 연다. 뷰어가 없어도 조용히 넘어간다."""
        import subprocess as sub
        viewer = (shutil.which("evince") or shutil.which("xpdf")
                  or shutil.which("qpdfview") or shutil.which("xdg-open"))
        if not viewer:
            self.report("PDF 뷰어가 없어 파일만 저장했습니다: report.pdf")
            return
        self.report("성적서를 화면에 표시합니다: report.pdf")
        # start_new_session=True 로 새 세션에 분리해야 시험 종료 후 프로그램이
        # 닫힐 때(터미널 SIGHUP) 뷰어까지 같이 꺼지지 않는다.
        sub.Popen([viewer, pdf_path],
                  stdout=sub.DEVNULL, stderr=sub.DEVNULL,
                  start_new_session=True)
