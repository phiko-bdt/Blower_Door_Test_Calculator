"""python3 -m bdt 진입점.

기밀성능 시험 앱을 구동한다. 시작·종료 시 팬 PWM duty 를 0 으로 두어
팬이 도는 상태로 남지 않도록 안전을 보장한다.
"""

import os
import sys
import atexit
import fcntl
import traceback

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QFontDatabase

from bdt import hardware
from bdt import paths
from bdt.widgets import alert
from bdt.config import TEST_MODE
from bdt.theme import APP_STYLE, WIN_W, WIN_H
from bdt.flow import MainWindow, TestFlow

# 중복 실행 잠금 파일. 열어둔 파일 객체가 살아 있어야 잠금이 유지되므로
# 모듈 수준에 참조를 든다.
_lock_file = None


def _another_instance_running():
    """이미 실행 중인 앱이 있으면 True.

    터치스크린에서는 아이콘 더블클릭이 두 번 먹는 일이 흔한데, 앱이 두 개
    뜨면 같은 팬 PWM 을 서로 다른 duty 로 다투게 된다 — 한쪽이 측정 중인데
    다른 쪽이 시작하며 duty 0 을 걸어 시험을 망치는 식이다.
    """
    global _lock_file
    _lock_file = open(os.path.join(paths.ROOT, ".bdt.lock"), "w")
    try:
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return False
    except OSError:
        return True


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
    app = QApplication(sys.argv)

    # 하드웨어를 건드리기 전에 중복 실행부터 확인한다. 두 번째 인스턴스가
    # duty 0 을 걸면 첫 인스턴스의 측정이 망가진다.
    if _another_instance_running():
        alert(None, "이미 실행 중",
              "기밀성능 시험 앱이 이미 실행되고 있습니다.\n"
              "열려 있는 창을 사용하세요.")
        sys.exit(0)

    # Ensure the fan PWM duty is zero on startup so that the fan does not run
    # even if powered. This provides a safe default state before any test begins.
    # duty_set 이 핀 레벨을 되읽어 검증하므로, 실패하면 팬이 계속 도는 상태다.
    # PWMUnavailable(오버레이 미적용·권한 문제)이 나도 죽지 않고 창을 띄운 뒤
    # 경고로 알린다 — 예외로 즉사하면 터치스크린에서는 창도 안내도 없다.
    fan_stop_error = None
    try:
        fan_stop_failed = hardware.duty_set(0, test=TEST_MODE) != 0
    except Exception as exc:
        traceback.print_exc()
        fan_stop_failed = True
        fan_stop_error = str(exc)
    # 정상 종료·예외·창 닫기 등 모든 종료 경로에서 팬을 정지시킨다
    atexit.register(stop_fan_on_exit)

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

    # 시험 전 과정을 담는 창 하나 (1280×800 터치스크린 기준).
    #
    # 부팅하면 이 앱이 바로 뜨는 현장 단말이라 전체화면으로 연다 — 작업자가
    # 창을 찾거나 데스크톱을 만질 일이 없어야 한다. 창 데코레이션이 없으므로
    # 종료는 헤더 오른쪽 '종료' 버튼이 맡는다 (StepHeader 참고).
    #
    # BDT_WINDOWED=1 이면 창 모드로 뜬다. 원격에서 화면을 확인할 때 전체화면은
    # 다른 창을 전부 가려 작업이 어렵다.
    window = MainWindow()
    window.resize(WIN_W, WIN_H)
    if os.environ.get("BDT_WINDOWED") == "1":
        window.show()
    else:
        window.showFullScreen()

    # 시작 시 팬 정지에 실패했다면 시험 전에 반드시 알린다
    if fan_stop_failed:
        if fan_stop_error:
            detail = f"원인: {fan_stop_error}"
        else:
            detail = ("팬이 계속 회전할 수 있으니 팬 전원을 차단해 주세요.")
        alert(window, "팬 정지 실패",
              f"팬을 정지시키지 못했습니다.\n\n{detail}")

    # 시험 절차 시작 (이후 진행은 시그널을 따라 페이지만 바뀐다)
    flow = TestFlow(window)
    window.flow = flow  # closeEvent 가 실행 중 작업을 정리할 수 있게
    flow.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
