"""계산 결과 브리핑 페이지.

계산 자체는 0.04초면 끝나지만, 뒤이어 그래프(약 6초)와 성적서(약 12초)를
만드는 동안 화면이 비어 있었다. 그 시간에 **실제로 계산된 값**을 사람이
읽을 수 있는 속도로 하나씩 내보인다. 없는 지연을 만들어 넣지 않는다 —
진짜 기다리는 시간에 진짜 값을 보여줄 뿐이다.

시험 현장에는 의뢰자가 함께 있으므로, "이런 과정을 거쳐 나온 수치입니다"를
보여주는 설명 화면이기도 하다.
"""

from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QProgressBar,
)
from PyQt6.QtCore import Qt, QTimer

from bdt.widgets import PageHeader, SectionTitle

# 값 하나가 채워지는 간격 (ms).
# 뒤 작업(그래프 약 6초 + 성적서 약 12초)이 18초쯤 걸리고 채울 값이 10개라,
# 450ms 면 4~5초에 다 채워지고 남은 시간은 결과를 들여다보는 시간이 된다.
REVEAL_INTERVAL = 450

# 아직 계산 전인 값 자리
PENDING = "…"


def _fmt(value, digits=2):
    """숫자를 자리수 맞춰 문자열로. 없으면 '–'."""
    if value is None:
        return "–"
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


class ResultRow(QWidget):
    """항목 이름 + 값 한 줄.

    이름·단위는 처음부터 보이고 값만 나중에 채워진다. 줄 자체를 숨겼다
    드러내면 카드가 자라면서 화면이 출렁이고, 아직 안 채워진 카드는 텅 빈
    채로 남아 고장난 것처럼 보인다. 틀을 먼저 보여주고 값을 채우는 편이
    실제 계산 과정에도 가깝다.
    """

    def __init__(self, label, value, unit="", emphasis=False):
        super().__init__()
        self._final = value
        name = QLabel(label)
        name.setObjectName("SummaryEmphasisName" if emphasis else "SummaryName")
        self.value = QLabel(PENDING)
        self._emphasis = emphasis
        self.value.setObjectName("SummaryPending")
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight
                                | Qt.AlignmentFlag.AlignBottom)
        # 값이 들어와도 줄 높이가 변하지 않도록 최종 크기로 자리를 잡아둔다
        probe = QLabel(value)
        probe.setObjectName(
            "SummaryEmphasisValue" if emphasis else "SummaryValue")
        probe.ensurePolished()
        self.value.setMinimumHeight(probe.sizeHint().height())
        unit_label = QLabel(unit)
        unit_label.setObjectName("SummaryUnit")
        unit_label.setAlignment(Qt.AlignmentFlag.AlignBottom)
        unit_label.setFixedWidth(62)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 3, 0, 3)
        row.setSpacing(8)
        row.addWidget(name)
        row.addStretch(1)
        row.addWidget(self.value)
        row.addWidget(unit_label)

    def fill(self):
        """계산된 값을 채워 넣는다."""
        self.value.setText(self._final)
        self.value.setObjectName(
            "SummaryEmphasisValue" if self._emphasis else "SummaryValue")
        self.value.style().unpolish(self.value)
        self.value.style().polish(self.value)


class CalculationSummary(QWidget):
    """계산 결과를 단계적으로 드러내며 뒤 작업의 진행 상황을 함께 보여준다."""

    def __init__(self, report, conditions):
        super().__init__()
        self._rows = []   # 순서대로 값을 채울 줄들

        header = PageHeader("기밀성능 시험", "Building Airtightness Test")

        # ── 왼쪽: 회귀분석 과정 ────────────────────────────────
        left = QFrame()
        left.setObjectName("Card")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(24, 18, 24, 18)
        left_layout.setSpacing(2)

        model = QLabel("Q = C₀ · Δpⁿ")
        model.setObjectName("Formula")
        model_note = QLabel("측정점에 최소 자승법 회귀를 적용해 누기 계수와 기류 지수 n 을 구합니다.")
        model_note.setObjectName("Hint")
        model_note.setWordWrap(True)
        left_layout.addWidget(model)
        left_layout.addWidget(model_note)
        left_layout.addSpacing(10)

        did_dep = bool(conditions.get("depressurization"))
        did_pre = bool(conditions.get("pressurization"))

        for suffix, name, ran in (("-", "감압", did_dep), ("+", "가압", did_pre)):
            if not ran:
                continue
            left_layout.addWidget(SectionTitle(name))
            for label, key, digits, unit in (
                ("보정 누기 계수 C₀", f"C0{suffix}", 2, "㎥/(h·Paⁿ)"),
                ("기류 지수 n", f"n{suffix}", 4, ""),
                ("결정 계수 R²", f"r^2{suffix}", 4, ""),
            ):
                row = ResultRow(label, _fmt(report.get(key), digits), unit)
                left_layout.addWidget(row)
                self._rows.append(row)
            left_layout.addSpacing(10)
        left_layout.addStretch(1)

        # ── 오른쪽: 50 Pa 환산 결과 ───────────────────────────
        right = QFrame()
        right.setObjectName("Card")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(24, 18, 24, 18)
        right_layout.setSpacing(2)

        conv = SectionTitle("50 Pa 기준 환산")
        conv_note = QLabel("회귀식에 Δp = 50 Pa 를 넣어 기준 압력에서의 값을 구합니다.")
        conv_note.setObjectName("Hint")
        conv_note.setWordWrap(True)
        right_layout.addWidget(conv)
        right_layout.addWidget(conv_note)
        right_layout.addSpacing(10)

        for suffix, name, ran in (("-", "감압", did_dep), ("+", "가압", did_pre)):
            if not ran:
                continue
            row = ResultRow(f"{name} Q50", _fmt(report.get(f"Q50{suffix}"), 1), "㎥/h")
            right_layout.addWidget(row)
            self._rows.append(row)

        right_layout.addSpacing(14)

        # 최종 결과 — 감압·가압을 모두 했으면 평균, 하나면 그 값
        if did_dep and did_pre:
            final_key, final_note = "ACH50_avg", "감압·가압 평균"
            al_key = "AL50_avg"
        elif did_dep:
            final_key, final_note = "ACH50-", "감압 기준"
            al_key = "AL50-"
        else:
            final_key, final_note = "ACH50+", "가압 기준"
            al_key = "AL50+"

        right_layout.addWidget(SectionTitle("최종 결과"))

        ach = ResultRow("ACH50  시간당 공기교환횟수",
                        _fmt(report.get(final_key), 2), "1/h", emphasis=True)
        note = QLabel(final_note)
        note.setObjectName("Hint")
        al = ResultRow("AL50  누기 면적", _fmt(report.get(al_key), 4), "㎡")
        right_layout.addWidget(ach)
        right_layout.addWidget(note)
        right_layout.addWidget(al)
        right_layout.addStretch(1)
        self._rows += [ach, al]

        columns = QHBoxLayout()
        columns.setSpacing(16)
        columns.addWidget(left, 1)
        columns.addWidget(right, 1)

        # ── 하단: 뒤 작업(그래프·성적서) 진행 상황 ─────────────
        self.status = QLabel("누기 그래프를 그리는 중…")
        self.status.setObjectName("Hint")
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)  # 미확정 — 남은 시간을 알 수 없다
        self.bar.setTextVisible(False)
        self.bar.setFixedWidth(200)
        status_row = QHBoxLayout()
        status_row.setSpacing(14)
        status_row.addWidget(self.status)
        status_row.addStretch(1)
        status_row.addWidget(self.bar)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 24, 40, 24)
        outer.setSpacing(14)
        outer.addWidget(header)
        # 카드는 내용만큼만 차지하고(늘리면 안이 텅 빈 채로 벌어진다)
        # 남는 공간을 위아래로 나눠 가운데에 둔다
        outer.addStretch(1)
        outer.addLayout(columns)
        outer.addStretch(1)
        outer.addLayout(status_row)

        # 틀은 처음부터 보이고, 값만 하나씩 채워진다
        self._index = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._reveal_next)

    def start(self):
        """값을 하나씩 채우기 시작한다."""
        self._reveal_next()
        self._timer.start(REVEAL_INTERVAL)

    def _reveal_next(self):
        if self._index >= len(self._rows):
            self._timer.stop()
            return
        self._rows[self._index].fill()
        self._index += 1

    def set_progress(self, text):
        """뒤에서 도는 작업(그래프·성적서)의 진행 상황을 받는다."""
        self.status.setText(text)

    def set_done(self):
        """모든 작업이 끝났다 — 남은 값을 즉시 채우고 막대를 감춘다."""
        self._timer.stop()
        for row in self._rows:
            row.fill()
        self.bar.setVisible(False)
