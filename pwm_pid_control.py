import time
from simple_pid import PID
import sensor_and_controller

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
             progress=None, on_point=None):
    '''
    [2023-11-18]
    reversible fan 사용 시 pwm duty
    10~45 까지 forward (가압) 10이 max, 45가 min
    55~90 까지 reverse (감압) 55가 min, 90이 max
    duty를 기반으로 pressure 제어 하는 코드를 실행하기 위해, duty 변환 함수를 사용해서 제어
    initial controlled duty = 0 → pwm-pressure PID control → duty result → function^-1(duty result) → real duty

    progress: 진행 상황을 받을 콜백. 지정하지 않으면 터미널에만 출력한다.
    on_point: 제어 중 측정한 (duty, 압력)을 받을 콜백. 실시간 그래프 표시에 쓴다.
    '''
    def notify(message):
        if progress:
            progress(message)
        else:
            print(message)

    def notify_point(duty_value, pressure):
        if on_point:
            on_point(duty_value, pressure)

    # 테스트 모드
    if test:
        return (duty_max, True, target)
    # 현재 압력 값 측정 및 초기값 세팅
    current = abs(sensor_and_controller.pressure_read(0.1, test=test))
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
    failure_threshold = 20

    # 종료 측정 조건
    final_measure_time = 5

    # PID 컨트롤러 생성
    pid = PID(1, 0, 0, setpoint=target)
    pid.auto_mode = True
    pid.output_limits = (-control_limit, control_limit)

    while True:
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
        sensor_and_controller.duty_set(duty_real, test=False)
        # 압력 변화를 기다리는 동안(delay) 압력을 짧은 주기로 읽어 실시간 위치를 갱신한다.
        # (기존엔 delay 만큼 통째로 sleep 해서 그래프가 delay 마다 한 번만 움직였다)
        deadline = time.time() + delay
        while time.time() < deadline:
            live = abs(sensor_and_controller.pressure_read(0.1, test=test))
            notify_point(duty_real, live)
        # 압력 값 측정
        current = abs(sensor_and_controller.pressure_read(average_time, test=test))
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
            current = abs(sensor_and_controller.pressure_read(final_measure_time, test=test))
            notify(f"목표 압력 {target} Pa 도달 (측정값 {current:.1f} Pa)")
            # 실제 duty값으로 변환 후 반환
            duty_real = duty_transformation(duty, duty_min, duty_max)
            return (duty_real, True, current)

        # duty 100으로 설정해도 목표 압력에 도달하지 못하는 경우
        if duty == 100 and error_pressure > failure_threshold:
            notify(f"팬을 최대로 돌려도 목표 {target} Pa에 못 미칩니다 "
                   f"(현재 {current:.1f} Pa) — 누기량이 많거나 개구부가 열려 있는지 확인하세요")
            failure_time += time_diff
        elif duty == 0 and error_pressure > failure_threshold:
            notify(f"팬을 멈춰도 압력이 목표 {target} Pa를 넘습니다 "
                   f"(현재 {current:.1f} Pa) — 외풍이나 센서 상태를 확인하세요")
            failure_time += time_diff
        else:
            failure_time = 0

        if failure_time >= duration:
            current = abs(sensor_and_controller.pressure_read(final_measure_time, test=test))
            notify(f"목표 압력 조절 실패 (최종 {current:.1f} Pa)")
            # 실제 duty값으로 변환 후 반환
            duty_real = duty_transformation(duty, duty_min, duty_max)
            return (duty_real, False, current)
