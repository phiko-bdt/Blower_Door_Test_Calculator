"""스모크 테스트 — 하드웨어 없이 앱의 핵심 경로를 종단으로 검증한다.

실행:  QT_QPA_PLATFORM=offscreen python3 tests/smoke.py
       (저장소 루트에서. 약 30초. 모든 검사 통과 시 종료코드 0)

센서·팬은 전부 모킹하므로 실기기가 아니어도, 팬이 물려 있어도 안전하다.
저장소 루트의 실데이터(conditions.json, *_raw.json)를 잠시 사용하며
끝나면 원본을 복원한다.

코드 리뷰(2026-07-17)에서 실제 재현으로 확정했던 결함들의 회귀 방지가
목적이다 — 각 검사에 어떤 사고를 막는지 적어 두었다.
"""

import json
import math
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402
from PyQt6.QtCore import QTimer  # noqa: E402

from bdt import hardware, control, paths, tasks  # noqa: E402

DATA_FILES = ("conditions.json", "depressurization_raw.json",
              "pressurization_raw.json", "calculation_raw.json")

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(ok)
    mark = "OK  " if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))


def install_mocks():
    """하드웨어를 완전히 차단한다. duty 에 비례해 압력이 형성되는 흉내."""
    state = {"duty": 20}

    def duty_set(d, test=True):
        try:
            state["duty"] = int(float(str(d)))
        except (ValueError, TypeError):
            pass
        return 0

    hardware.duty_set = duty_set
    hardware.pressure_read = lambda **k: -(
        15.0 + state["duty"] * 0.75 + math.sin(time.time() * 7) * 0.8)

    def fast_get_duty(**kw):
        state["duty"] = 68
        if kw.get("on_point"):
            for i in range(5):
                kw["on_point"](68, 50 + i)
        return (68, True, 65.8)

    control.get_duty = fast_get_duty
    tasks.SETTLE_SECONDS_PER_DUTY = 0
    tasks.MEASURE_SECONDS = 0.12
    tasks.BackgroundTask.open_pdf = lambda self, p: None
    return state


def main():
    backup = tempfile.mkdtemp(prefix="bdt_smoke_")
    for f in DATA_FILES:
        if os.path.exists(f):
            shutil.copy(f, os.path.join(backup, f))

    app = QApplication(sys.argv)
    install_mocks()
    from bdt.flow import MainWindow, TestFlow

    try:
        # ── 1. 정상 경로: 측정 → 계산 → 그래프 → 성적서 ────────
        # (조절 페이지는 모킹이 즉시 반환해 건너뛴다)
        print("1. 정상 경로 종단")
        w = MainWindow(); w.resize(1180, 720); w.show()
        flow = TestFlow(w); w.flow = flow
        cond = json.load(open(paths.CONDITIONS_JSON))
        cond.update(depressurization=True, pressurization=False, fan_count=1)
        json.dump(cond, open(paths.CONDITIONS_JSON, "w"), indent=4)
        flow.data = cond
        flow.time_start = "26/07/17 00:00:00"
        flow.fan_count = 1
        flow.steps = ["조건 입력", "감압", "계산", "성적서"]
        w.header.set_steps(flow.steps)

        done = []
        orig_done = flow.done
        flow.done = lambda: (orig_done(), done.append(1),
                             QTimer.singleShot(200, app.quit))
        flow.measure("depressurization")
        QTimer.singleShot(60000, app.quit)
        app.exec()
        check("완료까지 도달", bool(done))
        report = json.load(open(paths.CALCULATION_RAW_JSON)).get("report", {})
        ach = report.get("ACH50-")
        check("계산 결과 산출", isinstance(ach, float) and 0 < ach < 100,
              f"ACH50- = {ach}")
        check("성적서 PDF 존재", os.path.exists(paths.REPORT_PDF))

        # ── 2. 취소 레이스: 중단 후 계산으로 직행하면 안 된다 ───
        # (사고: 지난 시험 데이터로 성적서 자동 발행)
        print("2. 시험 중단 레이스")

        def slow_get_duty(**kw):
            cc = kw.get("check_cancelled")
            for _ in range(50):
                if cc:
                    cc()
                time.sleep(0.1)
            return (68, True, 65.8)

        control.get_duty = slow_get_duty
        w2 = MainWindow(); w2.resize(1180, 720); w2.show()
        flow2 = TestFlow(w2); w2.flow = flow2
        flow2.data = cond; flow2.time_start = "x"; flow2.fan_count = 1
        flow2.steps = ["조건 입력", "감압", "계산", "성적서"]
        w2.header.set_steps(flow2.steps)
        pages = []
        poll = QTimer()
        poll.timeout.connect(lambda: (
            pages.append(type(w2.stack.currentWidget()).__name__)
            if not pages or pages[-1] != type(w2.stack.currentWidget()).__name__
            else None))
        poll.start(50)
        flow2.measure("depressurization")
        QTimer.singleShot(800, lambda: flow2.task.cancel())
        QTimer.singleShot(6000, app.quit)
        app.exec()
        poll.stop()
        raced = any(p in ("ProgressPage", "CalculationSummary") for p in pages)
        check("중단 후 계산 미진행", not raced, " → ".join(pages))

        # ── 3. 실패가 침묵하지 않는다 ───────────────────────────
        print("3. 실패 경로")
        t = tasks.BackgroundTask("no_such_task")
        ev = []
        t.error.connect(lambda e: ev.append("error"))
        t.run()
        check("미지의 task_type → error", "error" in ev)

        from bdt.report import html
        orig_make = html.make_report_pdf
        html.make_report_pdf = lambda *a, **k: None
        t = tasks.BackgroundTask("reporting")
        ev2 = []
        t.error.connect(lambda e: ev2.append("error"))
        t.run()
        html.make_report_pdf = orig_make
        check("성적서 생성 실패 → error", "error" in ev2)

        try:
            hardware.__dict__["pressure_read"]  # 모킹 전 원본이 필요하다
        except KeyError:
            pass
        import importlib
        importlib.reload(hardware)
        try:
            hardware.pressure_read(average_time=0.1, port="/dev/ttyUSB9",
                                   test=False)
            check("없는 포트 → SensorTimeout", False, "예외 없음")
        except hardware.SensorTimeout:
            check("없는 포트 → SensorTimeout", True)
        except Exception as exc:
            check("없는 포트 → SensorTimeout", False, type(exc).__name__)
        install_mocks()  # reload 가 모킹을 지웠으므로 복구

        # ── 4. 빈 측정 차트의 축 (씨앗 범위 유지) ────────────────
        print("4. 차트 경계 조건")
        from bdt.pages import LiveMeasurementChart
        LiveMeasurementChart.reset()
        pg = LiveMeasurementChart("측정", num_fans=1)
        span = pg.axis_x.max() - pg.axis_x.min()
        check("점 0개 x축 = 씨앗 범위", span >= 50,
              f"{pg.axis_x.min():.0f}~{pg.axis_x.max():.0f} Pa")
        pg.add_point(1300, 45, 0.9, "depressurization")
        check("점 1개 후 데이터 맞춤 전환",
              pg.axis_x.max() - pg.axis_x.min() < span)

        # ── 5. 종료 시 워커 정리 ────────────────────────────────
        print("5. 창 닫기 정리")
        control.get_duty = slow_get_duty
        QMessageBox.question = staticmethod(
            lambda *a, **k: QMessageBox.StandardButton.Yes)
        w3 = MainWindow(); w3.resize(1180, 720); w3.show()
        flow3 = TestFlow(w3); w3.flow = flow3
        flow3.data = cond; flow3.time_start = "x"; flow3.fan_count = 1
        flow3.steps = ["조건 입력", "감압", "계산", "성적서"]
        w3.header.set_steps(flow3.steps)
        flow3.measure("depressurization")
        result = {}

        def do_close():
            w3.close()
            result["running"] = flow3.task.isRunning()
            app.quit()

        QTimer.singleShot(800, do_close)
        QTimer.singleShot(10000, app.quit)
        app.exec()
        check("닫기 승인 시 워커 종료", result.get("running") is False)

    finally:
        for f in DATA_FILES:
            src = os.path.join(backup, f)
            if os.path.exists(src):
                shutil.copy(src, f)
        shutil.rmtree(backup, ignore_errors=True)
        print("(실데이터 복원 완료)")

    passed = sum(RESULTS)
    print(f"\n{passed}/{len(RESULTS)} 통과")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
