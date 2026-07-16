"""공통 디자인 테마.

모던 플랫 · 밝은 테마 · 1280×800 터치스크린 기준의 색상 상수와
전역 스타일시트(APP_STYLE)를 모은다.
"""

# ──────────────────────────────────────────────────────────────
# 공통 디자인 테마 (모던 플랫 · 밝은 테마 · 1280×800 터치스크린)
# ──────────────────────────────────────────────────────────────
COLOR_BG = "#F5F7FA"            # 전체 배경
COLOR_SURFACE = "#FFFFFF"       # 입력칸/카드 표면
COLOR_PRIMARY = "#2D7FF9"       # 포인트(파랑)
COLOR_PRIMARY_DARK = "#1C6FE8"  # hover
COLOR_PRIMARY_PRESSED = "#1560CC"
COLOR_TEXT = "#2B2F36"          # 본문 글자
COLOR_SUBTLE = "#6B7280"        # 보조 글자
COLOR_BORDER = "#D8DEE9"        # 테두리

# 화면 기본 크기 (1280×800 화면에 여백을 두고 배치)
WIN_W = 1180
WIN_H = 720

APP_STYLE = f"""
QWidget, QMainWindow {{
    background-color: {COLOR_BG};
    color: {COLOR_TEXT};
    font-family: 'NanumSquare', 'Noto Sans CJK KR', sans-serif;
}}
QLabel {{
    font-size: 16px;
    background: transparent;
}}
QLabel#Title {{
    font-size: 22px;
    font-weight: bold;
    color: #FFFFFF;
    padding: 16px 24px;
    background-color: {COLOR_PRIMARY};
    border-radius: 12px;
}}
QLabel#Hint {{
    font-size: 13px;
    color: {COLOR_SUBTLE};
}}
QLabel#Message {{
    font-size: 26px;
    font-weight: bold;
    color: {COLOR_TEXT};
}}
/* 상단 진행 단계 표시 (지나온 단계 / 현재 / 남은 단계) */
QLabel#Step {{
    font-size: 14px;
    padding: 6px 14px;
    color: {COLOR_SUBTLE};
}}
QLabel#Step[state="current"] {{
    font-weight: bold;
    color: #FFFFFF;
    background-color: {COLOR_PRIMARY};
    border-radius: 14px;
}}
QLabel#Step[state="done"] {{
    color: {COLOR_PRIMARY};
}}
QLabel#StepSep {{
    font-size: 14px;
    color: {COLOR_BORDER};
}}
QLineEdit, QComboBox {{
    font-size: 16px;
    min-height: 30px;
    padding: 8px 12px;
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 10px;
}}
QLineEdit:focus, QComboBox:focus {{
    border: 2px solid {COLOR_PRIMARY};
}}
QComboBox::drop-down {{ border: none; width: 36px; }}
QComboBox QAbstractItemView {{
    font-size: 16px;
    background-color: {COLOR_SURFACE};
    selection-background-color: {COLOR_PRIMARY};
    selection-color: #FFFFFF;
    outline: none;
}}
QPushButton {{
    font-size: 17px;
    font-weight: bold;
    min-height: 48px;
    padding: 10px 28px;
    color: #FFFFFF;
    background-color: {COLOR_PRIMARY};
    border: none;
    border-radius: 12px;
}}
QPushButton:hover {{ background-color: {COLOR_PRIMARY_DARK}; }}
QPushButton:pressed {{ background-color: {COLOR_PRIMARY_PRESSED}; }}
QCheckBox {{
    font-size: 16px;
    spacing: 10px;
    padding: 6px;
    background: transparent;
}}
QCheckBox::indicator {{
    width: 26px;
    height: 26px;
    border: 2px solid {COLOR_BORDER};
    border-radius: 6px;
    background: {COLOR_SURFACE};
}}
QCheckBox::indicator:checked {{
    border: 2px solid {COLOR_PRIMARY};
    background-color: {COLOR_PRIMARY};
}}
QFrame#Card {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 16px;
}}
QTableWidget {{
    font-size: 15px;
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 10px;
    gridline-color: {COLOR_BORDER};
}}
QHeaderView::section {{
    font-size: 15px;
    font-weight: bold;
    color: #FFFFFF;
    background-color: {COLOR_PRIMARY};
    padding: 10px;
    border: none;
}}
QTableWidget::item {{ padding: 8px; }}
QTableCornerButton::section {{ background-color: {COLOR_PRIMARY}; border: none; }}
QMessageBox {{ background-color: {COLOR_SURFACE}; }}
QMessageBox QLabel {{ font-size: 16px; }}
"""
