"""리소스·산출물 절대경로 규약.

앱은 바탕화면 아이콘(.desktop)으로 실행되므로 작업 디렉터리를 신뢰할 수 없다.
모든 파일 접근은 이 모듈의 상수를 통해 저장소 루트 기준 절대경로로 수행한다.
"""

import os

# bdt 패키지의 부모 = 저장소 루트
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 리소스 ──────────────────────────────────────────────
FONT_PATH = os.path.join(ROOT, "NanumSquare_acL.ttf")
ICON_PATH = os.path.join(ROOT, "icon.png")

# ── 설정·측정 원본(JSON) ────────────────────────────────
CONDITIONS_JSON = os.path.join(ROOT, "conditions.json")
FAN_COEFFICIENTS_JSON = os.path.join(ROOT, "fan_coefficients.json")
DEPRESSURIZATION_RAW_JSON = os.path.join(ROOT, "depressurization_raw.json")
PRESSURIZATION_RAW_JSON = os.path.join(ROOT, "pressurization_raw.json")
CALCULATION_RAW_JSON = os.path.join(ROOT, "calculation_raw.json")

# ── 최신 산출물(루트에 덮어쓰기) ─────────────────────────
GRAPH_PNG = os.path.join(ROOT, "graph.png")
REPORT_PDF = os.path.join(ROOT, "report.pdf")

# ── 이력 보관 디렉터리 ──────────────────────────────────
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
