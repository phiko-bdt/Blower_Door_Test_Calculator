#!/usr/bin/env python3
"""팬 연결 테스트 스크립트.

GPIO 13(물리핀 33) 하드웨어 PWM(1kHz)으로 팬 duty를 직접 설정한다.
GUI와 동일하게 bdt.hardware.duty_set()을 사용하므로
실제 배선/팬 동작 확인용으로 쓸 수 있다.

사용:
    python3 fan_test.py

    프롬프트에 0~100 사이 duty(%)를 입력하면 즉시 반영된다.
    q 또는 Ctrl+C 로 종료하면 duty 0%(정지)로 되돌린다.
"""

import sys

from bdt import hardware


def set_duty(duty):
    duty = max(0, min(100, duty))
    hardware.duty_set(duty, test=False)
    print(f"  → GPIO13 PWM duty = {duty}%")
    return duty


def main():
    print("=" * 40)
    print(" 팬 연결 테스트 (GPIO 13 / 물리핀 33, 1kHz PWM)")
    print("=" * 40)
    print(" 0~100 입력: 해당 duty(%)로 설정")
    print(" q 입력 또는 Ctrl+C: 정지(0%) 후 종료")
    print("-" * 40)

    # 시작은 항상 정지 상태로
    set_duty(0)

    try:
        while True:
            raw = input("duty(%) > ").strip().lower()
            if raw in ("q", "quit", "exit"):
                break
            if raw == "":
                continue
            try:
                value = float(raw)
            except ValueError:
                print("  ! 숫자(0~100) 또는 q 를 입력하세요.")
                continue
            set_duty(value)
    except KeyboardInterrupt:
        print()
    finally:
        print("정지합니다 (duty 0%).")
        set_duty(0)


if __name__ == "__main__":
    sys.exit(main())
