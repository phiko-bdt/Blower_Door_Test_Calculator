"""리소스·산출물 절대경로 규약.

앱은 바탕화면 아이콘(.desktop)으로 실행되므로 작업 디렉터리를 신뢰할 수 없다.
모든 파일 접근은 이 모듈의 상수를 통해 저장소 루트 기준 절대경로로 수행한다.
"""

import os

# bdt 패키지의 부모 = 저장소 루트
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 리소스 ──────────────────────────────────────────────
FONT_PATH = os.path.join(ROOT, "NanumSquare_acL.ttf")
# (앱 아이콘 경로는 BlowerDoorTest.desktop 이 자체로 갖는다 — 여기엔 없다)

# ── 설정·측정 원본(JSON) ────────────────────────────────
CONDITIONS_JSON = os.path.join(ROOT, "conditions.json")
FAN_COEFFICIENTS_JSON = os.path.join(ROOT, "fan_coefficients.json")
DEPRESSURIZATION_RAW_JSON = os.path.join(ROOT, "depressurization_raw.json")
PRESSURIZATION_RAW_JSON = os.path.join(ROOT, "pressurization_raw.json")
CALCULATION_RAW_JSON = os.path.join(ROOT, "calculation_raw.json")

# ── 최신 산출물(루트에 덮어쓰기) ─────────────────────────
GRAPH_PNG = os.path.join(ROOT, "graph.png")
REPORT_PDF = os.path.join(ROOT, "report.pdf")
# 성적서를 앱 안에서 보여주려고 PDF 를 이미지로 렌더한 것 (pdftoppm).
# 발행물이 아니라 화면 표시용 캐시라 시험마다 덮어쓴다.
REPORT_PNG = os.path.join(ROOT, "report_page.png")

# ── 이력 보관 디렉터리 ──────────────────────────────────
# 성적서 보관함 — 바탕화면의 '결과보고서' 폴더.
# report.pdf 는 시험마다 덮어써지므로 발행한 성적서는 여기에 사본으로 남긴다.
# 작업자가 파일 관리자를 몰라도 바탕화면에서 바로 찾을 수 있어야 한다.
DESKTOP_DIR = os.path.join(os.path.expanduser("~"), "Desktop")
REPORT_ARCHIVE_DIR = os.path.join(DESKTOP_DIR, "결과보고서")

# USB 저장소 자동 마운트 위치. 라즈베리파이 데스크톱(udisks2)은 꽂힌 USB 를
# /media/<사용자>/<라벨> 로 올린다. 사용자 이름은 홈 디렉터리에서 끌어온다
# (DESKTOP_DIR 과 같은 소스).
MEDIA_DIR = os.path.join("/media", os.path.basename(os.path.expanduser("~")))


def usb_mounts():
    """마운트된 USB 저장소 경로 목록. 없으면 빈 리스트.

    /media/<사용자>/ 아래에서 실제 마운트포인트인 항목만 고른다 (빈 폴더나
    마운트 해제된 잔여 디렉터리는 제외). 성적서 화면이 이걸로 'USB로 복사'
    버튼을 띄울지 정한다.
    """
    # isdir 확인과 listdir 사이에 디렉터리가 사라질 수 있다(USB 탈거 등).
    # 이 함수는 성적서 화면의 2초 폴링 슬롯에서 돌므로, 예외가 새면 앱이
    # 통째로 죽는다 — 빈 목록 폴백이 맞다.
    try:
        names = sorted(os.listdir(MEDIA_DIR))
    except OSError:
        return []
    found = []
    for name in names:
        path = os.path.join(MEDIA_DIR, name)
        try:
            if os.path.ismount(path):
                found.append(path)
        except OSError:
            continue
    return found


def report_archive_path(when, tests, volume):
    """발행한 성적서를 남길 경로.

    결과보고서/<연월일시>/<연월일시분>_<시험 종류>_<체적>㎥.pdf
    예: 결과보고서/2026071719/202607171908_감압_424.21㎥.pdf

    시(時) 단위로 폴더를 나눈다 — 하루에 여러 현장을 도는 운용이라 날짜만으로
    묶으면 한 폴더에 뒤섞이고, 분 단위로 나누면 폴더가 파일만큼 생긴다.
    """
    folder = os.path.join(REPORT_ARCHIVE_DIR, when.strftime("%Y%m%d%H"))
    volume = _safe_name(str(volume).strip()) or "체적미상"
    name = f"{when.strftime('%Y%m%d%H%M')}_{_safe_name(tests)}_{volume}㎥.pdf"
    return os.path.join(folder, name)


def _safe_name(text):
    """파일명에 쓸 수 없는 문자를 없앤다 (경로 구분자·제어문자)."""
    return "".join(c for c in text if c not in '/\\:*?"<>|' and c.isprintable())


CONDITIONS_DIR = os.path.join(ROOT, "conditions")
MEASUREMENTS_DIR = os.path.join(ROOT, "measurements")
CALCULATIONS_DIR = os.path.join(ROOT, "calculations")
GRAPHS_DIR = os.path.join(ROOT, "graphs")
REPORTS_DIR = os.path.join(ROOT, "reports")


def raw_json(test):
    """시험 종류("depressurization"/"pressurization")별 raw 파일 경로."""
    return os.path.join(ROOT, f"{test}_raw.json")


def ensure_dir(path):
    """이력 디렉터리를 만들고 그 경로를 그대로 반환한다."""
    os.makedirs(path, exist_ok=True)
    return path
