"""센서 입력·팬 PWM 출력 하드웨어 제어.

라즈베리파이5의 하드웨어 PWM(RP1, sysfs)과 시리얼 압력 센서를 다룬다.

**pigpio 를 쓰지 않는다.** pigpio 는 BCM2711 주변장치 레지스터를 /dev/mem 으로
직접 두드리는데, 파이5는 GPIO 를 RP1 칩이 PCIe 너머에서 담당해 구조적으로
동작하지 않는다("unknown rev code (c04171)" → "not a raspberry pi"). 대신 커널이
노출하는 sysfs PWM(/sys/class/pwm)으로 같은 하드웨어 PWM 을 쓴다.

sysfs PWM 설정은 프로세스가 끝나도 커널에 남으므로(= 팬이 계속 돈다), 앱 종료 시
atexit 훅이 duty 0% 를 보장한다.
"""

import atexit
import os
import struct
import subprocess
import time

import crcmod
import serial


# 팬 PWM 출력 핀.
# 교체 이력: GPIO18(물리핀 12) → GPIO12(물리핀 32) → GPIO13(물리핀 33)
# 앞의 두 핀은 모두 LOW 구동 불가(출력 싱크 손상)로 폐기했다. duty 0%를 줘도
# 핀이 2.4V 아래로 내려가지 않아 팬이 항상 100%로 동작했다.
# 원인은 팬 PWM 선 대신 sensor(TACH) 선에 물린 채 팬을 돌린 배선 실수로 보인다
# (TACH 는 12V 로 풀업된 출력이라 3.3V 패드의 싱크측이 탄다). 그래도 같은 실수는
# 또 날 수 있으므로 duty_set() 은 핀 레벨을 되읽어 계속 확인한다.
PWM_GPIO = 13  # 물리핀 33
PWM_FREQUENCY = 1000  # 1kHz
PWM_PERIOD_NS = 1_000_000_000 // PWM_FREQUENCY  # 1kHz → 1,000,000ns

# GPIO12·13 이 붙는 RP1 PWM 컨트롤러의 장치 이름.
# ⚠️ CPU 쿨링팬은 다른 컨트롤러(1f0009c000.pwm)의 채널 3 을 쓴다. 그쪽을 건드리면
# 파이가 냉각을 잃는다. 그리고 /sys/class/pwm/pwmchipN 의 N 은 부팅마다 바뀔 수
# 있으므로 번호가 아니라 반드시 장치 이름으로 찾는다.
PWM_CHIP_DEVICE = "1f00098000.pwm"
PWM_CHANNEL = 1  # GPIO13 = PWM0_CHAN1 (dtoverlay=pwm-2chan 이 매핑)

PWM_SYSFS_ROOT = "/sys/class/pwm"


class SensorTimeout(RuntimeError):
    """압력 센서가 제한 시간 안에 응답하지 않을 때 발생한다."""


class PWMUnavailable(RuntimeError):
    """팬 PWM 하드웨어를 쓸 수 없다 (오버레이 미적용·권한 문제 등)."""


# ── sysfs PWM 준비 (지연 초기화) ────────────────────────────
# 채널 export·주기 설정은 한 번만 하면 되므로 결과를 캐시한다.
_pwm_dir = None


def _find_chip():
    """GPIO13 이 붙은 PWM 컨트롤러 디렉터리를 장치 이름으로 찾는다."""
    if not os.path.isdir(PWM_SYSFS_ROOT):
        raise PWMUnavailable(
            "커널에 PWM 인터페이스(/sys/class/pwm)가 없습니다.")
    for name in sorted(os.listdir(PWM_SYSFS_ROOT)):
        chip = os.path.join(PWM_SYSFS_ROOT, name)
        device = os.path.realpath(os.path.join(chip, "device"))
        if os.path.basename(device) == PWM_CHIP_DEVICE:
            return chip
    raise PWMUnavailable(
        f"팬 PWM 컨트롤러({PWM_CHIP_DEVICE})를 찾지 못했습니다. "
        "/boot/firmware/config.txt 에 "
        "'dtoverlay=pwm-2chan,pin=12,func=4,pin2=13,func2=4' 가 있는지 "
        "확인하고 재부팅하세요.")


def _write(path, value):
    with open(path, "w") as f:
        f.write(str(value))


def _wait_writable(path, timeout=3.0):
    """udev 가 소유권을 gpio 그룹으로 바꿔 쓸 수 있게 될 때까지 기다린다."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.access(path, os.W_OK):
            return
        time.sleep(0.02)
    raise PWMUnavailable(
        f"{path} 에 쓸 수 있게 되기를 {timeout}초 기다렸으나 실패했습니다. "
        "udev 규칙(/etc/udev/rules.d/99-com.rules)과 실행 계정의 "
        "'gpio' 그룹 소속을 확인하세요.")


def _get_pwm():
    """PWM 채널 디렉터리를 반환한다. 처음이면 export·주기 설정까지 한다."""
    global _pwm_dir
    if _pwm_dir is not None and os.path.isdir(_pwm_dir):
        return _pwm_dir

    chip = _find_chip()
    channel_dir = os.path.join(chip, f"pwm{PWM_CHANNEL}")
    duty_path = os.path.join(channel_dir, "duty_cycle")
    try:
        if not os.path.isdir(channel_dir):
            _write(os.path.join(chip, "export"), PWM_CHANNEL)
            # export 하면 커널이 디렉터리를 만들고, **그 뒤에** udev 가 소유권을
            # root:gpio 로 바꿔준다(약 50ms). 디렉터리만 보고 바로 쓰면 아직
            # root:root 라 PermissionError 가 난다. 쓸 수 있을 때까지 기다린다.
            _wait_writable(duty_path)
        # 주기를 먼저 잡아야 duty_cycle 을 그 안의 값으로 쓸 수 있다.
        # duty 를 먼저 0 으로 내려야 주기 변경 중 팬이 튀지 않는다.
        _write(duty_path, 0)
        _write(os.path.join(channel_dir, "period"), PWM_PERIOD_NS)
        _write(os.path.join(channel_dir, "enable"), 1)
    except PermissionError as exc:
        raise PWMUnavailable(
            "PWM sysfs 에 쓸 권한이 없습니다. 실행 계정이 'gpio' 그룹에 "
            f"속해 있는지 확인하세요. ({exc})") from exc
    except OSError as exc:
        raise PWMUnavailable(f"팬 PWM 초기화에 실패했습니다. ({exc})") from exc

    _pwm_dir = channel_dir
    return _pwm_dir


def _shutdown_pwm():
    """종료 시 팬을 반드시 멈춘다 (duty 0%).

    atexit 로 등록되어 앱 종료 시 자동 호출된다. PWM 을 실제로 연 적이 없으면
    (TEST_MODE 등) 아무 것도 하지 않는다.

    enable 은 끄지 않는다. 끄면 핀이 뜨거나 정의되지 않은 상태가 될 수 있어,
    duty 0% 로 LOW 를 계속 능동적으로 물고 있는 편이 안전하다.
    """
    global _pwm_dir
    if _pwm_dir is None:
        return
    try:
        _write(os.path.join(_pwm_dir, "duty_cycle"), 0)
    except OSError:
        pass
    finally:
        _pwm_dir = None


atexit.register(_shutdown_pwm)


# 압력 센서 Modbus 프레임 규격 (Lefoo, 홀딩 레지스터 1개 읽기)
SENSOR_ADDRESS = 0x01   # 슬레이브 주소
SENSOR_FUNCTION = 0x03  # read holding registers
SENSOR_BYTE_COUNT = 0x02
RESPONSE_SIZE = 7       # 주소 1 + 기능 1 + 바이트수 1 + 값 2 + CRC 2


# CRC 함수는 모듈 수준에서 한 번만 만든다. 호출마다 Crc 객체를 만들면
# 256 엔트리 테이블을 매번 재생성한다 (Pi5 실측 257µs vs 0.24µs — 1000배).
# 수신 프레임마다 검증하는 핫 패스라 차이가 누적된다.
_modbus_crc16 = crcmod.predefined.mkPredefinedCrcFun('modbus')


def _modbus_crc(payload):
    """Modbus RTU CRC16 값을 계산한다."""
    return _modbus_crc16(payload)


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
    # 시리얼 연결. 포트 소멸(USB 뽑힘)은 SerialException 인데, 호출부들은
    # SensorTimeout 만 잡도록 계약돼 있다 — 변환하지 않으면 100ms GUI 타이머
    # 슬롯에서 미처리 예외로 앱이 통째로 죽는다.
    try:
        ser = serial.Serial(port=port,
                            baudrate=baudrate,
                            timeout=1)
    except (serial.SerialException, OSError) as exc:
        raise SensorTimeout(
            f"압력 센서 포트({port})를 열 수 없습니다. "
            f"USB 연결을 확인하세요. ({exc})") from exc
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
            # (루프 안의 시리얼 I/O 도중 포트가 사라질 수 있다 — 아래 except)
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
    except (serial.SerialException, OSError) as exc:
        raise SensorTimeout(
            f"압력 센서({port}) 통신 중 연결이 끊어졌습니다. "
            f"USB 연결을 확인하세요. ({exc})") from exc
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
    # (OverflowError: inf·1e400 류 — 손상된 보정 파일의 duty_range 가 만들 수 있다)
    try:
        duty_value = int(float(str(duty).strip()))
    except (ValueError, TypeError, OverflowError):
        print("입력 값 오류로 duty를 0으로 설정합니다.")
        duty_value = 0
    # 허용 범위(0~100)를 벗어나면 잘라낸다.
    duty_value = max(0, min(100, duty_value))

    # sysfs 하드웨어 PWM (지연 초기화 후 재사용)
    channel_dir = _get_pwm()

    # duty_cycle 은 주기(ns) 기준의 ON 시간이다.
    # 주기가 1,000,000ns 이므로 1% = 10,000ns.
    duty_ns = duty_value * (PWM_PERIOD_NS // 100)
    _write(os.path.join(channel_dir, "duty_cycle"), duty_ns)

    healthy = _verify_pin_level(duty_value)

    return 0 if healthy else -1


def duty_is_zero(test=True):
    """현재 PWM duty 가 0 인지 sysfs 에서 읽는다. 판단이 안 서면 None.

    fan_guard 가 유휴 상태(앱 없음, 대부분의 시간)에서 1초마다
    duty_set(0) → 핀 검증(pinctrl 서브프로세스 5회) 을 반복하지 않도록,
    이미 0 이면 쓰기를 건너뛰는 용도. None 이면 호출부가 안전한 쪽
    (duty 0 쓰기)을 택한다.
    """
    if test:
        return True
    try:
        channel_dir = _get_pwm()
        with open(os.path.join(channel_dir, "duty_cycle")) as f:
            return int(f.read().strip()) == 0
    except (OSError, ValueError, PWMUnavailable):
        return None


def _read_pin_level():
    """GPIO13 의 현재 레벨을 읽는다 (1=HIGH, 0=LOW, None=읽기 실패).

    핀이 PWM 기능(Alt0)에 물려 있어 일반 GPIO 읽기로는 잡히지 않는다.
    파이5의 `pinctrl` 은 Alt 모드에서도 실제 핀 레벨을 보여준다.
    (파이4 의 raspi-gpio 는 파이5 에서 동작하지 않는다.)
    출력 예: `13: a0    pd | lo // GPIO13 = PWM0_CHAN1`
    """
    try:
        out = subprocess.run(["pinctrl", "get", str(PWM_GPIO)],
                             capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    head = out.split("//")[0]
    if "| hi" in head:
        return 1
    if "| lo" in head:
        return 0
    return None


def _verify_pin_level(duty_value):
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
    levels = [_read_pin_level() for _ in range(5)]
    if all(level == expected for level in levels):
        return True
    if all(level is None for level in levels):
        # 레벨을 못 읽는 것과 핀이 망가진 것은 다르다. 검증을 못 했다고 해서
        # 정상 동작을 막지는 않되, 안전 검사가 꺼졌음은 반드시 알린다.
        print(f"경고: pinctrl 로 GPIO{PWM_GPIO} 레벨을 읽지 못해 핀 손상 검사를 "
              "건너뜁니다. 팬이 실제로 멈췄는지 직접 확인하세요.")
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
