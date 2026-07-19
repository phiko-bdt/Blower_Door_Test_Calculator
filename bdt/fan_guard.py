"""팬 안전 감시 — 앱이 실행 중이 아니면 PWM duty 0 을 강제한다.

`python3 -m bdt.fan_guard` 로 실행하며, systemd 유닛 bdt-fan-guard.service 가
부팅 때 띄워 계속 돌린다.

기존 안전장치(config.txt 펌웨어 LOW · 부팅 fan_stop · 앱 종료 후행 fan_stop ·
앱 atexit)는 모두 **특정 시점에 한 번씩** duty 0 을 건다. 그런데 앱이 측정 중
(팬이 도는 상태)에 SIGKILL 로 갑자기 죽거나, autostart 래퍼를 거치지 않고
직접 실행한 앱이 비정상 종료하면, duty 가 0 으로 안 내려간 채 앱이 없는
상태가 될 수 있다. 이 감시 장치가 그 틈을 메운다: 몇 초마다 '앱이 도는가'를
확인해, **앱이 없으면 duty 0 을 건다.** 앱이 돌고 있으면 손대지 않는다
(측정 중 팬이 도는 게 정상이므로).

sysfs PWM 은 프로세스가 끝나도 커널이 유지하므로, 한 번 0 으로 내려두면
다음 확인까지 그대로 있다.
"""

import os
import time
import traceback

from bdt import hardware
from bdt.config import TEST_MODE

# 확인 주기. 짧을수록 비정상 종료 후 팬이 도는 시간이 줄지만, 그만큼 자주
# 깨어난다. duty 확인·쓰기는 가벼워(수 ms) 1초로 촘촘히 둔다.
CHECK_INTERVAL = 1.0


def is_app_cmdline(args):
    """명령줄 인자가 기밀성능 시험 앱(`python3 -m bdt`)인지 판정한다.

    `-m` 바로 다음 인자가 **정확히 "bdt"** 여야 한다. 이 감시 장치
    (`-m bdt.fan_guard`)나 부팅 정지(`-m bdt.fan_stop`)는 다음 인자가
    "bdt.fan_guard"·"bdt.fan_stop" 이라 걸리지 않는다 — 부분 일치
    (pgrep -f "bdt")로는 자기 자신을 앱으로 오인해 영영 duty 0 을 안 건다.
    """
    for i in range(len(args) - 1):
        if args[i] == "-m" and args[i + 1] == "bdt":
            return True
    return False


def app_running():
    """기밀성능 시험 앱(`python3 -m bdt`)이 실행 중이면 True."""
    my_pid = str(os.getpid())
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or entry == my_pid:
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as f:
                args = [a.decode(errors="replace")
                        for a in f.read().split(b"\0") if a]
        except OSError:
            # 프로세스가 그 사이 사라졌거나 접근 불가 — 넘어간다
            continue
        if is_app_cmdline(args):
            return True
    return False


def main():
    print(f"팬 감시 시작 (주기 {CHECK_INTERVAL:.0f}초). "
          "앱이 없을 때 PWM duty 0 을 강제합니다.")
    while True:
        try:
            if not app_running():
                # 앱이 없다 = 팬을 쥔 주인이 없다. duty 0 을 건다 (이미 0 이면
                # 그대로 유지되는 무해한 쓰기). 앱이 있으면 팬은 앱이 관리한다.
                hardware.duty_set(0, test=TEST_MODE)
        except Exception:
            # 감시 장치는 절대 죽으면 안 된다 — 오류를 남기고 계속 돈다
            # (systemd Restart=always 도 있지만, 여기서 삼켜 재시작 폭주를 막는다).
            traceback.print_exc()
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
