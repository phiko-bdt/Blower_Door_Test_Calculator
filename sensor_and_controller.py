import serial
import crcmod
import struct
import time
import pigpio


# 팬 PWM 출력 핀.
# 교체 이력: GPIO18(물리핀 12) → GPIO12(물리핀 32) → GPIO13(물리핀 33)
# 앞의 두 핀은 모두 LOW 구동 불가(출력 싱크 손상)로 폐기했다. duty 0%를 줘도
# 핀이 2.4V 아래로 내려가지 않아 팬이 항상 100%로 동작했다.
# 두 번 연속 같은 방식으로 손상된 원인이 아직 규명되지 않았으므로 이 핀도
# 같은 식으로 죽을 수 있다. duty_set() 후 핀 레벨을 되읽어 확인할 것.
PWM_GPIO = 13  # 하드웨어 PWM1 (물리핀 33)
PWM_FREQUENCY = 1000  # 1kHz


class SensorTimeout(RuntimeError):
    """압력 센서가 제한 시간 안에 응답하지 않을 때 발생한다."""


def temperature_and_humidity(port='/dev/ttyUSB1', baudrate=9600):
    # 시리얼 연결
    ser = serial.Serial(port=port,
                        baudrate=baudrate,
                        timeout=1)
    return ser


def pressure_read(average_time=0.1, port='/dev/ttyUSB0', baudrate=9600, test=True):
    # 테스트 모드
    if test:
        import random
        return random.randrange(0, 100)
    # 시리얼 연결
    ser = serial.Serial(port=port,
                        baudrate=baudrate,
                        timeout=1)
    # 측정 시작 시간
    time_start = time.time()
    # 평균 값을 위한 변수 선언
    average = []
    # 데이터 요청 값
    data = b'\x01\x03\x00\x01\x00\x01'
    # 모드버스 통신을 위한 CRC 계산
    crc16 = crcmod.predefined.Crc('modbus')
    crc16.update(data)
    crc_bytes = crc16.digest()
    crc_bytes_reversed = crc_bytes[::-1]
    # 데이터 요청 값 + CRC
    data += crc_bytes_reversed
    # 센서가 응답하지 않으면 average 가 비어 있어 종료 조건을 영영 만족하지 못한다.
    # 무한 대기로 GUI 가 멈추지 않도록 상한을 둔다.
    deadline = time_start + max(average_time * 3, 5)

    # 반복 측정
    try:
        while True:
            # 데이터 송신
            ser.write(data)
            # 데이터 수신
            response = ser.read(7)
            try:
                # 데이터 분해
                _, _, _, value, _ = struct.unpack('>BBBhH', response)
                # 데이터 축적
                average.append(value)
            except struct.error:
                pass

            # 데이터 평균값 계산
            if time.time() - time_start >= average_time and len(average):
                average_pressure = sum(average) / len(average)
                # 소수점 1자리까지 값을 반환하는 Lefoo 압력 센서이므로
                # 결과값을 10으로 나눈 값으로 반환
                return average_pressure/10

            if time.time() >= deadline:
                raise SensorTimeout(
                    f"압력 센서({port})가 응답하지 않습니다. "
                    "센서 연결과 전원을 확인하세요.")
    finally:
        ser.close()

def duty_set(duty, test=True):
    """팬 PWM duty(0~100%)를 설정한다.

    반환값: 정상이면 0, 핀 손상이 의심되면 -1.
    duty 0%는 팬 정지를 의미하므로, 설정 후 핀이 실제로 LOW인지 되읽어 확인한다.
    (PWM_GPIO 주석 참고: 과거 두 핀이 LOW 구동 불가로 죽어 팬이 계속 100%로 돌았다.)
    """
    # 테스트 모드
    if test:
        return 0

    # 입력 값을 정수(0~100)로 검증/정규화한다.
    # 숫자로 해석할 수 없는 값은 안전을 위해 0(팬 정지)으로 처리한다.
    try:
        duty_value = int(float(str(duty).strip()))
    except (ValueError, TypeError):
        print("입력 값 오류로 duty를 0으로 설정합니다.")
        duty_value = 0
    # 허용 범위(0~100)를 벗어나면 잘라낸다.
    duty_value = max(0, min(100, duty_value))

    # Connect to pigpio
    pi = pigpio.pi()

    # Set the hardware PWM
    # The range of duty cycle is from 0 to 1,000,000 (representing 0% to 100%)
    duty_cycle = duty_value * 10_000

    # Initialize the PWM on the specified pin
    pi.hardware_PWM(PWM_GPIO, PWM_FREQUENCY, duty_cycle)

    healthy = _verify_pin_level(pi, duty_value)

    # Disconnect from pigpio
    pi.stop()
    return 0 if healthy else -1


def _verify_pin_level(pi, duty_value):
    """duty 0%/100%는 핀 레벨이 고정되므로 되읽어 손상 여부를 확인한다.

    그 사이 duty는 PWM이 토글 중이라 단발 read로 판별할 수 없어 검사하지 않는다.
    """
    if duty_value == 0:
        expected, name = 0, "LOW"
    elif duty_value == 100:
        expected, name = 1, "HIGH"
    else:
        return True

    time.sleep(0.05)
    levels = [pi.read(PWM_GPIO) for _ in range(5)]
    if all(level == expected for level in levels):
        return True

    print(f"경고: duty {duty_value}% 설정 후에도 GPIO{PWM_GPIO}(물리핀 33)가 "
          f"{name}로 내려가지 않습니다 (레벨 {levels}). 핀 손상이 의심됩니다.")
    if duty_value == 0:
        print("      팬이 계속 100%로 회전할 수 있으니 전원을 수동으로 차단하세요.")
    return False


def fan_power(set=1):
    # Connect to pigpio
    pi = pigpio.pi()
    
    # Define the GPIO pin for power relay for the Fan
    gpio_pin = 23
    # To set the relay
    pi.write(gpio_pin, set)

    # Disconnect from pigpio
    pi.stop()
    return 0


if __name__ == '__main__':
    print(pressure_read(test=False))
    duty_input=int(input("duty: "))
    duty_set(duty_input, test=False)
