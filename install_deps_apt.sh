#!/bin/bash
# 라즈베리파이(Debian bookworm) 의존성 설치 — 검증된 실제 패키지명 목록.
#
# 예전엔 requirements.txt 의 각 줄을 python3-<이름> 으로 파생했는데, 실제
# 데비안 이름과 달라(Pillow→python3-pil, pyserial→python3-serial 등) 첫
# 불일치(Pillow)에서 set -e 로 전체가 중단되고 뒤 패키지는 설치조차 안 됐다.
# 새 머신(교체·2호기) 재현이 깨지는 원인이라 명시 목록으로 바꿨다.
# requirements.txt 는 pip 환경(개발 PC)용 참고로 남긴다.
set -e
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root using sudo" >&2
  exit 1
fi

apt-get update

# ── 파이썬 라이브러리 (앱 실행 필수) ──────────────────────────
apt-get install -y \
  python3-pyqt6 python3-pyqt6.sip python3-pyqt6.qtcharts \
  python3-matplotlib python3-numpy python3-scipy \
  python3-pil python3-serial python3-dateutil \
  python3-crcmod python3-openpyxl python3-six python3-packaging \
  python3-flask python3-segno

# ── 시스템 도구 ──────────────────────────────────────────────
#  chromium: 성적서 HTML→PDF 변환 (bdt/report/html.py)
#  poppler-utils: PDF 렌더·검증 (pdftoppm, pdfinfo)
#  fonts-nanum: 성적서·설명서 한글 폰트 (docs/build_manual.py 포함)
apt-get install -y chromium poppler-utils fonts-nanum

# ── apt 에 없는 패키지 → pip (사용자 사이트) ──────────────────
#  simple-pid: 팬 압력 PID 제어 (bdt/control.py)
REAL_USER="${SUDO_USER:-$(whoami)}"
sudo -u "$REAL_USER" pip3 install --user --break-system-packages simple-pid \
  || echo "경고: simple-pid pip 설치 실패 — 오프라인이면 USB 로 wheel 을 옮겨 설치할 것" >&2

echo "완료. 실행: python3 -m bdt"
