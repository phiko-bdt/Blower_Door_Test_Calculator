"""공통 디자인 토큰과 전역 스타일시트.

**이 파일이 앱 전체 색의 단일 소스**다. 화면(PyQt), 성적서 그래프(matplotlib,
report/graph.py), 성적서 HTML(report/html.py)이 모두 여기서 색을 가져가므로
한 곳만 고치면 세 산출물이 함께 움직인다.

디자인 언어는 성적서를 기준으로 삼는다: 회색조 잉크로 정보를 싣고, 포인트
색(accent)은 제목 룰·현재 단계처럼 '지금 어디를 봐야 하는지'에만 아껴 쓴다.
큰 면적을 채도 높은 색으로 칠하지 않는다.

Qt 를 임포트하지 않는 순수 문자열 모듈이라 matplotlib·HTML 쪽에서도 안전하게
가져다 쓸 수 있다.
"""

# ──────────────────────────────────────────────────────────────
# 데이터 계열 색 (감압/가압)
# ──────────────────────────────────────────────────────────────
# CVD(색각이상) 안전이 검증된 blue/orange 조합.
# dataviz 검증기 6개 검사 전부 통과 (surface #fcfcfb, all-pairs):
#   CVD 분리 ΔE 24.7 (protan) · 일반시야 ΔE 33.6 · 명도대/채도/대비 모두 pass
# 색만으로 구분하지 않도록 마커 모양(원/사각)도 함께 다르게 쓴다.
COLOR_DEP = "#2a78d6"      # 감압 (blue)
COLOR_PRE = "#eb6834"      # 가압 (orange)

# ──────────────────────────────────────────────────────────────
# 잉크 (글자)
# ──────────────────────────────────────────────────────────────
COLOR_INK = "#1c2430"      # 본문·제목
COLOR_SUB = "#5b6672"      # 보조 글자
COLOR_MUTED = "#8a94a0"    # 흐린 글자 (단위·주석)

# ──────────────────────────────────────────────────────────────
# 선 (경계·격자)
# ──────────────────────────────────────────────────────────────
COLOR_LINE = "#e4e8ee"     # 카드 테두리·성적서 주 격자
COLOR_LINE2 = "#eef1f5"    # 옅은 구분선
COLOR_GRID_MINOR = "#f1f3f6"  # 성적서(matplotlib) 보조 격자

# 화면 차트의 격자선.
# 성적서 격자(COLOR_LINE)는 300dpi 인쇄에 0.7 선폭으로 얹는 값이라, 같은 색을
# 1280×800 터치스크린에 1px 로 깔면 거의 보이지 않는다(표면 대비 1.20:1).
# 밝은 현장에서 쓰는 화면이므로 한 단계씩 진하게 둔다. 글자색은 매체와
# 무관하므로 성적서와 같은 값(COLOR_SUB·COLOR_INK)을 그대로 쓴다.
COLOR_CHART_GRID = "#ccd3dc"       # 주 격자·축선 (표면 대비 1.47:1)
COLOR_CHART_GRID_SOFT = "#e4e8ee"  # 보조 격자 (표면 대비 1.20:1)
COLOR_CROSSHAIR = "#94a0ae"   # 기준선 (50 Pa)
COLOR_CURSOR = "#b6bfc9"      # 현재 위치 십자 포인터 (기준선보다 연하게)

# ──────────────────────────────────────────────────────────────
# 포인트 (accent) — 아껴 쓴다
# ──────────────────────────────────────────────────────────────
COLOR_ACCENT = "#1f5fa8"
COLOR_ACCENT_DARK = "#1a5190"     # hover
COLOR_ACCENT_PRESSED = "#154578"  # pressed
COLOR_ACCENT_SOFT = "#eef4fb"     # 아주 옅은 포인트 배경

# ──────────────────────────────────────────────────────────────
# 표면
# ──────────────────────────────────────────────────────────────
COLOR_SURFACE = "#ffffff"  # 카드·입력칸
COLOR_PLOT = "#fcfcfb"     # 차트 plot 배경 (팔레트 검증 기준 표면)
COLOR_BG = "#f4f6f9"       # 화면 배경 (성적서에는 없는 화면 전용)

# 규격 표기 — 성적서 헤더와 같은 문구를 화면에서도 쓴다
STANDARD_NAME = "KS L ISO 9972"
STANDARD_NOTE = "팬 가압법 (Fan pressurization method)"

# 화면 기본 크기 (1280×800 터치스크린에 여백을 두고 배치)
WIN_W = 1180
WIN_H = 720

APP_STYLE = f"""
QWidget, QMainWindow {{
    background-color: {COLOR_BG};
    color: {COLOR_INK};
    font-family: 'NanumSquare', 'Noto Sans CJK KR', sans-serif;
}}
QLabel {{
    font-size: 16px;
    background: transparent;
}}
/* 페이지 제목 — 성적서 헤더와 같은 처리(굵은 제목 + accent 하단 룰) */
QLabel#Title {{
    font-size: 26px;
    font-weight: bold;
    color: {COLOR_INK};
}}
QLabel#Subtitle {{
    font-size: 12px;
    color: {COLOR_SUB};
}}
QLabel#Standard {{
    font-size: 14px;
    font-weight: bold;
    color: {COLOR_ACCENT};
}}
QLabel#StandardNote {{
    font-size: 11px;
    color: {COLOR_MUTED};
}}
/* 성적서 헤더의 2.5px accent 룰에 대응 */
QFrame#TitleRule {{
    background-color: {COLOR_ACCENT};
    border: none;
    max-height: 3px;
    min-height: 3px;
}}
/* 섹션 제목 — 성적서의 소형 accent 라벨 + 하도급 룰 */
QLabel#Section {{
    font-size: 12px;
    font-weight: bold;
    color: {COLOR_ACCENT};
}}
QFrame#SectionRule {{
    background-color: {COLOR_LINE2};
    border: none;
    max-height: 1px;
    min-height: 1px;
}}
QLabel#Hint {{
    font-size: 13px;
    color: {COLOR_SUB};
}}
/* 스탯 타일 — 성적서의 KPI 카드와 같은 구성(작은 accent 이름 + 큰 값 + 단위) */
QLabel#StatName {{
    font-size: 11px;
    font-weight: bold;
    color: {COLOR_ACCENT};
}}
QLabel#StatName[state="warn"] {{
    color: #b45309;
}}
QLabel#StatValue {{
    font-size: 34px;
    font-weight: bold;
    color: {COLOR_INK};
}}
QLabel#StatUnit {{
    font-size: 14px;
    font-weight: bold;
    color: {COLOR_SUB};
    padding-bottom: 6px;
}}
QLabel#Message {{
    font-size: 26px;
    font-weight: bold;
    color: {COLOR_INK};
}}
/* 계산 결과 브리핑 — 성적서 상세표와 같은 짜임 */
QLabel#Formula {{
    font-size: 24px;
    font-weight: bold;
    color: {COLOR_ACCENT};
}}
QLabel#SummaryName {{
    font-size: 14px;
    color: {COLOR_SUB};
}}
QLabel#SummaryValue {{
    font-size: 17px;
    font-weight: bold;
    color: {COLOR_INK};
}}
QLabel#SummaryEmphasisName {{
    font-size: 14px;
    font-weight: bold;
    color: {COLOR_ACCENT};
}}
QLabel#SummaryEmphasisValue {{
    font-size: 30px;
    font-weight: bold;
    color: {COLOR_INK};
}}
QLabel#SummaryUnit {{
    font-size: 12px;
    color: {COLOR_MUTED};
    padding-bottom: 3px;
}}
/* 아직 계산되기 전인 값 자리 */
QLabel#SummaryPending {{
    font-size: 17px;
    color: {COLOR_LINE};
}}
QLabel#FieldLabel {{
    font-size: 14px;
    color: {COLOR_SUB};
}}
/* 상단 진행 단계 (지나온 단계 / 현재 / 남은 단계) */
QLabel#Step {{
    font-size: 14px;
    padding: 5px 4px;
    color: {COLOR_MUTED};
}}
QLabel#Step[state="current"] {{
    font-weight: bold;
    color: {COLOR_ACCENT};
}}
QLabel#Step[state="done"] {{
    color: {COLOR_SUB};
}}
/* 현재 단계 밑줄 — 색만으로 현재 위치를 알리지 않는다 */
QFrame#StepMark {{
    border: none;
    max-height: 2px;
    min-height: 2px;
    background-color: transparent;
}}
QFrame#StepMark[state="current"] {{
    background-color: {COLOR_ACCENT};
}}
QLabel#StepSep {{
    font-size: 13px;
    color: {COLOR_LINE};
    padding: 5px 8px;
}}
QFrame#HeaderRule {{
    background-color: {COLOR_LINE};
    border: none;
    max-height: 1px;
    min-height: 1px;
}}
QLineEdit, QComboBox {{
    font-size: 15px;
    min-height: 28px;
    padding: 7px 12px;
    color: {COLOR_INK};
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_LINE};
    border-radius: 8px;
}}
QLineEdit:focus, QComboBox:focus {{
    border: 2px solid {COLOR_ACCENT};
}}
QLineEdit::placeholder {{ color: {COLOR_MUTED}; }}
QComboBox::drop-down {{ border: none; width: 32px; }}
QComboBox QAbstractItemView {{
    font-size: 15px;
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_LINE};
    selection-background-color: {COLOR_ACCENT};
    selection-color: #ffffff;
    outline: none;
}}
/* 주 동작 버튼 — 터치 대상이라 채워서 쓴다 (accent 를 쓰는 몇 안 되는 자리) */
QPushButton {{
    font-size: 16px;
    font-weight: bold;
    min-height: 46px;
    padding: 10px 28px;
    color: #ffffff;
    background-color: {COLOR_ACCENT};
    border: none;
    border-radius: 8px;
}}
QPushButton:hover {{ background-color: {COLOR_ACCENT_DARK}; }}
QPushButton:pressed {{ background-color: {COLOR_ACCENT_PRESSED}; }}
QPushButton:disabled {{
    color: {COLOR_MUTED};
    background-color: {COLOR_LINE};
}}
/* 보조 버튼 — 외곽선만 */
QPushButton#Secondary {{
    color: {COLOR_ACCENT};
    background-color: transparent;
    border: 1px solid {COLOR_LINE};
}}
QPushButton#Secondary:hover {{ background-color: {COLOR_ACCENT_SOFT}; }}
QCheckBox {{
    font-size: 15px;
    spacing: 10px;
    padding: 6px;
    background: transparent;
}}
QCheckBox::indicator {{
    width: 22px;
    height: 22px;
    border: 1px solid {COLOR_LINE};
    border-radius: 5px;
    background: {COLOR_SURFACE};
}}
QCheckBox::indicator:checked {{
    border: 1px solid {COLOR_ACCENT};
    background-color: {COLOR_ACCENT};
}}
QFrame#Card {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_LINE};
    border-radius: 10px;
}}
/* 차트 뷰는 QWidget 이라 전역 배경색을 물려받는다. 차트가 스스로 표면을
   칠하므로 뷰 자체는 투명하게 두고 테두리도 없앤다. */
QChartView {{
    background: transparent;
    border: none;
}}
/* 진행 표시 막대 — 작업이 도는 중임을 보여준다 */
QProgressBar {{
    background-color: {COLOR_LINE2};
    border: none;
    border-radius: 3px;
    max-height: 6px;
    min-height: 6px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {COLOR_ACCENT};
    border-radius: 3px;
}}
QMessageBox {{ background-color: {COLOR_SURFACE}; }}
QMessageBox QLabel {{ font-size: 15px; }}
"""
