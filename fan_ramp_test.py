#!/usr/bin/env python3
"""팬 램프 테스트.

시퀀스:
  1) duty 0% 로 시작 후 10초 대기
  2) 10% -> 100% 까지 10%씩 상승, 각 단계 5초 유지
  3) 90% -> 0% 까지 10%씩 하강, 각 단계 5초 유지
  4) 최종 0%(정지)

Ctrl+C 로 중단해도 안전하게 0%로 되돌린다.
"""

import time
import sensor_and_controller as s

HOLD = 5      # 각 단계 유지 시간(초)
START_WAIT = 10  # 시작 대기(초)


def set_duty(duty):
    duty = max(0, min(100, duty))
    s.duty_set(duty, test=False)
    print(f"  duty = {duty:3d}%")
    return duty


def main():
    print("=" * 40)
    print(" 팬 램프 테스트 (GPIO 13 / 물리핀 33, 1kHz PWM)")
    print("=" * 40)
    try:
        print(f"[시작] duty 0% 로 초기화 후 {START_WAIT}초 대기")
        set_duty(0)
        time.sleep(START_WAIT)

        print("[상승] 10% -> 100%")
        for duty in range(10, 101, 10):
            set_duty(duty)
            time.sleep(HOLD)

        print("[하강] 90% -> 0%")
        for duty in range(90, -1, -10):
            set_duty(duty)
            time.sleep(HOLD)

        print("[종료] 최종 duty 0%")
    except KeyboardInterrupt:
        print("\n중단됨 — 정지합니다.")
    finally:
        set_duty(0)
    print("완료")


if __name__ == "__main__":
    main()
