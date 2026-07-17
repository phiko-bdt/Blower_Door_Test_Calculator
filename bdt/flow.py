"""단일 창(MainWindow)과 시험 절차 진행(TestFlow)."""

import json
from datetime import datetime

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QMainWindow,
                             QStackedWidget, QMessageBox)
from PyQt6.QtCore import QObject

from bdt import paths
from bdt.widgets import StepHeader
from bdt.pages import (
    InputInitialValues,
    LivePressureData,
    ProgressPage,
    ErrorPage,
    LiveMeasurementChart,
    TargetingPage,
    CalculationSummary,
)
from bdt.tasks import BackgroundTask, TARGET_PRESSURE


class MainWindow(QMainWindow):
    """시험 전 과정을 담는 단일 창.

    단계마다 창을 새로 띄우지 않고 이 창 안에서 페이지만 바꾼다.
    덕분에 창 크기·위치가 시험 내내 유지된다.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("기밀성능 시험")
        # 측정이 진행 중인지 (TestFlow 가 갱신). 창 닫기 확인에 쓴다.
        self.measuring = False

        self.header = StepHeader()
        self.stack = QStackedWidget()

        center = QWidget()
        outer = QVBoxLayout(center)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.header)
        outer.addWidget(self.stack, 1)
        self.setCentralWidget(center)

    def closeEvent(self, event):
        """작업 중에는 확인 없이 닫히지 않게 하고, 닫을 때는 작업을 정리한다.

        '시험 중단' 버튼에는 확인창이 있는데 창의 X 버튼이 그걸 우회해
        몇 분치 측정이 조용히 증발했다. 그리고 확인만 받고 워커를 그대로
        두면, 종료 후에도 살아 있는 측정 스레드가 duty 를 써넣어 앱은
        꺼졌는데 팬이 도는 상태가 될 수 있다 (sysfs PWM 은 프로세스가
        죽어도 유지된다). 승인 시 cancel + wait 로 반드시 정리한다.
        """
        flow = getattr(self, "flow", None)
        task = getattr(flow, "task", None) if flow else None
        running = task is not None and task.isRunning()
        if running:
            if self.measuring:
                text = ("측정이 진행 중입니다. 앱을 종료할까요?\n\n"
                        "지금까지 측정한 값은 저장되지 않고, 팬은 정지합니다.")
            else:
                text = ("계산·성적서 작업이 진행 중입니다. 앱을 종료할까요?\n\n"
                        "이번 시험의 성적서가 만들어지지 않을 수 있습니다.")
            answer = QMessageBox.question(
                self, "작업 진행 중", text,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            task.cancel()
            task.wait(5000)  # 워커가 팬을 세우고 빠져나올 시간
        event.accept()

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
        self.window.measuring = False
        page = ErrorPage("시험을 계속할 수 없습니다", message)
        page.restart.connect(self.start)
        self.window.show_page(page)

    def on_cancelled(self):
        """사용자가 시험을 중단했다 — 조건 입력부터 다시 시작한다."""
        self.stopped = True
        self.window.measuring = False
        self.start()

    def _connect(self, task, on_done):
        """작업의 완료·실패·중단 시그널을 한 자리에서 연결한다.

        실패·중단 표시는 flow 수준 플래그가 아니라 **그 작업 자신**에 남긴다.
        예전엔 flow.stopped 하나로 판단했는데, 중단 시 on_cancelled → start()
        가 stopped 를 즉시 False 로 되돌린 뒤 큐에 남아 있던 finished 가
        가드를 통과해 계산 단계로 직행했다 — 지난 시험의 raw 파일로 성적서가
        발행되는 레이스다. 같은 작업의 시그널은 emit 순서대로 배달되므로
        작업 객체에 남긴 표시는 레이스가 없다.
        """
        task._halted = False

        def on_error(message):
            task._halted = True
            self.on_error(message)

        def on_cancelled():
            task._halted = True
            self.on_cancelled()

        def proceed():
            if task._halted:
                return
            on_done()

        task.error.connect(on_error)
        task.cancelled.connect(on_cancelled)
        task.finished.connect(proceed)
        # QThread 는 파이썬 참조가 사라져도 C++ 스레드가 정리 중일 수 있어,
        # 마지막 참조가 too early 로 끊기면 "Destroyed while thread is still
        # running" 으로 죽는다. flow 를 부모로 걸어 수명을 보장한다
        # (시험당 작업 몇 개 수준이라 누적 부담은 무시할 만하다).
        task.setParent(self)
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
        self.window.measuring = False
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
        """목표 압력 조절 페이지부터 시작한다.

        PID 가 건물에 맞는 팬 세기를 찾아 압력을 목표(70 Pa)로 끌어올리는
        과정을 전용 화면으로 보여주고, 조절이 끝나면(targeted 시그널)
        측정 차트로 넘어간다.
        """
        label = self.TESTS[test]
        page = TargetingPage(f"{label} 시험 — 목표 압력 조절 중",
                             target=TARGET_PRESSURE)
        self.window.show_page(page, step=self.steps.index(label))

        task = BackgroundTask(test)
        task.progress.connect(page.set_progress)
        task.raw_position.connect(page.update_position)
        # 중단 버튼 → 측정 루프가 스스로 빠져나오고 팬을 세운다
        page.cancelled.connect(task.cancel)
        task.targeted.connect(lambda: self.show_measurement(test, task))
        self.window.measuring = True
        self._connect(task, self.next_test)
        task.start()

    def show_measurement(self, test, task):
        """조절이 끝났다 — 측정 차트 페이지로 전환하고 신호를 옮겨 단다.

        이전(조절) 페이지는 show_page 가 정리하며, 파괴된 위젯으로 가던
        시그널 연결은 Qt 가 자동으로 끊는다.
        """
        if getattr(task, "_halted", False):
            return
        label = self.TESTS[test]
        page = LiveMeasurementChart(f"{label} 시험 측정 중…", num_fans=self.fan_count)
        self.window.show_page(page, step=self.steps.index(label))
        task.progress.connect(page.set_progress)
        task.point.connect(page.add_point)
        task.position.connect(page.move_crosshair)
        page.cancelled.connect(task.cancel)

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
        self.run_background("graph_plotting", "누기 그래프를 그리는 중…", self.run_report)

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
        # 다음 세대 시험을 앱 재시작 없이 시작할 수 있게 한다
        self.summary.restart_button.clicked.connect(self.start)
