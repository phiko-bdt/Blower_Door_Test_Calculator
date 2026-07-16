"""센서 입력·팬 PWM 출력 하드웨어 제어.

라즈베리파이4의 pigpio(하드웨어 PWM)와 시리얼 압력 센서를 다룬다.

pigpio 연결은 호출마다 새로 만들지 않고 모듈 수준에서 한 번만 열어 재사용한다
(`_get_pi()`의 지연 초기화 싱글턴). 앱 종료 시 atexit 훅이 duty 0%를 보장한 뒤
연결을 정리한다.
"""

import atexit
import struct
import time

import crcmod
import pigpio
import serial


# 팬 PWM 출력 핀.
# 교체 이력: GPIO18(물리핀 12) → GPIO12(물리핀 32) → GPIO13(물리핀 33)
# 앞의 두 핀은 모두 LOW 구동 불가(출력 싱크 손상)로 폐기했다. duty 0%를 줘도
# 핀이 2.4V 아래로 내려가지 않아 팬이 항상 100%로 동작했다.
# 두 번 연속 같은 방식으로 손상된 원인이 아직 규명되지 않았으므로 이 핀도
# 같은 식으로 죽을 수 있다. duty_set() 후 핀 레벨을 되읽어 확인할 것.
PWM_GPIO = 13  # 하드웨어 PWM1 (물리핀 33)
PWM_FREQUENCY = 1000  # 1kHz

# 팬 전원은 수동 공급이라 릴레이(GPIO23)는 실사용하지 않는다.
# 제어 코드는 쓰이지 않은 채 남아 있어 삭제했다 (필요해지면 git 이력 참고).


class SensorTimeout(RuntimeError):
    """압력 센서가 제한 시간 안에 응답하지 않을 때 발생한다."""


# ── pigpio 연결 재사용 ──────────────────────────────────────
# 호출마다 pigpio.pi()/stop() 을 반복하면 데몬 소켓을 계속 여닫아 비효율적이고,
# 종료 타이밍에 따라 팬이 도는 상태로 남을 위험이 있다. 지연 초기화 싱글턴으로
# 연결을 한 번만 열어 재사용하고, atexit 에서 duty 0% + stop() 을 보장한다.
_pi = None


def _get_pi():
    """공유 pigpio 연결을 반환한다. 없으면 지연 생성한다.

    연결이 끊겼으면(데몬 재시작 등) 다시 연결을 시도한다.
    """
    global _pi
    if _pi is None or not _pi.connected:
        _pi = pigpio.pi()
        if not _pi.connected:
            raise RuntimeError(
                "pigpio 데몬에 연결하지 못했습니다. 'sudo pigpiod' 로 "
                "pigpiod 가 실행 중인지 확인하세요.")
    return _pi


def _shutdown_pi():
    """종료 시 팬을 반드시 멈추고(duty 0%) pigpio 연결을 정리한다.

    atexit 로 등록되어 앱 종료 시 자동 호출된다. 연결을 실제로 연 적이 없으면
    (TEST_MODE 등) 아무 것도 하지 않는다.
    """
    global _pi
    if _pi is None:
        return
    try:
        if _pi.connected:
            # 종료 직전 팬 정지 보장.
            _pi.hardware_PWM(PWM_GPIO, PWM_FREQUENCY, 0)
    finally:
        if _pi.connected:
            _pi.stop()
        _pi = None


atexit.register(_shutdown_pi)


# 압력 센서 Modbus 프레임 규격 (Lefoo, 홀딩 레지스터 1개 읽기)
SENSOR_ADDRESS = 0x01   # 슬레이브 주소
SENSOR_FUNCTION = 0x03  # read holding registers
SENSOR_BYTE_COUNT = 0x02
RESPONSE_SIZE = 7       # 주소 1 + 기능 1 + 바이트수 1 + 값 2 + CRC 2


def _modbus_crc(payload):
    """Modbus RTU CRC16 값을 계산한다."""
    crc = crcmod.predefined.Crc('modbus')
    crc.update(payload)
    return crc.crcValue


def _parse_pressure_frame(response):
    """응답 프레임을 검증하고 원시 측정값을 돌려준다. 못 믿을 프레임이면 None.

    예전에는 CRC 를 언팩만 하고 버려서, 프레임이 어긋나 읽힌 쓰레기 7바이트도
    struct.unpack 만 성공하면 그대로 평균에 섞였다. 이게 이따금 튀던 값의
    정체다. 아웃라이어를 사후에 걸러내는 대신 여기서 원인을 막는다.
    """
    if len(response) != RESPONSE_SIZE:
        return None

    address, function, byte_count, value = struct.unpack('>BBBh', response[:5])
    # CRC 는 전선 위에서 리틀엔디언이라 '<H' 로 읽으면 계산값과 바로 비교된다
    (crc_received,) = struct.unpack('<H', response[5:7])

    if _modbus_crc(response[:5]) != crc_received:
        return None  # 전송 중 깨졌거나 프레임이 어긋났다
    if (address, function, byte_count) != (SENSOR_ADDRESS, SENSOR_FUNCTION,
                                           SENSOR_BYTE_COUNT):
        return None  # 다른 장치·다른 응답 (CRC 가 우연히 맞는 경우까지 차단)
    return value


def pressure_read(average_time=0.1, port='/dev/ttyUSB0', baudrate=9600, test=True):
    """압력을 average_time 동안 반복 측정해 평균(Pa)으로 돌려준다."""
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
    # 모드버스 통신을 위한 CRC (전선 위에서는 리틀엔디언이라 뒤집어 붙인다)
    data += struct.pack('<H', _modbus_crc(data))
    # 센서가 응답하지 않으면 average 가 비어 있어 종료 조건을 영영 만족하지 못한다.
    # 무한 대기로 GUI 가 멈추지 않도록 상한을 둔다.
    deadline = time_start + max(average_time * 3, 5)
    rejected = 0

    # 반복 측정
    try:
        while True:
            # 앞선 응답의 잔여 바이트가 남아 있으면 다음 프레임이 어긋나 읽힌다.
            # 요청 전에 입력 버퍼를 비워 매번 프레임 경계에서 시작한다.
            ser.reset_input_buffer()
            # 데이터 송신
            ser.write(data)
            # 데이터 수신
            response = ser.read(RESPONSE_SIZE)
            value = _parse_pressure_frame(response)
            if value is None:
                rejected += 1
            else:
                # 데이터 축적
                average.append(value)

            # 데이터 평균값 계산
            if time.time() - time_start >= average_time and len(average):
                average_pressure = sum(average) / len(average)
                # 소수점 1자리까지 값을 반환하는 Lefoo 압력 센서이므로
                # 결과값을 10으로 나눈 값으로 반환
                return average_pressure/10

            if time.time() >= deadline:
                # 응답이 아예 없는 것과, 오고는 있는데 전부 깨진 것을 구분해
                # 알린다 (후자는 배선 노이즈·보레이트 불일치를 의심할 일이다).
                if rejected:
                    raise SensorTimeout(
                        f"압력 센서({port}) 응답을 신뢰할 수 없습니다 "
                        f"(깨진 프레임 {rejected}개). 배선 노이즈와 "
                        "통신 속도 설정을 확인하세요.")
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

    # 공유 pigpio 연결 재사용 (호출마다 새로 열지 않는다)
    pi = _get_pi()

    # Set the hardware PWM
    # The range of duty cycle is from 0 to 1,000,000 (representing 0% to 100%)
    duty_cycle = duty_value * 10_000

    # Initialize the PWM on the specified pin
    pi.hardware_PWM(PWM_GPIO, PWM_FREQUENCY, duty_cycle)

    healthy = _verify_pin_level(pi, duty_value)

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


if __name__ == '__main__':
    print(pressure_read(test=False))
    duty_input=int(input("duty: "))
    duty_set(duty_input, test=False)
