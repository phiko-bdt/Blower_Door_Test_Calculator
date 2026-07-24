#!/usr/bin/env python3
"""사용설명서(docs/manual.pdf) 생성 — reportlab + NanumGothic.

  python3 docs/build_manual.py

내용을 고칠 땐 이 파일의 CONTENT 를 편집하고 다시 실행한다. LibreOffice
HTML→PDF 가 이 단말에서 동작하지 않아(source file could not be loaded)
reportlab 으로 직접 조판한다. 한글은 나눔고딕 TTF 를 등록해 쓴다.
"""

import os

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table,
    TableStyle, KeepTogether, PageBreak, Image as RLImage,
)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCREENS = os.path.join(HERE, "screens")
OUT = os.path.join(HERE, "manual.pdf")
FONT_DIR = "/usr/share/fonts/truetype/nanum"

# ── 폰트 등록 (나눔고딕: 한글 + ㎥/㎡ 등 포함) ─────────────────
# 시스템 fonts-nanum(권장, install_deps_apt.sh 가 설치)이 없으면 저장소에
# 포함된 NanumSquare 한 벌로 폴백한다 — 굵기 구분은 잃지만 클론만으로도
# 설명서 재생성이 되게.
_regular = f"{FONT_DIR}/NanumGothic.ttf"
_bold = f"{FONT_DIR}/NanumGothicBold.ttf"
if not (os.path.exists(_regular) and os.path.exists(_bold)):
    _repo_font = os.path.join(ROOT, "NanumSquare_acL.ttf")
    _regular = _bold = _repo_font
pdfmetrics.registerFont(TTFont("Nanum", _regular))
pdfmetrics.registerFont(TTFont("Nanum-B", _bold))
pdfmetrics.registerFontFamily("Nanum", normal="Nanum", bold="Nanum-B",
                              italic="Nanum", boldItalic="Nanum-B")

# ── 색 (bdt/theme.py 와 맞춤) ─────────────────────────────────
ACCENT = colors.HexColor("#1f5fa8")
ACCENT_DK = colors.HexColor("#154578")
INK = colors.HexColor("#1c2430")
SUB = colors.HexColor("#5b6672")
MUTED = colors.HexColor("#8a94a0")
LINE = colors.HexColor("#e4e8ee")
DANGER = colors.HexColor("#b42318")
WARNING = colors.HexColor("#b45309")
NOTE_BG = colors.HexColor("#eef4fb")
NOTE_BD = colors.HexColor("#d5e0ef")
WARN_BG = colors.HexColor("#fbf3e6")
WARN_BD = colors.HexColor("#e7cfa3")
DANG_BG = colors.HexColor("#fbeeec")
DANG_BD = colors.HexColor("#e6bcb6")
KEY_BG = colors.HexColor("#f8fafc")

# ── 문단 스타일 ──────────────────────────────────────────────
def _st(name, **kw):
    base = dict(fontName="Nanum", fontSize=10.5, leading=18, textColor=INK,
                alignment=TA_LEFT)
    base.update(kw)
    return ParagraphStyle(name, **base)

S = {
    "h1": _st("h1", fontName="Nanum-B", fontSize=23, leading=28,
              textColor=ACCENT_DK, spaceAfter=3),
    "lead": _st("lead", fontSize=11, leading=17, textColor=SUB),
    "small": _st("small", fontSize=8.5, leading=13.5, textColor=MUTED),
    "h2": _st("h2", fontName="Nanum-B", fontSize=15, leading=20,
              textColor=ACCENT, spaceBefore=20, spaceAfter=9),
    "h3": _st("h3", fontName="Nanum-B", fontSize=12, leading=16,
              textColor=INK, spaceBefore=14, spaceAfter=6),
    "body": _st("body", spaceAfter=7),
    "li": _st("li", leftIndent=14, bulletIndent=2, spaceAfter=5, leading=17),
    "cell": _st("cell", fontSize=9.5, leading=14.5),
    "cellk": _st("cellk", fontName="Nanum-B", fontSize=9.5, leading=14.5),
    "cellh": _st("cellh", fontName="Nanum-B", fontSize=9.5, leading=14.5,
                 textColor=ACCENT_DK),
    "box": _st("box", fontSize=9.8, leading=16),
}


def P(text, style="body"):
    return Paragraph(text, S[style])


def bullets(items, style="li", bullet="•"):
    return [Paragraph(f"{t}", S[style], bulletText=bullet) for t in items]


def callout(kind, html):
    """note/warn/danger 색 상자 (한 칸 표)."""
    bg, bd = {"note": (NOTE_BG, NOTE_BD), "warn": (WARN_BG, WARN_BD),
              "danger": (DANG_BG, DANG_BD)}[kind]
    t = Table([[P(html, "box")]], colWidths=[170 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 0.8, bd),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    # 앞뒤 여백 — 콜아웃끼리·본문과 붙지 않게.
    t.spaceBefore = 7
    t.spaceAfter = 7
    return t


def info_table(rows, header=None, key_w=58, three=False):
    """설명용 표. rows=[(key, val)] 또는 [(a,b,c)]. header=열 제목 리스트."""
    data = []
    style = [
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    r0 = 0
    if header:
        data.append([P(h, "cellh") for h in header])
        style += [("BACKGROUND", (0, 0), (-1, 0), NOTE_BG),
                  ("LINEBELOW", (0, 0), (-1, 0), 0.8, NOTE_BD)]
        r0 = 1
    for row in rows:
        if three:
            data.append([P(row[0], "cellk"), P(row[1], "cell"),
                         P(row[2], "cell")])
        else:
            data.append([P(row[0], "cellk"), P(row[1], "cell")])
    if three:
        widths = [40 * mm, 22 * mm, 108 * mm]
    else:
        widths = [key_w * mm, (170 - key_w) * mm]
    style.append(("BACKGROUND", (0, r0), (0, -1), KEY_BG))
    t = Table(data, colWidths=widths)
    t.setStyle(TableStyle(style))
    t.spaceBefore = 4
    t.spaceAfter = 6
    # 표가 페이지 경계에서 두 쪽으로 쪼개지지 않게 통째로 유지한다.
    return KeepTogether([t])


# 인라인 강조 헬퍼
def b(t):      # 굵게
    return f"<b>{t}</b>"


def btn(t):    # 버튼 이름
    return f'<font color="#154578"><b>[{t}]</b></font>'


def tag(t, c): # 색 라벨
    return f'<font color="{c}"><b>{t}</b></font>'


DEP = '<font color="#2a78d6"><b>감압</b></font>'
PRE = '<font color="#eb6834"><b>가압</b></font>'
DTAG = "#b42318"
WTAG = "#b45309"
NTAG = "#1f5fa8"


def screenshot(fname, caption, width_mm=155, root=False):
    """실제 앱 화면 캡처를 테두리·캡션과 함께 넣는다.

    반환은 플로어블 리스트(EXT 로 붙인다). 파일이 없으면 조용히 건너뛴다
    (capture_screens.py 를 안 돌렸을 때도 build 는 되게).
    """
    path = os.path.join(ROOT if root else SCREENS, fname)
    if not os.path.exists(path):
        return [P(f'<font color="#8a94a0">[화면: {caption} — 캡처 파일 없음]'
                  f'</font>', "small")]
    iw, ih = ImageReader(path).getSize()
    w = width_mm * mm
    h = w * ih / iw
    img = RLImage(path, width=w, height=h)
    box = Table([[img]], colWidths=[w])
    box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    box.hAlign = "CENTER"
    cap = P(f'<font color="#5b6672">▲ {caption}</font>', "small")
    cap.alignment = 1  # center
    grp = KeepTogether([box, Spacer(1, 3), cap])
    return [Spacer(1, 5), grp, Spacer(1, 8)]


def ch(title):
    """챕터 제목 — 새 페이지에서 시작하도록 앞에 PageBreak 를 둔다."""
    return [PageBreak(), P(title, "h2")]


# ── 본문 구성 ────────────────────────────────────────────────
def build():
    E = []  # 플로어블 목록
    A = E.append
    EXT = E.extend

    A(P("기밀성능 시험기 사용설명서", "h1"))
    A(P("건물 기밀성능 시험(KS L ISO 9972 준용)", "lead"))
    A(Spacer(1, 4))
    A(P("이 설명서는 현장 작업자를 위한 것입니다. 화면에 나오는 순서 그대로, "
        "단계별로 따라 하시면 됩니다. 버튼·문구는 실제 화면과 같은 이름으로 "
        "적었습니다.", "small"))
    A(Spacer(1, 6))
    A(callout("note",
      f'{tag("한눈에 보기", NTAG)} &nbsp; 전원 켜기 → {b("조건 입력")} → '
      f'{b("준비(영기류 확인)")} → {b("목표 압력 조절")} → {b("측정")} → '
      f'{b("계산")} → {b("성적서 확인·공유")}. 한 번의 시험은 보통 몇 분이면 '
      f'끝납니다.'))

    A(P("0. 기밀 시험 장비 구성", "h2"))
    A(P("이 장비는 아래 세 부분으로 구성됩니다."))
    A(info_table([
        ("제어 모듈", "전원공급부, 압력센서, 컴퓨터, 터치스크린을 담은 "
         "인클로저(제어기). 시험을 조작하고 성적서를 발행하는 본체입니다."),
        ("팬 모듈", f'{b("PWM 제어 팬 2개")}와 전원·PWM 제어선, 외부 압력을 재기 '
         f'위한 측정 탭(tap)을 갖춘 모듈. 개구부(창호 등)에 설치합니다.'),
        ("연결선", "제어 모듈과 팬 모듈을 잇는 선. "
         '<font color="#b42318"><b>전원선(48 VDC, 적·흑)</b></font> · '
         '<font color="#b45309"><b>PWM 신호선(황)</b></font> · '
         '<font color="#2a78d6"><b>압력 측정 튜브(청)</b></font>.'),
    ], header=["구성", "설명"], key_w=32))

    EXT(ch("1. 장비 켜기 — 설치와 전원"))
    A(P("시험을 시작하기 전에 아래 순서로 설치·연결하고 전원을 켭니다. 하나라도 "
        "빠지면 측정이 어긋나거나 시험 불가 화면이 뜹니다."))
    EXT(bullets([
        f'{b("팬 모듈 설치")}: 팬 모듈을 창호 등 개구부에 단단히 고정하고, 틈새는 '
        f'밀폐합니다.',
        f'{b("제어기 전원 연결")}: 제어 모듈에 220 VAC 전원선을 연결하고 전원 '
        f'버튼을 켜면 장치에 전원이 들어옵니다.',
        f'{b("팬 모듈 전원")}: 팬 전원 공급은 연결선 중 전원선 연결이 '
        f'필요합니다. 팬 전원 버튼을 {b("Reset 방향으로 누르면 전원이 켜진")} '
        f'상태입니다. 시험 전에는 팬이 돌지 않는 상태(정지)여야 합니다. '
        f'{b("아래 순서 경고를 반드시 지키세요.")}',
        f'{b("압력센서 호스")}: 실내·실외 측정 튜브(청)를 연결합니다. '
        f'차압센서는 정압·부압(+/-) {b("양방향 측정")}이 가능하므로 반대로 '
        f'연결해도 측정은 됩니다(부호만 반대로 읽힘). 다만 '
        f'{b("가압·감압 시험 시 팬 방향")}에 주의하세요.',
        f'{b("건물 상태")}: 창문·문을 규정대로 닫고 시험 조건을 맞춥니다.',
    ]))
    A(callout("danger",
      f'{tag("경고 — 팬 전원을 켜는 순서", DTAG)}<br/>'
      f'{b("앱이 실행된 상태에서 PWM 신호선(황)을 먼저 연결한 뒤")} 팬 전원을 '
      f'켜세요. PWM선이 연결되지 않은 채로 팬 전원을 켜면 팬이 '
      f'{b("100% 속도로 회전")}해 시험 공간에 손상을 줄 수 있습니다.<br/>'
      f'순서: ① 앱 실행 → ② PWM선(황) 연결 → ③ 팬 전원 ON(Reset).'))
    A(callout("warn",
      f'{tag("주의 — 팬", WTAG)} &nbsp; 화면에서 팬 세기가 0보다 커지면 '
      f'{b("실제로 팬이 돕니다")}. 손·옷·이물질이 팬에 닿지 않도록 하세요. '
      f'팬 세기 0은 항상 안전합니다.'))
    A(P("앱 실행", "h3"))
    EXT(bullets([
        f'전원을 켜면 부팅 후 앱이 {b("자동으로 전체화면")}으로 열립니다. 앱을 '
        f'종료한 경우 바탕화면 아이콘으로 다시 실행합니다(아이콘을 더블클릭한 뒤 '
        f'{btn("Execute")} 버튼).',
        f'{b("앱 종료는 화면 오른쪽 위")} {btn("종료")} 버튼입니다(창 테두리가 '
        f'없어 이 버튼이 유일한 방법).',
    ]))
    A(P("장비 종료", "h3"))
    A(P("장비를 끌 때는 아래 순서대로 전원을 차단하세요."))
    EXT([Paragraph(t, S["li"], bulletText=f"{i}.") for i, t in enumerate([
        f'{b("팬 전원 버튼을 OFF")}로 내립니다.',
        '팬 모듈 전원선 등 연결선을 분리합니다.',
        f'앱을 종료한 뒤 {b("OS 종료(shutdown)")}를 합니다.',
        f'{b("제어 모듈 전원 버튼을 OFF")}로 내립니다.',
        '전원 플러그를 제거합니다.',
    ], start=1)])

    EXT(ch("2. 조건 입력 — 첫 화면"))
    A(P(f'첫 화면({b("조건 입력")})에서 시험 정보를 입력합니다. 입력칸을 누르면 '
        f'화면 키보드가 뜹니다(숫자 칸은 숫자 키패드, 글자 칸은 한글/영문 '
        f'키보드).'))
    EXT(screenshot("input.png", "조건 입력 화면 — 오른쪽 위에 이전 보고서·설정·"
                   "저장하고 시작 버튼"))
    A(P("꼭 입력해야 하는 항목 (＊ 표시)", "h3"))
    A(info_table([
        ("실내 체적 (㎥)", "측정 대상 공간의 체적. 누기량 환산의 기준이라 반드시 "
         "정확히 넣습니다. 숫자만 입력."),
        ("팬 수량 (팬 1 / 팬 2)", f'사용하는 팬을 {b("체크")}합니다. 체크한 개수가 '
         f'곧 팬 수입니다. {b("최소 하나는 반드시")} 선택해야 합니다. 팬을 1개만 '
         f'쓰면(1개 체크), {b("사용하지 않는 팬은 팬 커버로 막습니다")} — 막지 '
         f'않으면 팬 사이로 차압에 따라 기류가 발생해 측정값에 오류가 '
         f'발생합니다.'),
        ("수행할 시험", f'{DEP} 시험 / {PRE} 시험 중 하나 이상 체크. 둘 다 체크하면 '
         f'감압→가압 순서로 이어서 수행합니다.'),
    ]))
    A(P("선택 항목 (성적서에 실리는 정보)", "h3"))
    A(P("아래는 비워 둬도 시험은 됩니다. 성적서에 들어갈 정보이니 가능하면 "
        "채웁니다."))
    A(P("시험 목적 · 시험 위치 · 시험 방법 · 의뢰자 · 설계자 · 시험자 · "
        "시공자 · 연면적(㎡) · 구조"))
    A(callout("note",
      f'{tag("헤더 버튼", NTAG)} &nbsp; 화면 오른쪽 위에 세 버튼이 있습니다 — '
      f'{btn("이전 보고서")}(지난 성적서를 스마트폰으로 다운로드), '
      f'{btn("설정")}(측정 '
      f'기준값 편집), {btn("저장하고 시작")}(입력을 저장하고 다음 단계로).'))

    EXT(ch("3. 준비 — 영기류(기류 0) 확인"))
    A(P(f'{btn("저장하고 시작")}을 누르면 시험 종류별로 {b("준비")} 화면이 '
        f'뜹니다. 팬이 정지한 상태에서 실시간 압력을 보여줍니다.'))
    EXT(screenshot("prepare.png", "준비 화면 — 팬 정지 상태의 실시간 압력과 "
                   "측정 시작 버튼"))
    EXT([Paragraph(t, S["li"], bulletText=f"{i}.") for i, t in enumerate([
        f'압력이 {b("0에 가깝게")} 안정됐는지 봅니다. 이때 값이 곧 자연 '
        f'압력차(영기류)입니다.',
        f'준비가 되면 오른쪽 위 {btn("측정 시작")} 버튼을 누릅니다.',
    ], start=1)])
    A(callout("warn",
      f'{tag("예외 — 영기류 과다", WTAG)} &nbsp; 팬 정지 압력의 절대값이 '
      f'{b("3 Pa를 넘으면")} 경고가 표시됩니다(KS L ISO 9972 기준). 외풍이 '
      f'강하거나 건물에 큰 압력차가 있다는 뜻입니다. 측정을 막지는 않지만 결과 '
      f'신뢰도가 떨어지므로 조건을 안정시킨 뒤 시작하기를 권합니다.'))

    EXT(ch("4. 목표 압력 조절 — 팬 세기 맞추기"))
    A(P(f'{btn("측정 시작")}을 누르면 {b("목표 압력 조절")} 화면으로 넘어갑니다. '
        f'앱이 팬 세기를 자동으로 조절해 {b("목표 압력(기본 70 Pa)")}을 '
        f'맞춥니다.'))
    EXT(screenshot("targeting.png", "목표 압력 조절 화면 — 팬 세기를 자동으로 "
                   "조절하며 실시간 압력 표시"))
    EXT(bullets([
        '상단에 진행 안내가, 가운데에 실시간 압력이 표시됩니다.',
        f'압력이 목표 근처(허용 오차 안, 기본 ±10%)에서 '
        f'{b("정해진 시간(기본 10초) 연속 유지")}되면 조절이 끝나고 측정으로 '
        f'넘어갑니다.',
    ]))
    A(callout("danger",
      f'{tag("예외 — 시험 불가(압력을 제어할 수 없습니다)", DTAG)}<br/>'
      f'이 화면 또는 측정 준비 중 아래 상황이면 '
      f'{b("「시험 불가 — 압력을 제어할 수 없습니다」")} 화면이 뜹니다. 장비 '
      f'고장과는 다른 {b("현장 조건")} 문제입니다.<br/>'
      f'• {b("팬을 최소로 낮춰도 압력이 상한(기본 100 Pa)을 넘음")} → 건물이 '
      f'지나치게 기밀하거나 외풍이 강합니다.<br/>'
      f'• {b("팬을 최대로 올려도 압력이 하한(기본 15 Pa)에 못 미침")} → 공간이 '
      f'너무 넓어 가·감압이 이루어지지 않거나, {b("압력센서 연결·호스 방향이 잘못")}'
      f'됐을 수 있습니다(값이 0 Pa 근처).<br/>'
      f'대처: 팬·패널 밀폐 상태와 센서 호스 연결을 점검하고 다시 시도합니다. '
      f'필요하면 {btn("설정")}에서 상한/하한을 조정합니다(하한은 목표보다 낮아야 '
      f'합니다).'))

    EXT(ch("5. 측정 — 여러 압력점 순차 측정"))
    A(P(f'조절이 끝나면 {b("측정")} 화면에서 시작 압력부터 낮은 압력까지 여러 '
        f'지점(기본 10점)을 자동으로 측정합니다. 각 지점에서 압력이 안정될 때까지 '
        f'기다렸다가 평균을 기록합니다.'))
    EXT(screenshot("measure.png", "측정 화면 — 압력차별 측정점이 그래프에 하나씩 "
                   "찍힘"))
    EXT(bullets([
        '진행은 자동입니다. 화면의 그래프에 측정점이 하나씩 찍힙니다.',
        f'{DEP}과 {PRE}을 모두 선택했다면, 감압 측정이 끝난 뒤 가압 준비 화면으로 '
        f'이어집니다.',
    ]))
    A(callout("warn",
      f'{tag("예외 — 저압 경고", WTAG)} &nbsp; 아주 낮은 압력(기본 10 Pa 미만)'
      f'에서 잡힌 점은 신뢰도가 낮아 경고가 표시됩니다. 다만 이런 점도 '
      f'{b("계산에서 제외하지 않고 포함")}합니다(의도된 방침).'))

    A(P("6. 계산 — 결과 요약", "h2"))
    A(P(f'모든 측정이 끝나면 {b("계산")} 화면이 측정값을 회귀분석해 핵심 결과를 '
        f'먼저 보여줍니다.'))
    EXT(bullets([
        '누기량, 보정 누기 계수(C<sub>0</sub>), 기류 지수(n), 누기 면적 등 '
        'KS L ISO 9972 용어로 표시됩니다.',
        '내용을 확인하면 성적서(PDF)가 자동으로 만들어집니다.',
    ]))

    EXT(ch("7. 성적서 — 확인과 공유"))
    A(P(f'마지막 {b("성적서")} 화면에서 발행된 성적서를 앱 안에서 바로 '
        f'봅니다.'))
    EXT(screenshot("report.png", "성적서 화면 — 왼쪽 성적서, 오른쪽 스마트폰 "
                   "공유 QR, 아래 저장 위치·버튼"))
    A(info_table([
        (f'{btn("100% 로 보기")}', "성적서를 원래 크기로 확대해 표의 작은 글씨까지 "
         "확인. 손가락으로 끌어 이동합니다. 다시 누르면 화면 맞춤."),
        (f'{btn("USB 로 복사")}', "USB 메모리를 연결했을 때만 나타납니다. 누르면 "
         "성적서 PDF가 USB에 복사됩니다."),
        (f'{btn("새 시험 시작")}', "처음(조건 입력) 화면으로 돌아가 다음 시험을 "
         "시작합니다."),
    ], header=["버튼", "기능"], key_w=45))
    A(P(f'성적서는 시험할 때마다 단말 바탕화면의 {b("「결과보고서」 폴더")}에 '
        f'{b("날짜·시험종류·체적")}이 담긴 이름으로 자동 보관됩니다(예: '
        f'202607171943_감압+가압_500㎥.pdf). 화면 하단에 저장 위치가 표시됩니다.'))
    A(P("스마트폰으로 성적서 다운로드 — 2단계 QR", "h3"))
    A(P("성적서 화면 오른쪽에 QR 두 개가 있습니다. 스마트폰 카메라로 순서대로 "
        "스캔합니다."))
    EXT([Paragraph(t, S["li"], bulletText=f"{i}.") for i, t in enumerate([
        f'{b("① WiFi 접속 QR")}: 스캔하면 단말이 만드는 WiFi'
        f'({b("BlowerDoor-Test")})에 스마트폰이 자동으로 연결됩니다.',
        f'{b("② 목록 열기 QR")}: 연결된 뒤 스캔하면 성적서 목록 페이지가 '
        f'열립니다. 목록에서 {b("「받기」")}를 누르면 스마트폰에 저장됩니다.',
    ], start=1)])
    A(callout("note",
      f'{tag("수동 연결", NTAG)} &nbsp; ① QR이 잘 안 되면, 스마트폰 WiFi 설정에서 직접 '
      f'{b("BlowerDoor-Test")}에 붙습니다(비밀번호는 ① QR 아래에 표시됩니다). '
      f'그다음 ② QR을 찍거나 주소를 직접 입력합니다.'))

    EXT(ch("8. 이전 보고서 받기 — 시험 없이 지난 성적서 스마트폰으로"))
    A(P(f'새 시험을 하지 않고 지난 성적서만 스마트폰으로 넘기려면, 첫 화면 오른쪽 위 '
        f'{btn("이전 보고서")} 버튼을 누릅니다.'))
    EXT(screenshot("input.png", "첫 화면(조건 입력) 오른쪽 위의 [이전 보고서] "
                   "버튼 — 여기서 시작합니다"))
    EXT(bullets([
        f'성적서 화면과 같은 {b("2단계 QR")}이 뜨는데, 여기서는 '
        f'{b("화면 양쪽에 크게")} 배치돼 스마트폰으로 찍을 때 두 QR이 겹치지 않습니다.',
        f'① WiFi 접속 → ② 목록 열기 순서는 동일합니다. 다 받은 뒤 {btn("닫기")}를 '
        f'누르면 첫 화면으로 돌아갑니다.',
    ]))
    EXT(screenshot("past_reports.png", "이전 보고서 화면 — 두 QR을 좌우로 크게 "
                   "배치(겹침 방지)"))

    EXT(ch("9. 설정 — 측정 기준값"))
    A(P(f'첫 화면의 {btn("설정")} 버튼에서 측정 기준값을 바꿀 수 있습니다. '
        f'{b("설정은 시험을 시작하기 전에만")} 바꾸세요(측정 중 기준이 바뀌면 같은 '
        f'시험 안에서 값이 어긋납니다). 바꾼 값은 저장되어 다음 시험부터 '
        f'적용됩니다.'))
    EXT(screenshot("settings.png", "설정 화면 — 측정 기준값을 항목별로 편집"))
    A(info_table([
        ("목표 압력", "70 Pa", "측정을 시작할 압력차."),
        ("수렴 허용 오차", "10 %", "수렴 판정 폭(목표의 비율). 70 Pa의 10% → ±7 Pa."),
        ("수렴 유지 시간", "10 초", "허용 오차 안에 연속으로 머물러야 하는 시간."),
        ("시험 가능 상한", "100 Pa", "팬 최소에서도 이 값을 넘으면 시험 불가."),
        ("측정 가능 하한", "15 Pa", f'팬 최대에서도 못 미치면 시험 불가. '
         f'{b("목표보다 낮아야")} 저장됩니다.'),
        ("압력 평활 창", "20 점", "조절 압력·수렴 판정에 쓰는 이동평균 표본 수."),
        ("지점 측정 시간", "10 초", "측정 지점마다 압력을 산술평균하는 시간."),
        ("안정화 대기", "2 초/duty", "팬 세기를 바꾼 뒤 압력 안정 대기(변화량 비례)."),
        ("측정 지점 수", "10 개", "시작 압력에서 최저 지점까지 몇 등분해 측정할지."),
        ("저압 경고 기준", "10 Pa", "이보다 낮은 압력점에 경고 표시(계산에는 포함)."),
    ], header=["항목", "기본값", "설명"], three=True))
    A(callout("note",
      f'{tag("되돌리기", NTAG)} &nbsp; 값을 잘못 바꿨으면 '
      f'{btn("기본값으로 되돌리기")}로 표의 기본값으로 복원합니다. 범위를 벗어난 '
      f'값이나 모순된 값(예: 하한 ≥ 목표)은 저장이 거부되고 안내가 뜹니다.'))

    EXT(ch("10. 문제 해결 — 예외 상황 모음"))
    A(P("화면에 뜨는 알림", "h3"))
    A(info_table([
        (tag("시험 불가 — 압력을 제어할 수 없습니다", DTAG),
         f'{b("현장 조건")} 문제(장비 고장 아님). 팬 최소에서 상한 초과(과기밀·'
         f'외풍) 또는 팬 최대에서 하한 미달(공간 과대·센서 오류). 밀폐·센서 호스를 '
         f'점검하고 다시 시도. 4·9장 참조.'),
        (tag("시험을 계속할 수 없습니다", DTAG),
         f'{b("장비·처리 오류")}(센서 통신, 계산, 성적서 생성 실패 등). 센서 '
         f'연결(USB)·전원을 확인하고 {btn("다시 시작")}. 반복되면 단말을 '
         f'재부팅합니다.'),
        ("영기류 3 Pa 초과 경고", "팬 정지 압력이 큼(바람·건물 압력차). 조건을 "
         "안정시킨 뒤 측정을 권함(측정은 가능). 3장 참조."),
        ("저압 경고", "낮은 압력점의 신뢰도 안내. 계산에는 포함되니 무시하고 진행해도 "
         "됩니다."),
        ("「준비 안 됨」(QR 자리)", "공유 WiFi(AP)가 아직 안 뜸. 잠시 기다리면 QR이 "
         "나타납니다. 7장 참조."),
    ], header=["화면/알림", "뜻과 대처"], key_w=52))
    A(P("참고 사항", "h3"))
    A(info_table([
        ("앱을 종료하고 싶어요", f'화면 오른쪽 위 {btn("종료")} 버튼(한 번 '
         f'되묻습니다). 전체화면이라 이 버튼이 유일한 종료 수단입니다.'),
        ("시험을 중간에 멈추고 싶어요", f'진행 중 화면의 {b("시험 중단")} 버튼으로 '
         f'멈춥니다. 확인창이 뜨고, 중단하면 팬이 정지되고 첫 화면으로 돌아갑니다.'),
        ("USB 복사 버튼이 안 보여요", "USB 메모리가 인식돼야 버튼이 나타납니다(약 "
         "2초 간격 확인). 다시 꽂아 보세요. 쓰기 금지(잠금)면 복사가 실패합니다."),
        ("화면이 전체화면에서 풀렸어요", f'보통 자동으로 다시 전체화면이 됩니다. '
         f'그래도 이상하면 {btn("종료")} 후 다시 실행하거나 재부팅하세요.'),
        ("지난 성적서를 다시 받고 싶어요", f'첫 화면 {btn("이전 보고서")} 버튼 → 스마트폰 '
         f'QR로 받기. 8장 참조. 원본은 바탕화면 「결과보고서」 폴더에도 있습니다.'),
        ("압력값이 이상해요(유령값)", "대개 센서 호스 연결·방향 문제입니다. 호스와 "
         "USB 케이블 연결을 확인하세요. 반복되면 센서 전원을 껐다 켭니다."),
    ], header=["상황", "대처"], key_w=52))
    A(P("안전 — 팬", "h3"))
    A(callout("danger",
      f'{tag("중요", DTAG)}<br/>'
      f'• 팬 세기 0은 {b("항상 안전")}합니다. 0보다 크면 '
      f'{b("실제로 팬이 돕니다")}.<br/>'
      f'• 앱은 여러 겹의 안전장치로 '
      f'{b("앱이 실행 중이 아닐 때 팬을 자동으로 끕니다")}(부팅 시, 종료 후, '
      f'비정상 종료 감시 등). 측정 중에는 팬이 도는 것이 정상입니다.<br/>'
      f'• 팬 전원은 수동 공급이므로, 시험을 마치면 필요 시 팬 전원도 정리하세요.'))

    EXT(ch("11. 개발자 정보 — 저장소·설치·의존성"))
    A(P("이 장은 유지보수·재설치를 맡는 개발자를 위한 것입니다.", "small"))
    A(P("저장소 · 라이선스", "h3"))
    A(info_table([
        ("소스 저장소", "github.com/phiko-bdt/Blower_Door_Test_Calculator"),
        ("라이선스", "MIT License (© 2023) — 자유롭게 사용·수정·재배포할 수 "
         "있습니다."),
    ], key_w=34))
    A(P("실행 환경", "h3"))
    A(info_table([
        ("하드웨어", "라즈베리파이 5 + 1280×800 터치스크린. 팬은 커널 "
         "sysfs PWM(/sys/class/pwm, GPIO13), 압력센서는 Modbus RTU"
         "(/dev/ttyUSB0)로 제어합니다."),
        ("OS · 런타임", "Debian 12(bookworm), Python 3.11. GUI 는 PyQt6"
         "(labwc/Wayland 위 XWayland). 실행 명령: python3 -m bdt."),
    ], key_w=30))
    A(P("파이썬 의존성 (requirements.txt)", "h3"))
    A(P("PyQt6 · PyQt6-Charts(화면·실시간 차트), matplotlib · numpy · "
        "scipy(성적서 그래프·회귀분석), pyserial · crcmod(압력센서 Modbus·CRC), "
        "simple-pid(팬 압력 PID 제어), Pillow(이미지), openpyxl(엑셀), "
        "Flask(성적서 공유 웹서버), segno(QR 생성). "
        f'{b("설치")}: pip install -r requirements.txt'))
    A(P("시스템 패키지 · 리소스", "h3"))
    A(P("poppler-utils(pdftoppm · pdfinfo — 성적서 렌더), NetworkManager · "
        "dnsmasq · nftables(공유 AP · 캡티브 포털), 나눔고딕 폰트(fonts-nanum), "
        "커널 pwm-2chan 오버레이(/boot/firmware/config.txt). ※ 이 설명서 PDF "
        "생성은 reportlab 을 별도로 씁니다(docs/build_manual.py)."))
    A(P("오픈소스 고지", "h3"))
    A(P("이 앱은 아래 오픈소스에 기대고 있으며, 각 라이선스를 따릅니다.",
        "small"))
    A(info_table([
        ("PyQt6 / Qt6", "GPL v3 또는 상용(PyQt6) · LGPL v3(Qt6)"),
        ("matplotlib", "matplotlib License(PSF · BSD 계열)"),
        ("NumPy · SciPy · Flask · Pillow · pyserial", "BSD 계열(허용적 "
         "라이선스)"),
        ("simple-pid · crcmod", "MIT License"),
        ("segno", "BSD License"),
        ("나눔고딕(NanumGothic)", "SIL Open Font License 1.1"),
        ("poppler(poppler-utils)", "GPL v2"),
    ], header=["구성요소", "라이선스"], key_w=60))
    return E


# ── 페이지 프레임(머리말·꼬리말) ─────────────────────────────
def _decorate(canvas, doc):
    canvas.saveState()
    canvas.setFont("Nanum", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 10 * mm, "기밀성능 시험기 사용설명서")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"{doc.page}")
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 13 * mm, A4[0] - 18 * mm, 13 * mm)
    canvas.restoreState()


def main():
    doc = BaseDocTemplate(
        OUT, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title="기밀성능 시험기 사용설명서", author="J Hong")
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                  doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame],
                                       onPage=_decorate)])
    doc.build(build())
    print("생성됨:", OUT)


if __name__ == "__main__":
    main()
