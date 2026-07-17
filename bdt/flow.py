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
    SettingsPage,
    ReportPage,
)
from bdt import settings
from bdt.tasks import BackgroundTask


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
        self.header.quit_button.clicked.connect(self._confirm_quit)
        self.stack = QStackedWidget()

        center = QWidget()
        outer = QVBoxLayout(center)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.header)
        outer.addWidget(self.stack, 1)
        self.setCentralWidget(center)

    def _confirm_quit(self):
        """헤더의 종료 버튼 — 한 번 되묻고 닫는다.

        closeEvent 는 작업 중일 때만 확인을 받는다 (창의 X 를 누르는 건
        분명한 의사표시였다). 전체화면에서는 이 버튼이 유일한 종료 수단이라
        화면 구석에 늘 떠 있으므로, 지나가다 스친 터치로 앱이 꺼지지 않게
        여기서 한 번 더 묻는다.
        """
        answer = QMessageBox.question(
            self, "앱 종료", "기밀성능 시험 앱을 종료할까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.close()  # 진행 중 작업 정리는 closeEvent 가 맡는다

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
        # 성적서 사본을 남긴 자리 (reporting 작업이 알려준다) — 성적서 화면이
        # 작업자에게 어디서 찾는지 안내하는 데 쓴다
        self.archived_path = None
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
        page.settings_requested.connect(self.show_settings)
        self.window.show_page(page, step=0)

    def show_settings(self):
        """설정 페이지 — 닫으면 조건 입력으로 돌아온다.

        입력하던 조건은 남기지 않는다. 설정을 고칠 일은 시험 시작 전이고,
        입력값을 보존하려면 저장 안 된 상태를 들고 다녀야 해 얻는 것보다
        복잡해진다.
        """
        # 설정은 시험 단계가 아니다 — 헤더에 '조건 입력'이 켜진 채로 두면
        # 시험이 진행 중인 것처럼 보인다. 복귀할 때 start() 가 되돌린다.
        self.window.header.set_steps(["설정"])
        page = SettingsPage()
        page.closed.connect(self.start)
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

    def on_impossible(self, message):
        """현장 조건이 시험을 허락하지 않는다 — 장비 오류와 구분해 알린다.

        팬을 최소로 낮춰도 압력이 상한을 넘는 경우다. 작업자가 장비를
        의심하며 시간을 쓰지 않도록, 원인(외풍·과도한 기밀)과 대처를
        제목에서부터 분명히 한다.
        """
        self.stopped = True
        self.window.measuring = False
        page = ErrorPage("시험 불가 — 압력을 제어할 수 없습니다", message)
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

        def on_impossible(message):
            task._halted = True
            self.on_impossible(message)

        def proceed():
            if task._halted:
                return
            on_done()

        task.error.connect(on_error)
        task.cancelled.connect(on_cancelled)
        task.impossible.connect(on_impossible)
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
        cfg = settings.load()
        page = TargetingPage(f"{label} 시험 — 목표 압력 조절 중",
                             target=cfg["target_pressure"],
                             tolerance=settings.tolerance_pa(cfg))
        self.window.show_page(page, step=self.steps.index(label))

        task = BackgroundTask(test)
        task.progress.connect(page.set_progress)
        task.raw_position.connect(page.update_position)
        task.hold.connect(page.update_hold)
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
        self.archived_path = None
        self.run_background("reporting", "성적서를 만드는 중…", self.done,
                            on_archived=self._remember_archive)

    def _remember_archive(self, path):
        self.archived_path = path

    def run_background(self, kind, status, on_done, on_archived=None):
        """결과 화면을 그대로 둔 채 백그라운드 작업만 실행한다."""
        self.summary.set_progress(status)
        task = BackgroundTask(kind)
        task.progress.connect(self.summary.set_progress)
        if on_archived:
            task.archived.connect(on_archived)
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
        """성적서를 앱 안에서 보여준다 — 시험의 마지막 화면.

        예전엔 계산 결과 화면을 그대로 두고 외부 뷰어(evince)가 그 위에
        성적서를 띄웠다. 전체화면 단말에서 남의 창이 위를 덮고, 작업자가
        그걸 닫아야 앱으로 돌아왔다. 이제 성적서까지 앱 안에 둔다
        (PDF 파일은 예전과 같은 자리에 그대로 저장된다).
        """
        page = ReportPage(archive_path=self.archived_path)
        page.restart.connect(self.start)  # 앱 재시작 없이 다음 시험으로
        self.window.show_page(page, step=self.steps.index("성적서"))
