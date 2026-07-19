"""PWM-압력 PID 제어.

reversible fan 의 duty 를 PID 로 조절해 목표 압력에 도달시킨다.
센서 입력·팬 출력은 bdt.hardware 를 통해 수행한다.
"""

import time

from simple_pid import PID

from bdt import hardware

# 압력 표시·밴드 판정에 쓰는 이동평균 창 크기 (0.1초 간격 → 약 1초 평활).
# TargetingPage 도 이 값을 참조해 화면과 판정이 같은 창을 쓰게 한다.
SMOOTH_WINDOW = 10


def duty_transformation(input_value, min_value, max_value):
    """PID 의 duty(0~100)를 팬이 실제로 받는 duty 로 옮긴다.

    PID 는 0~100 을 다루지만 팬에는 가용 구간이 따로 있다. 그 구간의 양 끝을
    (min_value, max_value) 로 받아 선형으로 눌러 넣는다.

    **min_value > max_value 인 역방향 매핑은 지금 쓰이지 않지만 의도적으로
    남겨둔 것이다.** 리버서블 팬(구 OF-OD172SAP-Reversible) 시절, 한 PWM 선의
    duty 구간으로 회전 방향까지 인코딩하는 컨트롤러를 쓸 때 필요했다
    (가압 10~45% = 정방향이라 duty 가 커질수록 값이 작아진다). 현재 팬
    (9GV2048P0G201)은 비리버서블이라 fan_coefficients.json 의 duty_range 가
    전부 [20, 100] 이고, 방향은 팬을 물리적으로 뒤집어 만든다 — 그래서 이
    분기는 도달하지 않는다. 리버서블 팬으로 돌아갈 여지를 두려고 유지하므로
    '안 쓰는 코드'로 보고 지우지 말 것.

    같은 이유로 fan_coefficients.json 의 forward/reverse 계수도 현재 값이
    서로 같다 (방향 구분이 무의미해진 상태).
    """
    # 입력 값이 최소와 최대 값 사이에 있는지 확인
    if not 0 <= input_value <= 100:
        raise ValueError("Input value should be between 0 and 100")

    # 변환 함수
    if min_value > max_value:
        # 역방향 매핑 (리버서블 팬 전용, 현재 미사용 — 위 독스트링 참고).
        # 예: (45, 10) → PID 0~100 이 실제 45~10 으로 내려간다.
        min_value, max_value = max_value, min_value
        transformed_value = (1 - input_value / 100) * (max_value - min_value) + min_value

    else:
        # 정방향 매핑 (현재 경로). 예: (20, 100) → PID 0~100 이 실제 20~100.
        transformed_value = (input_value / 100) * (max_value - min_value) + min_value

    return round(transformed_value)

def get_duty(target, delay, average_time, control_limit, duty_min=0, duty_max=100, test=True,
             progress=None, on_point=None, check_cancelled=None,
             tolerance_percent=10.0, hold_seconds=10.0, on_hold=None,
             smooth_window=SMOOTH_WINDOW):
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
    tolerance_percent: 수렴 허용 오차(목표 대비 %). 예전엔 target/10 으로 코드에
        박혀 있었다 — 목표를 바꿔도 비율은 못 바꿨다.
    hold_seconds: 허용 오차 안에 이만큼 연속으로 머물러야 수렴. 실패 판정에도
        같은 시간을 쓴다.
    on_hold: (종류, 경과초, 목표초) 콜백. 종류는 "converge" 또는 "fail".
        화면이 유지 구간을 색칠하고 카운트를 보여주는 데 쓴다.
        조건이 깨지면 경과초 0 으로 알린다.
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

    def notify_hold(kind, elapsed):
        if on_hold:
            on_hold(kind, elapsed, hold_seconds)

    # 테스트 모드
    if test:
        return (duty_max, True, target, None)
    # 현재 압력 값 측정 및 초기값 세팅
    current = abs(hardware.pressure_read(0.1, test=test))
    duty = 0

    # 압력 이동평균 — 표시선과 밴드 판정을 같은 매끄러운 값으로 맞춘다.
    # 0.1초마다 읽는 원시 압력은 바람·센서 노이즈로 들쭉날쭉해, 그대로 판정하면
    # 한 번 튄 값에 카운트가 리셋된다. 최근 N 점 평균으로 판정하면 단발 스파이크에
    # 흔들리지 않으면서도 '연속 유지'는 그대로 요구한다 (유령값은 CRC 가 이미
    # 걸러 여기 안 온다). 화면에도 이 평균값을 보내 선과 판정이 어긋나지 않는다.
    n_smooth = max(1, int(smooth_window))
    pressure_window = []

    def smooth(value):
        pressure_window.append(value)
        if len(pressure_window) > n_smooth:
            pressure_window.pop(0)
        return sum(pressure_window) / len(pressure_window)

    # 압력 수렴 조건
    convergence_time = 0
    pressure_threshold = target * tolerance_percent / 100.0
    duration = hold_seconds

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
        # PID 계산
        control = pid(current)
        # duty 업데이트 및 상하한 설정
        duty += control
        duty = round(duty)
        duty = max(0, min(100, duty))
        # PID 제어용 duty에서 실제 duty값으로 변경
        duty_real = duty_transformation(duty, duty_min, duty_max)
        # duty 값 적용 (여기까지 오면 test 는 항상 False — 위의 테스트 모드
        # 조기 반환 때문 — 이지만, False 를 박아두면 조기 반환을 손대는 순간
        # 개발 PC 에서 실제 PWM 을 건드리는 코드가 된다)
        hardware.duty_set(duty_real, test=test)
        # 압력이 자리 잡길 기다리는 동안(delay) 짧은 주기로 읽는다.
        #
        # **이 값들로 유지 시간을 센다.** 예전엔 delay 가 끝난 뒤 스냅샷 하나로만
        # 판정해서, 5초 사이 압력이 밴드를 들락거려도 카운트가 그대로 쌓였다.
        # 루프 한 바퀴가 5.5초쯤이라 "10초 유지"가 사실은 스냅샷 두 개였다 —
        # 그 사이 무슨 일이 있었는지는 아무도 안 봤다. 판정 기준(밴드)은 화면에
        # 그리는 것과 같은 pressure_threshold 다.
        deadline = time.time() + delay
        last_tick = time.time()
        while time.time() < deadline:
            cancel_check()
            # 원시값을 이동평균으로 매끄럽게 한 뒤, 그 값을 그리고 그 값으로
            # 밴드를 판정한다 (선 = 판정 기준).
            live = smooth(abs(hardware.pressure_read(0.1, test=test)))
            notify_point(duty_real, live)

            now = time.time()
            dt = now - last_tick
            last_tick = now
            in_band = abs(target - live) < pressure_threshold

            if in_band:
                convergence_time += dt
                notify_hold("converge", convergence_time)
            elif convergence_time:
                # 밴드를 벗어나는 순간 리셋한다 — '연속으로' 머물러야 수렴이다
                convergence_time = 0
                notify_hold("converge", 0)

            # 팬이 한계에 붙은 채 밴드 밖이면 실패를 센다 (같은 시간 기준)
            if duty in (0, 100) and not in_band:
                failure_time += dt
                notify_hold("fail", failure_time)
            elif failure_time:
                failure_time = 0
                notify_hold("fail", 0)

            if convergence_time >= duration or failure_time >= duration:
                break  # 판정이 섰다 — 남은 대기는 의미가 없다

        # 압력 값 측정 (PID 입력) — PID 에는 원시값을 준다 (제어는 지연 없이
        # 실제 압력을 봐야 한다). 밴드 판정은 위 대기 루프의 이동평균이 이미 했다.
        current = abs(hardware.pressure_read(average_time, test=test))
        # 압력 오차
        error_pressure = abs(target - current)
        # 이 측정점도 이동평균에 넣어 그린다 (표시선이 튀지 않게)
        notify_point(duty_real, smooth(current))

        # 유지 시간은 위 대기 루프가 실시간으로 셌다 — 여기서 또 더하면
        # 같은 시간을 두 번 세게 된다. 여기서는 상황만 알린다.
        if error_pressure < pressure_threshold:
            notify(f"팬 세기 {duty_real}% — 압력 {current:.1f} / 목표 {target} Pa "
                   f"· 안정화 중 ({convergence_time:.0f}/{duration:.0f}초)")
        else:
            notify(f"팬 세기 {duty_real}% — 압력 {current:.1f} / 목표 {target} Pa "
                   f"· 조절 중 (오차 {error_pressure:.1f} Pa)")

        if convergence_time >= duration:
            current = abs(hardware.pressure_read(final_measure_time, test=test))
            notify(f"목표 압력 {target} Pa 도달 (측정값 {current:.1f} Pa)")
            # 실제 duty값으로 변환 후 반환
            duty_real = duty_transformation(duty, duty_min, duty_max)
            return (duty_real, True, current, None)

        # duty 가 한계에 붙었는데 수렴 문턱(pressure_threshold)을 넘는 오차가
        # 남아 있으면 실패다. 예전엔 실패 문턱이 20 Pa 로 따로 있어서 오차가
        # 7~20 Pa 인 채 duty 100 에 포화되면 수렴도 실패도 아닌 데드존에 갇혀
        # 영영 반환하지 않았다. (카운트도 위 대기 루프가 실시간으로 센다)
        if duty == 100 and error_pressure >= pressure_threshold:
            notify(f"팬 세기를 최대로 높여도 목표 {target} Pa에 못 미칩니다 "
                   f"(현재 {current:.1f} Pa) — 누기량이 많거나 개구부가 열려 있는지 "
                   f"확인하세요 ({failure_time:.0f}/{duration:.0f}초)")
        elif duty == 0 and error_pressure >= pressure_threshold:
            # PID duty 0 은 팬 정지가 아니라 duty_min(팬이 도는 최소 세기)이다.
            # 예전엔 '팬을 멈춰도'라고 알려서, 실제로는 팬이 최소로 돌고 있는데
            # 작업자가 센서·외풍 문제로 오진하게 만들었다.
            notify(f"팬 세기를 최소({duty_min}%)로 낮춰도 압력이 목표 {target} Pa를 "
                   f"넘습니다 (현재 {current:.1f} Pa) — 외풍이나 센서 상태를 "
                   f"확인하세요 ({failure_time:.0f}/{duration:.0f}초)")

        if failure_time >= duration:
            current = abs(hardware.pressure_read(final_measure_time, test=test))
            notify(f"목표 압력 조절 실패 (최종 {current:.1f} Pa)")
            # 실제 duty값으로 변환 후 반환.
            # saturated 는 어느 한계에 붙어 실패했는지다 — 팬 최대인데 목표에
            # 못 미친 경우와, 팬 최소인데도 목표를 넘긴 경우는 뒤처리가 정반대라
            # 호출부가 구분할 수 있어야 한다.
            duty_real = duty_transformation(duty, duty_min, duty_max)
            saturated = "max" if duty == 100 else "min"
            return (duty_real, False, current, saturated)
