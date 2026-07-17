"""PWM-압력 PID 제어.

reversible fan 의 duty 를 PID 로 조절해 목표 압력에 도달시킨다.
센서 입력·팬 출력은 bdt.hardware 를 통해 수행한다.
"""

import time

from simple_pid import PID

from bdt import hardware


def duty_transformation(input_value, min_value, max_value):
    # 입력 값이 최소와 최대 값 사이에 있는지 확인
    if not 0 <= input_value <= 100:
        raise ValueError("Input value should be between 0 and 100")

    # 변환 함수
    if min_value > max_value:
        # Forward flow일 때, 0~100까지를 45~10으로 변환
        min_value, max_value = max_value, min_value
        transformed_value = (1 - input_value / 100) * (max_value - min_value) + min_value

    else:
        # Reverse flow일 때, 0~100까지를 55~90으로 변환
        transformed_value = (input_value / 100) * (max_value - min_value) + min_value

    return round(transformed_value)

def get_duty(target, delay, average_time, control_limit, duty_min=0, duty_max=100, test=True,
             progress=None, on_point=None, check_cancelled=None):
    '''
    [2023-11-18]
    reversible fan 사용 시 pwm duty
    10~45 까지 forward (가압) 10이 max, 45가 min
    55~90 까지 reverse (감압) 55가 min, 90이 max
    duty를 기반으로 pressure 제어 하는 코드를 실행하기 위해, duty 변환 함수를 사용해서 제어
    initial controlled duty = 0 → pwm-pressure PID control → duty result → function^-1(duty result) → real duty

    progress: 진행 상황을 받을 콜백. 지정하지 않으면 터미널에만 출력한다.
    on_point: 제어 중 측정한 (duty, 압력)을 받을 콜백. 실시간 그래프 표시에 쓴다.
    check_cancelled: 중단 요청을 확인하는 콜백(중단이면 예외를 던진다).
        목표 압력에 닿지 못하면 이 루프가 오래 돌 수 있어, 그동안에도 사용자가
        시험을 멈출 수 있어야 한다.
    '''
    def notify(message):
        if progress:
            progress(message)
        else:
            print(message)

    def notify_point(duty_value, pressure):
        if on_point:
            on_point(duty_value, pressure)

    def cancel_check():
        if check_cancelled:
            check_cancelled()

    # 테스트 모드
    if test:
        return (duty_max, True, target)
    # 현재 압력 값 측정 및 초기값 세팅
    current = abs(hardware.pressure_read(0.1, test=test))
    duty = 0

    # 압력 수렴 조건
    convergence_time = 0
    pressure_threshold = target/10
    duration = 10
    # duty 수렴 조건
    window = []
    window_size = 50

    # 실패 조건
    failure_time = 0

    # 종료 측정 조건
    final_measure_time = 5

    # PID 컨트롤러 생성
    pid = PID(1, 0, 0, setpoint=target)
    pid.auto_mode = True
    pid.output_limits = (-control_limit, control_limit)

    while True:
        cancel_check()
        # 제어 시작 시간
        time_start = time.time()
        # PID 계산
        control = pid(current)
        # duty 업데이트 및 상하한 설정
        duty += control
        duty = round(duty)
        duty = max(0, min(100, duty))
        # PID 제어용 duty에서 실제 duty값으로 변경
        duty_real = duty_transformation(duty, duty_min, duty_max)
        # duty 값 적용
        hardware.duty_set(duty_real, test=False)
        # 압력 변화를 기다리는 동안(delay) 압력을 짧은 주기로 읽어 실시간 위치를 갱신한다.
        # (기존엔 delay 만큼 통째로 sleep 해서 그래프가 delay 마다 한 번만 움직였다)
        deadline = time.time() + delay
        while time.time() < deadline:
            cancel_check()
            live = abs(hardware.pressure_read(0.1, test=test))
            notify_point(duty_real, live)
        # 압력 값 측정
        current = abs(hardware.pressure_read(average_time, test=test))
        # duty의 이동 평균 계산
        window.append(duty)
        if len(window) > window_size:
            window = window[1:]

        duty_avg = sum(window)/len(window)

        # 제어 종료 시간
        time_diff = time.time() - time_start
        # 압력 오차
        error_pressure = abs(target - current)
        # duty 오차 # 사용하지 않음
        error_duty = abs(duty_avg - duty)
        # 제어 중 측정한 점도 실시간 그래프에 표시한다
        notify_point(duty_real, current)

        if error_pressure < pressure_threshold: # and error_duty < max(2, duty/10):
            convergence_time += time_diff
            notify(f"팬 세기 {duty_real}% — 압력 {current:.1f} / 목표 {target} Pa "
                   f"· 안정화 중 ({convergence_time:.0f}/{duration}초)")
        else:
            convergence_time = 0
            notify(f"팬 세기 {duty_real}% — 압력 {current:.1f} / 목표 {target} Pa "
                   f"· 조절 중 (오차 {error_pressure:.1f} Pa)")

        if convergence_time >= duration:
            current = abs(hardware.pressure_read(final_measure_time, test=test))
            notify(f"목표 압력 {target} Pa 도달 (측정값 {current:.1f} Pa)")
            # 실제 duty값으로 변환 후 반환
            duty_real = duty_transformation(duty, duty_min, duty_max)
            return (duty_real, True, current)

        # duty 가 한계에 붙었는데 수렴 문턱(pressure_threshold)을 넘는 오차가
        # 남아 있으면 실패로 센다. 예전엔 실패 문턱이 20 Pa 로 따로 있어서
        # 오차가 7~20 Pa 인 채 duty 100 에 포화되면 수렴도 실패도 아닌
        # 데드존에 갇혀 영영 반환하지 않았다.
        if duty == 100 and error_pressure >= pressure_threshold:
            notify(f"팬을 최대로 돌려도 목표 {target} Pa에 못 미칩니다 "
                   f"(현재 {current:.1f} Pa) — 누기량이 많거나 개구부가 열려 있는지 확인하세요")
            failure_time += time_diff
        elif duty == 0 and error_pressure >= pressure_threshold:
            # PID duty 0 은 팬 정지가 아니라 duty_min(팬이 도는 최소 세기)이다.
            # 예전엔 '팬을 멈춰도'라고 알려서, 실제로는 팬이 최소로 돌고 있는데
            # 작업자가 센서·외풍 문제로 오진하게 만들었다.
            notify(f"팬을 최소({duty_min}%)로 낮춰도 압력이 목표 {target} Pa를 "
                   f"넘습니다 (현재 {current:.1f} Pa) — 외풍이나 센서 상태를 "
                   "확인하세요")
            failure_time += time_diff
        else:
            failure_time = 0

        if failure_time >= duration:
            current = abs(hardware.pressure_read(final_measure_time, test=test))
            notify(f"목표 압력 조절 실패 (최종 {current:.1f} Pa)")
            # 실제 duty값으로 변환 후 반환
            duty_real = duty_transformation(duty, duty_min, duty_max)
            return (duty_real, False, current)
