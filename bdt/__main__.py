"""python3 -m bdt 진입점.

기밀성능 시험 앱을 구동한다. 시작·종료 시 팬 PWM duty 를 0 으로 두어
팬이 도는 상태로 남지 않도록 안전을 보장한다.
"""

import sys
import atexit
import traceback

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QFont, QFontDatabase

from bdt import hardware
from bdt import paths
from bdt.config import TEST_MODE
from bdt.theme import APP_STYLE, WIN_W, WIN_H
from bdt.flow import MainWindow, TestFlow


def stop_fan_on_exit():
    """프로그램이 어떤 경로로 끝나든 팬을 정지시킨다.

    hardware_PWM 설정은 프로세스가 끝나도 하드웨어에 그대로 남으므로,
    종료 시 duty 0 을 명시하지 않으면 팬이 계속 돈다.
    """
    try:
        hardware.duty_set(0, test=TEST_MODE)
    except Exception:
        traceback.print_exc()


def main():
    # Ensure the fan PWM duty is zero on startup so that the fan does not run
    # even if powered. This provides a safe default state before any test begins.
    # duty_set 이 핀 레벨을 되읽어 검증하므로, 실패하면 팬이 계속 도는 상태다.
    fan_stop_failed = hardware.duty_set(0, test=TEST_MODE) != 0
    # 정상 종료·예외·창 닫기 등 모든 종료 경로에서 팬을 정지시킨다
    atexit.register(stop_fan_on_exit)

    app = QApplication(sys.argv)
    # 전역 디자인 테마 적용
    app.setStyleSheet(APP_STYLE)

    # 폰트 설정
    font_id = QFontDatabase.addApplicationFont(paths.FONT_PATH)
    if font_id != -1:
        font_families = QFontDatabase.applicationFontFamilies(font_id)
        # 로드한 글꼴의 첫 번째 패밀리를 사용
        app.setFont(QFont(font_families[0], 11))
    else:
        print("Failed to load font.")

    # 시험 전 과정을 담는 창 하나 (1280×800 터치스크린 기준)
    window = MainWindow()
    window.resize(WIN_W, WIN_H)
    window.show()

    # 시작 시 팬 정지에 실패했다면(PWM 핀 손상 의심) 시험 전에 반드시 알린다
    if fan_stop_failed:
        QMessageBox.warning(
            window, "팬 정지 실패",
            f"팬을 정지시키지 못했습니다 (PWM 핀 GPIO{hardware.PWM_GPIO} 손상 의심).\n\n"
            "팬이 계속 회전할 수 있으니 전원을 수동으로 차단하고,\n"
            "PWM 배선과 핀 상태를 점검한 뒤 시험을 진행하세요.")

    # 시험 절차 시작 (이후 진행은 시그널을 따라 페이지만 바뀐다)
    flow = TestFlow(window)
    flow.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
