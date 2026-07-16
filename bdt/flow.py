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
    LiveMeasurementChart,
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
        self.data = {}
        self.steps = []
        self.pending = []

    # ── 단계 진행 ────────────────────────────────────────────
    def start(self):
        self.window.header.set_steps(["조건 입력"])
        page = InputInitialValues()
        page.saved.connect(self.on_conditions_saved)
        self.window.show_page(page, step=0)

    def on_conditions_saved(self):
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
        task.finished.connect(self.next_test)
        self.task = task
        task.start()

    def after_measurement(self):
        # 측정 종료 시간 기록
        time_end = datetime.now().strftime("%H:%M:%S")
        self.data["test_period"] = f"{self.time_start}~{time_end}"
        with open(paths.CONDITIONS_JSON, "w") as file:
            json.dump(self.data, file, indent=4)
        self.run_task("calculation", "시험 결과를 계산하는 중…", "계산", self.run_graph)

    def run_graph(self):
        self.run_task("graph_plotting", "그래프를 그리는 중…", "계산", self.run_report)

    def run_report(self):
        self.run_task("reporting", "성적서를 만드는 중…", "성적서", self.done)

    def run_task(self, kind, title, step_name, on_done):
        """진행 페이지를 띄우고 백그라운드 작업을 실행한 뒤 다음 단계로 넘긴다."""
        page = ProgressPage(title)
        self.window.show_page(page, step=self.steps.index(step_name))
        task = BackgroundTask(kind)
        task.progress.connect(page.set_progress)
        task.finished.connect(on_done)
        self.task = task
        task.start()

    def done(self):
        page = ProgressPage("시험이 모두 끝났습니다")
        page.set_progress("성적서(report.pdf)가 화면에 표시됩니다.")
        self.window.show_page(page, step=len(self.steps) - 1)
