"""단일 창(MainWindow)과 시험 절차 진행(TestFlow)."""

import json
from datetime import datetime

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QMainWindow, QStackedWidget
from PyQt6.QtCore import QObject

from bdt import paths
from bdt.widgets import StepHeader
from bdt.pages import (
    InputInitialValues,
    LivePressureData,
    ProgressPage,
    ErrorPage,
    LiveMeasurementChart,
    CalculationSummary,
)
from bdt.tasks import BackgroundTask


class MainWindow(QMainWindow):
    """시험 전 과정을 담는 단일 창.

    단계마다 창을 새로 띄우지 않고 이 창 안에서 페이지만 바꾼다.
    덕분에 창 크기·위치가 시험 내내 유지된다.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("기밀성능 시험")

        self.header = StepHeader()
        self.stack = QStackedWidget()

        center = QWidget()
        outer = QVBoxLayout(center)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.header)
        outer.addWidget(self.stack, 1)
        self.setCentralWidget(center)

    def show_page(self, page, step=None):
        """페이지를 현재 화면으로 바꾸고, 이전 페이지는 정리한다."""
        previous = self.stack.currentWidget()
        self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)
        if step is not None:
            self.header.set_current(step)
        if previous is not None:
            self.stack.removeWidget(previous)
            previous.deleteLater()


class TestFlow(QObject):
    """시험 절차를 순서대로 진행한다.

    전에는 단계마다 창을 띄우고 app.exec() 를 다시 돌리는 식이라 창이 계속
    새로 떴다. 이제 창 하나를 두고 시그널을 따라 페이지만 바꾼다.
    """

    TESTS = {"depressurization": "감압", "pressurization": "가압"}

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.task = None      # 실행 중인 백그라운드 작업 (GC 방지용 참조)
        self.summary = None   # 계산 결과 화면 (그래프·성적서 동안 유지된다)
        self.data = {}
        self.steps = []
        self.pending = []
        # 작업이 실패·중단됐음을 표시. finished 시그널은 성공 여부와 무관하게
        # 항상 오므로, 이 표시를 보고 다음 단계로 넘어갈지 판단한다.
        self.stopped = False

    # ── 단계 진행 ────────────────────────────────────────────
    def start(self):
        self.stopped = False
        self.pending = []
        self.summary = None
        self.window.header.set_steps(["조건 입력"])
        page = InputInitialValues()
        page.saved.connect(self.on_conditions_saved)
        self.window.show_page(page, step=0)

    # ── 실패·중단 처리 ───────────────────────────────────────
    def on_error(self, message):
        """작업이 실패했다 — 흐름을 멈추고 화면에 알린다.

        예전엔 error 시그널이 아무데도 연결돼 있지 않아, 실패해도 흐름이
        그대로 다음 단계로 넘어갔다.
        """
        self.stopped = True
        page = ErrorPage("시험을 계속할 수 없습니다", message)
        page.restart.connect(self.start)
        self.window.show_page(page)

    def on_cancelled(self):
        """사용자가 시험을 중단했다 — 조건 입력부터 다시 시작한다."""
        self.stopped = True
        self.start()

    def _guard(self, on_done):
        """실패·중단했으면 다음 단계로 넘어가지 않게 감싼다."""
        def proceed():
            if self.stopped:
                return
            on_done()
        return proceed

    def _connect(self, task, on_done):
        """작업의 완료·실패·중단 시그널을 한 자리에서 연결한다."""
        task.error.connect(self.on_error)
        task.cancelled.connect(self.on_cancelled)
        task.finished.connect(self._guard(on_done))
        self.task = task

    def on_conditions_saved(self):
        self.stopped = False
        with open(paths.CONDITIONS_JSON, 'r') as file:
            self.data = json.load(file)

        self.time_start = datetime.now().strftime("%y/%m/%d %H:%M:%S")
        # 새 시험이므로 이전 시험의 그래프 점을 비운다
        LiveMeasurementChart.reset()
        self.fan_count = int(self.data.get("fan_count", 1))

        # 실제 수행할 시험만 단계로 표시한다
        self.pending = [t for t in self.TESTS if self.data.get(t)]
        self.steps = ["조건 입력"] + [self.TESTS[t] for t in self.pending] + ["계산", "성적서"]
        self.window.header.set_steps(self.steps)
        self.next_test()

    def next_test(self):
        """남은 시험이 있으면 준비 화면으로, 없으면 계산으로 넘어간다."""
        if self.pending:
            self.prepare(self.pending.pop(0))
        else:
            self.after_measurement()

    def prepare(self, test):
        label = self.TESTS[test]
        page = LivePressureData("측정 시작 버튼을 누르세요.")
        page.started.connect(lambda: self.measure(test))
        self.window.show_page(page, step=self.steps.index(label))

    def measure(self, test):
        label = self.TESTS[test]
        page = LiveMeasurementChart(f"{label} 시험 측정 중...", num_fans=self.fan_count)
        self.window.show_page(page, step=self.steps.index(label))

        task = BackgroundTask(test)
        task.progress.connect(page.set_progress)
        task.point.connect(page.add_point)
        task.position.connect(page.move_crosshair)
        # 중단 버튼 → 측정 루프가 스스로 빠져나오고 팬을 세운다
        page.cancelled.connect(task.cancel)
        self._connect(task, self.next_test)
        task.start()

    def after_measurement(self):
        # 측정 종료 시간 기록
        time_end = datetime.now().strftime("%H:%M:%S")
        self.data["test_period"] = f"{self.time_start}~{time_end}"
        with open(paths.CONDITIONS_JSON, "w") as file:
            json.dump(self.data, file, indent=4)
        self.run_task("calculation", "시험 결과를 계산하는 중…", "계산",
                      self.show_summary)

    def show_summary(self):
        """계산 결과를 띄우고, 그 화면을 유지한 채 그래프·성적서를 만든다.

        계산은 0.04초면 끝나지만 그래프·성적서는 도합 18초쯤 걸린다. 예전엔
        그 시간에 "그리는 중…" 한 줄만 떠 있었다. 이제 그동안 실제 계산 값을
        한 줄씩 내보여, 없는 지연을 만들지 않고도 볼 것을 준다.
        """
        with open(paths.CALCULATION_RAW_JSON, 'r') as file:
            report = json.load(file).get("report", {})

        self.summary = CalculationSummary(report, self.data)
        self.window.show_page(self.summary, step=self.steps.index("계산"))
        self.summary.start()
        # 결과를 읽는 동안 뒤에서 그래프를 만든다
        self.run_background("graph_plotting", "그래프를 그리는 중…", self.run_report)

    def run_report(self):
        # 같은 결과 화면을 유지한 채 단계 표시만 '성적서' 로 옮긴다
        self.window.header.set_current(self.steps.index("성적서"))
        self.run_background("reporting", "성적서를 만드는 중…", self.done)

    def run_background(self, kind, status, on_done):
        """결과 화면을 그대로 둔 채 백그라운드 작업만 실행한다."""
        self.summary.set_progress(status)
        task = BackgroundTask(kind)
        task.progress.connect(self.summary.set_progress)
        self._connect(task, on_done)
        task.start()

    def run_task(self, kind, title, step_name, on_done):
        """진행 페이지를 띄우고 백그라운드 작업을 실행한 뒤 다음 단계로 넘긴다."""
        page = ProgressPage(title)
        self.window.show_page(page, step=self.steps.index(step_name))
        task = BackgroundTask(kind)
        task.progress.connect(page.set_progress)
        self._connect(task, on_done)
        task.start()

    def done(self):
        # 결과 화면을 그대로 두고 끝났음만 알린다. 성적서 PDF 가 위에 떠서
        # 화면을 가리므로, 닫으면 결과가 그대로 남아 있는 편이 낫다.
        self.summary.set_progress("시험 완료 — 성적서(report.pdf)가 화면에 표시됩니다.")
        self.summary.set_done()
