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
from bdt import settings
from bdt.config import TEST_MODE


# 시험 조건은 bdt.settings 가 갖는다 (설정 화면에서 고칠 수 있다).
# 값을 모듈 수준에 캐시하지 않고 시험을 시작할 때마다 읽어, 방금 바꾼 설정이
# 다음 시험에 바로 먹게 한다.


class TestImpossible(Exception):
    """이 조건에서는 시험을 수행할 수 없다 (압력을 제어할 수 없음)."""


class TestCancelled(Exception):
    """사용자가 시험을 중단했다. 오류가 아니므로 따로 다룬다."""


class BackgroundTask(QThread):
    finished = pyqtSignal()   # 작업 완료 시그널 (성공·실패·중단 무관하게 항상)
    error = pyqtSignal(str)   # 작업 오류 시그널
    cancelled = pyqtSignal()  # 사용자가 중단시킴
    progress = pyqtSignal(str)  # 진행 상황 시그널 (측정 중 창에 표시)
    # (풍량, 압력차, 압력 표준편차, 시험종류) 확정 측정점 → 마커 + 변동폭 가로선
    point = pyqtSignal(float, float, float, str)
    position = pyqtSignal(float, float)  # (풍량, 압력차) 현재 위치 → 십자 포인터
    # (팬 세기 %, 압력차) — 목표 압력 조절 페이지용. position 과 달리 duty 를
    # 풍량으로 바꾸지 않은 원시값이라 팬 계수가 없어도 나간다.
    raw_position = pyqtSignal(float, float)
    # 목표 압력 조절(get_duty)이 끝나고 지점 측정으로 넘어간다 → 페이지 전환
    targeted = pyqtSignal()
    # (종류, 경과초, 목표초) — 수렴/실패 유지 카운트. 종류는 "converge"/"fail".
    # 조절 화면이 유지 구간을 색칠하고 카운트를 보여주는 데 쓴다.
    hold = pyqtSignal(str, float, float)
    # 이 조건에서는 시험 자체가 불가능하다 (장비 고장이 아니라 현장 조건 문제).
    # error 와 섞으면 "장비에 문제가 있나" 로 읽히므로 따로 알린다.
    impossible = pyqtSignal(str)

    def __init__(self, task_type):
        super().__init__()
        self.task_type = task_type
        # duty→풍량 변환에 쓰는 팬 계수 (blower_door_test 에서 설정)
        self.fan_coeff = None
        self.num_fans = 1
        # 중단 요청 플래그. QThread 를 밖에서 강제로 죽이면 팬이 도는 채로
        # 남을 수 있어, 측정 루프가 스스로 확인하고 빠져나오게 한다.
        self._cancelled = False
        # 센서 이상을 이미 알렸는지 (같은 경고를 반복해서 쏟지 않기 위해)
        self._sensor_warned = False

    def cancel(self):
        """시험 중단을 요청한다 (측정 루프가 확인하고 빠져나온다)."""
        self._cancelled = True

    def _check_cancelled(self):
        """중단 요청이 있었으면 예외를 던져 측정 루프를 빠져나온다."""
        if self._cancelled:
            raise TestCancelled()

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

    def report_hold(self, kind, elapsed, total):
        """get_duty 의 수렴·실패 유지 카운트를 화면에 전달한다."""
        self.hold.emit(kind, float(elapsed), float(total))

    def report_point(self, duty, pressure, sigma=0.0):
        """확정된 측정점을 마커로 찍는다. sigma 는 측정 중 압력 변동폭."""
        flow = self.duty_flow(duty)
        if flow is not None:
            self.point.emit(flow, abs(pressure), sigma, self.task_type)

    def report_position(self, duty, pressure):
        """제어 중 현재 위치를 십자 포인터로만 표시한다 (마커는 찍지 않음)."""
        self.raw_position.emit(float(duty), abs(pressure))
        flow = self.duty_flow(duty)
        if flow is not None:
            self.position.emit(flow, abs(pressure))

    def _read_pressure(self, average_time):
        """압력을 한 번 읽는다. 센서가 끊기면 None.

        실패를 매번 출력하면 센서가 죽었을 때 초당 수십 줄이 터미널을 뒤덮는다
        (.desktop 이 Terminal=true 라 사용자에게 그대로 보인다). 같은 문제는
        한 번만 알리고, 다시 읽히면 회복됐음을 알린다.
        """
        try:
            value = hardware.pressure_read(
                average_time=average_time, test=TEST_MODE)
        except hardware.SensorTimeout as exc:
            if not self._sensor_warned:
                self._sensor_warned = True
                self.report(f"⚠ 압력 센서 응답 없음 — {exc}")
            return None
        if self._sensor_warned:
            self._sensor_warned = False
            self.report("압력 센서 응답이 돌아왔습니다.")
        return value

    def live_wait(self, duty, seconds):
        """seconds 동안 대기하면서 현재 압력을 십자 포인터로 실시간 갱신한다."""
        deadline = time.time() + seconds
        while time.time() < deadline:
            self._check_cancelled()
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
            self._check_cancelled()
            p = self._read_pressure(0.3)
            if p is not None:
                samples.append(p)
                self.report_position(duty, p)
        if not samples:
            # 예전엔 0.0 을 돌려줬다. 센서가 죽어도 시험이 조용히 계속되며
            # 모든 지점이 0 Pa 로 기록됐고, 그 뒤 계산이 log(0) 로 터졌다.
            # 침묵으로 오염된 데이터를 남기느니 여기서 멈춘다.
            raise hardware.SensorTimeout(
                f"{seconds}초 동안 압력을 한 번도 읽지 못했습니다. "
                "센서 연결과 전원을 확인하세요.")
        mean = sum(samples) / len(samples)
        # 표본 1개면 stdev 가 예외를 낸다
        sigma = statistics.stdev(samples) if len(samples) > 1 else 0.0
        return mean, sigma, min(samples), max(samples)

    # 회귀선을 그으려면 서로 다른 압력의 지점이 최소 이만큼은 있어야 한다.
    # (계산부는 자유도 N-2 로 신뢰구간을 낸다 — 2점이면 오차가 정의되지 않는다)
    MIN_SWEEP_POINTS = 3

    @staticmethod
    def _sweep_points(start, end, count):
        """start(가장 높은 압력)에서 end 까지 count 등분한 팬 세기 목록.

        round() 때문에 구간이 좁으면 같은 duty 가 여러 번 나온다. 중복을 남기면
        같은 지점을 두 번 재고(측정 시간 낭비), 계산부는 N 을 그대로 믿어
        신뢰구간이 실제보다 좁게 나온다 — 없는 정보가 있는 척한다. 중복은
        지우고 실제로 서로 다른 지점만 남긴다.

        start 가 end 이하면(스윕할 구간이 없음) 빈 목록을 돌려준다. 호출부가
        MIN_SWEEP_POINTS 로 판정한다.
        """
        if start <= end or count < 2:
            return []
        step = (start - end) / (count - 1)
        points = [round(start - i * step) for i in range(count)]
        unique = []
        for p in points:
            if p not in unique:
                unique.append(p)
        return unique

    def _find_upper_duty(self, min_duty, max_duty, max_pressure,
                         settle_per_duty):
        """상한 압력을 넘지 않는 가장 높은 팬 세기를 찾는다.

        팬을 최소로 낮춰도 목표를 넘는 공간에서만 쓴다. 이때 스윕은 최소에서
        위로 갈 수밖에 없는데, 상한(기본 100 Pa)을 넘는 지점까지 재면 시험
        압력 구간을 벗어난 점이 회귀에 섞인다. 그래서 최소부터 한 단계씩
        올려보며 상한을 넘기 직전 세기를 스윕의 시작점으로 삼는다.

        압력이 duty 에 대해 단조 증가한다는 가정이라 처음 넘는 지점에서 멈춘다
        (바람으로 한 번 튀어도 그 아래는 안전한 구간이므로 손해는 없다).

        반환: (스윕 시작 세기, 팬에 마지막으로 건 세기).
        """
        step = max(1, round((max_duty - min_duty) / 10))
        upper = before = min_duty
        d = min_duty + step
        while d <= max_duty:
            hardware.duty_set(d, test=TEST_MODE)
            self.live_wait(d, abs(d - before) * settle_per_duty)
            pressure = abs(self.live_measure(d, 2.0)[0])
            before = d
            self.report(f"팬 세기 {d}% — {pressure:.1f} Pa "
                        f"(상한 {max_pressure:.0f} Pa)")
            if pressure > max_pressure:
                break
            upper = d
            d += step
        return upper, before

    def run(self):
        try:
            if self.task_type == "depressurization":
                self.blower_door_test(self.task_type)
            elif self.task_type == "pressurization":
                self.blower_door_test(self.task_type)
            elif self.task_type == "calculation":
                self._calculate_or_explain()
            elif self.task_type == "graph_plotting":
                self.graph_plotting()
            elif self.task_type == "reporting":
                self.reporting()
            else:
                # 오타·미등록 유형이 '조용한 성공'이 되면 흐름이 낡은 산출물로
                # 다음 단계를 진행한다. 반드시 오류로 드러낸다.
                raise RuntimeError(f"알 수 없는 작업 유형: {self.task_type!r}")
        except TestImpossible as exc:
            # 장비 결함이 아니라 현장 조건이 시험을 허락하지 않는 경우다.
            # 팬만 세우고, 원인과 대처를 그대로 화면에 넘긴다.
            self._stop_fan()
            self.report("시험 불가 — 압력을 제어할 수 없습니다.")
            self.impossible.emit(str(exc))
        except TestCancelled:
            # 사용자가 멈춘 것이니 오류가 아니다. 팬만 확실히 세운다.
            self._stop_fan()
            self.report("시험을 중단했습니다 — 팬을 정지시켰습니다.")
            self.cancelled.emit()
        except Exception as exc:
            # 측정/계산 중 예외가 나도 GUI가 멈추지 않도록 로그를 남기고 시그널로 알림
            traceback.print_exc()
            self._stop_fan()
            self.error.emit(str(exc))
        finally:
            # 성공/실패/중단과 무관하게 항상 완료 시그널을 보낸다.
            # 이 시그널만으로 다음 단계를 진행해서는 안 된다 — 실패했는지는
            # error/cancelled 시그널로 판단한다 (flow.TestFlow 참고).
            self.finished.emit()

    def _calculate_or_explain(self):
        """계산을 수행하되, 실패하면 현장에서 알아들을 수 있는 말로 바꿔 알린다.

        회귀는 log(압력) 을 쓰므로 압력이 0 이면 'math domain error', 실내 체적이
        0 이면 'float division by zero' 가 그대로 화면에 떴다. 원인을 짐작할 수
        없는 문구라 무엇을 고쳐야 할지 알 수 없다.
        """
        try:
            self.calculation()
        except (ValueError, ZeroDivisionError) as exc:
            raise RuntimeError(
                "측정값으로 결과를 계산할 수 없습니다.\n"
                "압력이 제대로 측정되지 않았거나 시험 조건(실내 체적 등)이 "
                f"올바르지 않을 수 있습니다.\n\n(원인: {exc})") from exc

    def _stop_fan(self):
        """측정 작업이 중간에 끝났으면 팬을 반드시 세워 안전 상태로 둔다."""
        if self.task_type not in ("depressurization", "pressurization"):
            return
        try:
            if hardware.duty_set(0, test=TEST_MODE) != 0:
                self.report("⚠ 팬 정지 실패 — PWM 핀 손상이 의심됩니다. "
                            "전원을 수동으로 차단하세요.")
        except Exception:
            traceback.print_exc()

    def blower_door_test(self, test):

        # 측정 모드에 따른 변수 설정
        # 9GV2048P0G201 fan only (formerly OF-OD172SAP-Reversible)
        zero_duty = 0
        cfg = settings.load()
        target = cfg["target_pressure"]
        measure_seconds = cfg["measure_seconds"]
        settle_per_duty = cfg["settle_seconds_per_duty"]
        num_to_measure = int(cfg["num_points"])
        low_warn = cfg["low_pressure_warn"]
        max_pressure = cfg["max_pressure"]

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
        # 스윕의 마지막(최저) 측정 지점.
        #
        # min_duty 자체가 아니라 +1 인 이유: duty_range 의 하한은 팬이 도는
        # 경계라 개체차에 따라 그 값에서 꺼질 수 있다. 측정점은 팬이 확실히
        # 도는 자리여야 하므로 한 단계 위에서 멈춘다.
        #
        # 예전엔 min_duty - 1 이었다. initial_duty 라는 이름은 '경계'인데
        # 실제로는 측정점으로 쓰이는 값이라 두 역할이 뒤섞였고, 그 결과
        # 팬이 꺼질 수 있는 하한 아래에서 측정하고 풍량도 팬 보정 범위
        # ([min,max]) 밖으로 외삽했다.
        lowest_duty = min_duty + 1

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

        # 0 기류(baseline) 압력 측정은 의도적으로 생략한다.
        # ISO 9972 는 시험 전후로 팬을 끈 상태의 압력차를 재서 측정값에서 빼도록
        # 하지만(바람·연돌효과 보정), 빠른 측정과 편의를 위해 넣지 않기로 했다.
        # 이 앱은 ISO 준용이지 엄밀한 준수를 목표로 하지 않는다. 대신 지점별
        # 압력 변동폭(pressure_spread)을 남겨 바람의 영향을 눈으로 볼 수 있게 한다.

        # 시험 시작
        self.report(f"팬 속도를 조절해 목표 압력({target:.0f} Pa)을 맞추는 중…")
        # 목표 압력에 해당하는 PWM duty 값 추출
        (duty, success, pressure, saturated) = control.get_duty(
            target=target,
            delay=5,
            average_time=0.5,
            control_limit=10,
            duty_min=min_duty,
            duty_max=max_duty,
            test=TEST_MODE,
            progress=self.report,
            on_point=self.report_position,
            check_cancelled=self._check_cancelled,
            tolerance_percent=cfg["tolerance_percent"],
            hold_seconds=cfg["hold_seconds"],
            on_hold=self.report_hold)
        # get_duty 가 팬에 마지막으로 건 duty. 첫 측정 지점의 안정화 시간을
        # 계산할 기준이며, 실패 시 duty 를 max 로 덮어써도 팬의 실제 상태는
        # 이 값이므로 따로 들고 있어야 한다.
        fan_duty = duty

        if success:
            self.report(f"목표 압력 도달 — 팬 세기 {duty}%, 압력 {pressure:.1f} Pa")
        elif saturated == "min":
            # 팬을 최소로 낮춰도 목표를 넘는다 = 아주 기밀한 공간이거나 외풍.
            # 예전엔 이 경우에도 최대 duty 로 올려 스윕했는데, 압력이 이미
            # 높은데 팬을 더 돌리는 정반대 처리였다.
            if pressure > max_pressure:
                # 최소에서도 상한을 넘으면 압력을 제어할 방법이 없다.
                raise TestImpossible(
                    f"팬을 최소({min_duty}%)로 낮춰도 압력이 "
                    f"{pressure:.1f} Pa 로 시험 가능 상한({max_pressure:.0f} Pa)을 "
                    "넘습니다.\n\n외풍이 심하거나 공간이 지나치게 기밀해 압력을 "
                    "제어할 수 없습니다. 기상 조건을 확인하고 다시 시도하세요.")
            self.report(f"팬 최소({min_duty}%)에서도 목표 {target:.0f} Pa 를 넘습니다 "
                        f"(현재 {pressure:.1f} Pa) — 측정 가능한 팬 세기 구간을 "
                        "찾는 중…")
            # 최소가 이 공간에서 낼 수 있는 가장 낮은 압력이다. 스윕은 최소에서
            # 위로 갈 수밖에 없는데, 그렇다고 최대까지 올리면 압력이 시험 가능
            # 상한을 한참 넘는다 — 상한을 넘지 않는 가장 높은 팬 세기를 찾아
            # 거기서부터 최소까지를 훑는다.
            duty, fan_duty = self._find_upper_duty(
                min_duty, max_duty, max_pressure, settle_per_duty)
            if duty <= lowest_duty:
                raise TestImpossible(
                    f"팬 최소({min_duty}%)에서 {pressure:.1f} Pa 인데, 한 단계만 "
                    f"올려도 시험 가능 상한({max_pressure:.0f} Pa)을 넘습니다.\n\n"
                    "측정할 수 있는 팬 세기 구간이 없습니다. 외풍이 심하거나 "
                    "공간이 지나치게 기밀한 상태입니다.")
            self.report(f"팬 세기 {lowest_duty}~{duty}% 구간에서 측정을 진행합니다")
        else:
            # 목표 압력 도달 실패 = 누기량/침기량 대비 압력형성을 위한 풍량 부족.
            # 최대 duty 부터 min duty 전까지 훑는다.
            self.report(f"{target:.0f} Pa 도달 실패 — "
                        f"최대 팬 세기({max_duty}%)로 측정을 진행합니다")
            duty = max_duty

        # 목표 압력 조절이 끝났다 — 화면을 측정 차트로 넘긴다
        self.targeted.emit()

        # 측정 범위 설정 — 시작 지점(가장 높은 압력)에서 최저 지점까지 등분해
        # 내려간다. 팬 최소에서도 목표를 넘은 경우엔 시작 지점이 목표 압력이
        # 아니라 위에서 찾은 '상한을 넘지 않는 최고 세기'일 뿐, 훑는 방향은 같다.
        duty_range = self._sweep_points(duty, lowest_duty, num_to_measure)
        if len(duty_range) < self.MIN_SWEEP_POINTS:
            # 시작 지점이 최저 지점에 붙어 있다 = 훑을 구간이 없다.
            # 아주 기밀한 공간에서 팬 최소만으로 이미 목표 압력에 닿으면
            # 성공 경로로도 여기에 온다. 그대로 두면 같은 duty 를 열 번 재고,
            # 압력이 거의 변하지 않는 점들로 회귀해 노이즈를 기울기로 읽는다.
            raise TestImpossible(
                f"측정할 수 있는 팬 세기 구간이 너무 좁습니다 "
                f"(시작 {duty}% · 최저 {lowest_duty}%).\n\n"
                "팬을 거의 최소로 돌려도 목표 압력에 닿을 만큼 기밀한 공간입니다. "
                "압력을 여러 단계로 나눠 측정할 수 없어 기류 지수를 구할 수 "
                "없습니다.")

        # 데이터 측정.
        # get_duty 가 이미 잰 값을 여기에 미리 넣지 않는다. 넣으면 첫 지점의
        # duty 를 아래 루프가 한 번 더 재서 같은 duty 가 두 번 들어가고(N=11),
        # get_duty 는 내부에서 abs() 를 쓰므로 그 점만 부호가 뒤집힌 채
        # 저장됐다. 또 도달 실패 시엔 다른 duty 에서 잰 압력이 max_duty 와
        # 짝지어져 들어갔다. 모든 점을 이 루프에서 같은 방식으로 잰다.
        before = fan_duty
        total = len(duty_range)
        try:
            for i, d in enumerate(duty_range, start=1):
                hardware.duty_set(d, test=TEST_MODE)
                # duty 를 많이 움직일수록 압력이 자리 잡는 데 오래 걸린다
                settle = abs(before - d) * settle_per_duty
                self.report(f"[{i}/{total}] 팬 세기 {d}% — 압력 안정화 대기 중… ({settle}초)")
                # 대기·측정 내내 실시간으로 십자 포인터를 갱신한다
                self.live_wait(d, settle)
                self.report(f"[{i}/{total}] 팬 세기 {d}% — 압력 측정 중… ({measure_seconds:.0f}초)")
                p, sigma, p_min, p_max = self.live_measure(d, measure_seconds)
                self.report(f"[{i}/{total}] 팬 세기 {d}% — 측정 완료: "
                            f"{p:.1f} Pa (변동 ±{sigma:.1f})")
                if abs(p) < low_warn:
                    self.report(f"⚠ 측정 압력이 {low_warn:.0f} Pa 미만입니다 "
                                "— 바람 영향이 커 이 지점의 신뢰도가 낮습니다")
                measuring["measured_value"].append([p, d])
                measuring["pressure_spread"].append(
                    {"duty": d, "std": sigma, "min": p_min, "max": p_max})
                self.report_point(d, p, sigma)
                before = d
        except (hardware.SensorTimeout, TestCancelled):
            # 도중 실패·중단이어도 이미 확정한 지점들은 파일로 남긴다.
            # 본 raw 저장은 루프 완주 뒤에만 수행되므로, 여기서 남기지 않으면
            # 4~5분치 확정 측정값이 통째로 증발해 처음부터 재시험해야 한다.
            if measuring["measured_value"]:
                now = datetime.now().strftime("%y%m%d-%H%M%S")
                partial = os.path.join(
                    paths.ensure_dir(paths.MEASUREMENTS_DIR),
                    f"{test}_{now}_incomplete.json")
                with open(partial, 'w') as file:
                    json.dump(measuring, file, indent=4)
                self.report(
                    f"중단 전까지의 측정값 {len(measuring['measured_value'])}개를 "
                    f"보관했습니다: measurements/{os.path.basename(partial)}")
            raise

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
        # 지난 시험의 결과 파일을 먼저 지운다.
        # 남겨두면 이번 계산이 실패했을 때 그래프·성적서가 그 낡은 값을 그대로
        # 읽어, 새 건물 이름에 이전 건물의 측정값이 실린 성적서가 발행된다.
        # 실패하면 뒤 단계가 파일을 못 찾고 함께 멈추는 편이 안전하다.
        if os.path.exists(paths.CALCULATION_RAW_JSON):
            os.remove(paths.CALCULATION_RAW_JSON)

        # 시험 조건 불러오기
        with open(paths.CONDITIONS_JSON, 'r') as file:
            data = json.load(file)

        # 수행된 시험이 하나도 없으면 빈 결과 파일이 만들어져 뒤 단계가
        # 이해할 수 없는 오류로 죽는다. 여기서 명확히 멈춘다.
        if not data.get("depressurization") and not data.get("pressurization"):
            raise RuntimeError("수행된 시험이 없어 계산할 수 없습니다.")

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

        self.report("누기 그래프를 그리는 중…")

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
            # return 으로 끝내면 finished 만 나가 완료 화면이 '성적서가 표시
            # 됩니다'로 안내한다 — 파일은 없거나 이전 시험 것인데. 오류로 알린다.
            raise RuntimeError(
                "성적서 PDF 를 만들지 못했습니다. chromium 이 설치돼 있는지 "
                "확인하세요.")
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
