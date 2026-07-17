"""실행 환경 설정.

TEST_MODE: Windows 개발 PC에서는 하드웨어(PWM, 시리얼 센서) 없이
UI·계산 로직만 시험할 수 있도록 True가 된다. 라즈베리파이(Linux)에서는 False.
"""

import platform

TEST_MODE = platform.system() == "Windows"
