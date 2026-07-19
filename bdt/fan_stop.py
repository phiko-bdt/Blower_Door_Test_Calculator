"""부팅 시 팬 PWM duty 0 고정 (안전 초기화).

`python3 -m bdt.fan_stop` 으로 실행하며, systemd 유닛 bdt-fan-stop.service 가
부팅 때 한 번 호출한다.

목적(fool proof): 앱을 켜기 전에 팬 전원을 먼저 올리는 운용 순서에서도 팬이
돌지 않게 보장한다. GPIO 는 부팅 직후 입력(하이임피던스) 상태라 팬 컨트롤러가
PWM 선을 HIGH 로 읽어 100% 로 도는 사고가 가능하다. duty 0% 를 명시적으로
출력해 핀을 LOW 로 고정해 둔다.

sysfs PWM 설정은 프로세스가 끝나도 커널이 유지하므로, 이 스크립트가
종료된 뒤에도 duty 0 은 그대로 남는다.

핀 레벨 되읽기(duty_set 의 검증)에 실패하면 0 이 아닌 값으로 종료해
`systemctl status bdt-fan-stop` 에 실패로 드러나게 한다.
"""

import sys
import time

from bdt import fan_guard
from bdt import hardware
from bdt.config import TEST_MODE

# 부팅 직후에는 PWM 오버레이 적용·udev 권한 설정이 아직 안 끝났을 수 있다.
# 한 번 실패했다고 팬을 방치하면 안 되므로 재시도한다.
RETRY_COUNT = 10
RETRY_INTERVAL = 1.0  # 초


def main():
    # 앱이 실행 중이면 팬은 앱이 관리한다 — 건드리면 측정을 망친다.
    # 실제 사고 경로: 측정 중 바탕화면 아이콘을 다시 탭 → 두 번째 인스턴스가
    # 중복 감지로 정상 종료 → .desktop/autostart 의 후행 fan_stop 이 실행돼
    # 첫 인스턴스가 돌리던 팬을 꺼 버린다. 부팅·크래시 뒤처리 경로에서는
    # 앱이 없으므로 이 확인이 걸리지 않는다.
    if fan_guard.app_running():
        print("기밀성능 시험 앱이 실행 중입니다 — 팬 제어는 앱에 맡기고 "
              "duty 를 건드리지 않습니다.")
        return 0

    last_error = None

    for attempt in range(1, RETRY_COUNT + 1):
        try:
            result = hardware.duty_set(0, test=TEST_MODE)
        except Exception as exc:  # PWM 준비 안 됨 등
            last_error = exc
            print(f"[{attempt}/{RETRY_COUNT}] 팬 PWM 준비 대기 중: {exc}")
            time.sleep(RETRY_INTERVAL)
            continue

        if result == 0:
            print(f"팬 PWM duty 0% 설정 완료 (GPIO{hardware.PWM_GPIO} LOW 확인).")
            return 0

        # 연결은 됐지만 핀이 LOW 로 내려가지 않은 경우 = 핀 손상 의심.
        # 재시도해도 낫지 않으므로 즉시 실패로 알린다.
        print(f"팬 정지 실패: GPIO{hardware.PWM_GPIO} 가 LOW 로 내려가지 않습니다. "
              "PWM 핀 손상이 의심되니 팬 전원을 수동으로 차단하고 배선을 점검하세요.",
              file=sys.stderr)
        return 1

    print(f"팬 정지 실패: 팬 PWM 을 준비하지 못했습니다 ({last_error}).",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
