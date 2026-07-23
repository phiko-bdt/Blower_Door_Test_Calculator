#!/usr/bin/env python3
"""설명서용 앱 화면 캡처 — docs/screens/*.png 를 만든다.

  QT_QPA_PLATFORM=offscreen python3 docs/capture_screens.py

실제 앱 스타일시트(theme.APP_STYLE)를 입혀 화면 그대로 캡처한다. 하드웨어·
네트워크는 모킹한다(오프스크린). 성적서 화면은 이미 렌더된 report_page.png 를
그대로 쓰므로 여기서 만들지 않는다. build_manual.py 가 이 PNG 들을 삽입한다.
"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QEventLoop, QTimer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUTDIR = os.path.join(HERE, "screens")
os.makedirs(OUTDIR, exist_ok=True)
sys.path.insert(0, ROOT)

# ── 하드웨어·네트워크 모킹 ────────────────────────────────────
from bdt import hardware, web
hardware.pressure_read = lambda *a, **k: 0.4      # 준비 화면: 영기류 근처
hardware.duty_set = lambda *a, **k: None
web.ap_ip = lambda: "10.42.0.1"
web.lan_ip = lambda: "10.42.0.1"
web.ap_credentials = lambda: ("BlowerDoor-Test", "blowerdoor123")
web.wifi_qr_payload = lambda cred=None: "WIFI:T:WPA;S:BlowerDoor-Test;P:blowerdoor123;;"
web.lan_ssid = lambda: "BlowerDoor-Test"
web.PORT = 8080

from bdt.theme import APP_STYLE
from bdt.pages import (InputInitialValues, SettingsPage, PastReportsPage,
                       LivePressureData, TargetingPage, LiveMeasurementChart)

W, H = 1180, 720


def _settle(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def capture(widget, name, wait=350):
    widget.resize(W, H)
    widget.show()
    _settle(wait)
    path = os.path.join(OUTDIR, f"{name}.png")
    widget.grab().save(path)
    widget.hide()
    print("저장:", path)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)

    capture(InputInitialValues(), "input")
    capture(SettingsPage(), "settings")
    capture(LivePressureData("시험 준비 — 측정 시작 버튼을 누르세요."), "prepare",
            wait=700)
    capture(TargetingPage("팬 세기를 조절해 목표 압력(70 Pa)을 맞추는 중…"),
            "targeting")
    capture(LiveMeasurementChart("측정 중…", num_fans=1), "measure")
    capture(PastReportsPage(), "past_reports", wait=500)

    # 오프스크린 센서 폴러 스레드가 남아 종료가 늦을 수 있어 즉시 끝낸다.
    os._exit(0)


if __name__ == "__main__":
    main()
