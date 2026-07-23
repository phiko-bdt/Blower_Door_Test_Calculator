"""공용 위젯 모음."""

from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QDialog,
)
from PyQt6.QtCore import Qt, QTimer, QSize

from bdt.theme import STANDARD_NAME, STANDARD_NOTE


class ElidedLabel(QLabel):
    """긴 문구가 와도 레이아웃을 넓히지 않는 한 줄 라벨.

    보통 QLabel 은 setWordWrap(False) 이면 최소 폭이 텍스트 전체 폭이 된다.
    상단 진행 문구처럼 길이가 들쭉날쭉한 라벨이 그러면, 문구 하나가 길어지는
    순간 그 라벨을 담은 상단 바의 최소 폭이 화면(1280)을 넘어 창이 화면보다
    넓어지고 — 그때 Qt 가 전체화면을 조용히 푼다. 데코레이션이 없는 키오스크
    단말에선 창을 줄이거나 되돌릴 수단이 없어 버튼이 화면 밖으로 밀린 채 갇힌다
    (목표 압력 조절 중 긴 안내 문구가 뜰 때 실제로 겪었다).

    이 라벨은 **최소 폭을 두지 않고**(레이아웃을 넓히지 않음), 선호 폭은 전체
    텍스트 폭 그대로 둔다(자리가 있으면 다 보여줌). 폭이 모자라면 그때만 끝을
    …로 줄여 그린다. QLabel 자체 그리기를 그대로 쓰므로 스타일시트 색·여백은
    영향받지 않는다.
    """

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full = ""
        self.setText(text)

    def setText(self, text):
        self._full = text or ""
        self._apply_elide()

    def text(self):
        return self._full

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self):
        width = self.width()
        if width <= 0:
            shown = self._full
        else:
            shown = self.fontMetrics().elidedText(
                self._full, Qt.TextElideMode.ElideRight, width)
        # QLabel 의 실제 텍스트만 줄인다 — sizeHint 는 전체 폭으로 따로 돌려주므로
        # (아래) 줄인 텍스트가 다시 폭을 좁히는 되먹임은 생기지 않는다.
        super().setText(shown)

    def sizeHint(self):
        base = super().sizeHint()
        return QSize(self.fontMetrics().horizontalAdvance(self._full),
                     base.height())

    def minimumSizeHint(self):
        # 세로 높이만 확보하고 가로 최소는 0 으로 둔다 — 이 라벨이 상단 바를
        # 화면보다 넓게 밀어 전체화면을 풀어버리지 않게 하는 핵심이다.
        return QSize(0, super().minimumSizeHint().height())


class Dialog(QDialog):
    """앱 디자인을 쓰는 확인·알림 창.

    QMessageBox 는 말풍선 아이콘에 영문 Yes/No 버튼이라 앱과 따로 놀았다
    (현장에서 '옛날 프로그램 같다'는 지적을 받았다). 아이콘을 없애고 제목·본문·
    버튼을 앱의 다른 화면과 같은 토큰으로 그린다. 버튼 문구도 '예/아니오'가
    아니라 실제 동작('종료'·'중단')을 쓴다 — 무엇에 동의하는지가 분명해진다.

    쓰는 쪽은 confirm()·alert() 를 부른다.
    """

    def __init__(self, parent, title, text, ok_text=None, cancel_text=None,
                 danger=False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        # 창틀을 없앤다. 남겨두면 전체화면 앱 위에 회색 제목표시줄과 최소화·
        # 닫기 버튼이 뜨고, 제목이 표시줄과 본문에 두 번 나온다. 터치스크린
        # 확인창은 옮길 일도 없다.
        self.setWindowFlags(Qt.WindowType.Dialog
                            | Qt.WindowType.FramelessWindowHint)

        heading = QLabel(title)
        heading.setObjectName("DialogTitle")
        body = QLabel(text)
        body.setObjectName("DialogBody")
        body.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)
        if cancel_text:
            cancel = QPushButton(cancel_text)
            cancel.setObjectName("Secondary")
            cancel.setMinimumWidth(120)
            cancel.clicked.connect(self.reject)
            buttons.addWidget(cancel)
        ok = QPushButton(ok_text or "확인")
        ok.setObjectName("Danger" if danger else "")
        ok.setMinimumWidth(120)
        ok.clicked.connect(self.accept)
        # 되돌릴 수 없는 동작은 기본 버튼으로 두지 않는다 — 터치스크린에서
        # 엔터가 아니라 손가락으로 누르지만, 실수 방지의 기본은 지킨다.
        ok.setDefault(not danger)
        buttons.addWidget(ok)

        card = QFrame()
        card.setObjectName("Card")
        inner = QVBoxLayout(card)
        inner.setContentsMargins(32, 26, 32, 24)
        inner.setSpacing(12)
        inner.addWidget(heading)
        inner.addWidget(body)
        inner.addSpacing(6)
        inner.addLayout(buttons)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)
        self.setMinimumWidth(420)


def confirm(parent, title, text, ok_text="확인", cancel_text="취소",
            danger=False):
    """예/아니오를 묻는다. 승인하면 True."""
    dialog = Dialog(parent, title, text, ok_text, cancel_text, danger)
    return dialog.exec() == QDialog.DialogCode.Accepted


def alert(parent, title, text):
    """알리기만 한다 (확인 버튼 하나)."""
    Dialog(parent, title, text, ok_text="확인").exec()


class Toast(QFrame):
    """화면 위에 잠깐 떴다 스스로 사라지는 알림. 모달이 아니다.

    확인이 필요 없는 가벼운 안내에 쓴다(예: USB 감지). Dialog 는 모달이라
    작업자가 눌러 닫아야 하지만, 토스트는 정해진 시간 뒤 스스로 없어진다.
    포커스·클릭을 뺏지 않아 화면 키보드나 밑의 버튼을 방해하지 않는다.
    """

    def __init__(self, parent, title, body, duration_ms=4500):
        super().__init__(parent)
        self.setObjectName("Toast")
        # 클릭이 밑의 위젯(복사 버튼 등)으로 통과하게 둔다
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        heading = QLabel(title)
        heading.setObjectName("ToastTitle")
        text = QLabel(body)
        text.setObjectName("ToastBody")
        # 본문은 한 줄로 — 줄바꿈을 끄면 토스트가 문구 폭에 맞춰 넓어진다
        text.setWordWrap(False)

        inner = QVBoxLayout(self)
        inner.setContentsMargins(24, 16, 24, 16)
        inner.setSpacing(4)
        inner.addWidget(heading)
        inner.addWidget(text)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.deleteLater)
        self._duration = duration_ms
        self._anchor = None
        self._gap = 12

    def popup(self, anchor=None, gap=12):
        """정해진 시간 뒤 스스로 사라지는 알림을 띄운다.

        anchor(위젯)를 주면 그 위젯 바로 위·오른쪽 맞춤으로 붙인다(예: USB 복사
        버튼). 없으면 부모 위쪽 가운데. 배치는 레이아웃이 끝난 뒤로 미룬다 —
        방금 보이게 된 앵커 버튼의 위치가 아직 안 잡혔을 수 있어서다.
        """
        self._anchor = anchor
        self._gap = gap
        QTimer.singleShot(0, self._place)

    def _place(self):
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        anchor = self._anchor
        if anchor is not None and anchor.isVisible():
            tl = anchor.mapTo(parent, anchor.rect().topLeft())
            x = tl.x() + anchor.width() - self.width()   # 오른쪽 끝 맞춤
            y = tl.y() - self.height() - self._gap        # 버튼 바로 위
        else:
            x = (parent.width() - self.width()) // 2
            y = 24
        x = max(12, min(x, parent.width() - self.width() - 12))
        y = max(12, y)
        self.move(x, y)
        self.show()
        self.raise_()
        self._timer.start(self._duration)


def toast(parent, title, body, duration_ms=4500, anchor=None):
    """가벼운 알림을 띄운다 (자동 소멸). 만든 Toast 를 돌려준다.

    anchor 를 주면 그 위젯 바로 위에 붙는다 (없으면 상단 가운데)."""
    t = Toast(parent, title, body, duration_ms)
    t.popup(anchor=anchor)
    return t


def _apply_state(widget, state):
    """상태 property 를 바꾸고 스타일을 다시 입힌다.

    Qt 는 property 만 바꿔서는 스타일시트를 다시 계산하지 않는다.
    """
    widget.setProperty("state", state)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class StepHeader(QWidget):
    """상단 진행 단계 표시. 시험은 정해진 순서로 진행되므로 현재 위치를 보여준다.

    수행할 시험(감압/가압)이 조건 입력 후에 정해지므로 단계 목록은 나중에 채운다.
    현재 단계는 색 + 굵기 + 밑줄로, 지나온 단계는 체크 표시로 알린다
    (색 하나에만 기대지 않는다).
    """

    def __init__(self):
        super().__init__()
        self.steps = []       # [(라벨, 밑줄, 이름), ...]

        self.row = QHBoxLayout()
        self.row.setContentsMargins(40, 14, 0, 0)
        self.row.setSpacing(0)

        # 앱이 전체화면이라 창의 X 버튼이 없다 — 종료 수단은 앱 안에 있어야
        # 한다. set_steps 가 self.row 를 통째로 비우므로 단계 목록과 같은
        # 레이아웃에 두면 첫 단계 전환에서 사라진다.
        self.quit_button = QPushButton("종료")
        self.quit_button.setObjectName("HeaderQuit")
        self.quit_button.setFixedHeight(30)
        self.quit_button.setMinimumWidth(72)

        top = QHBoxLayout()
        top.setContentsMargins(0, 10, 40, 0)
        top.setSpacing(0)
        top.addLayout(self.row)
        top.addStretch(1)
        top.addWidget(self.quit_button, 0, Qt.AlignmentFlag.AlignTop)

        # 헤더와 본문을 가르는 실선 한 줄 (성적서의 구분선과 같은 역할)
        rule = QFrame()
        rule.setObjectName("HeaderRule")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        outer.addLayout(top)
        outer.addWidget(rule)

    def _clear(self):
        while self.row.count():
            item = self.row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def set_steps(self, steps):
        """단계 목록을 새로 구성한다."""
        self._clear()
        self.steps = []
        for i, name in enumerate(steps):
            if i:
                sep = QLabel("›")
                sep.setObjectName("StepSep")
                self.row.addWidget(sep)

            label = QLabel(name)
            label.setObjectName("Step")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # 현재 단계를 알리는 밑줄. 색맹·저시력에서도 위치가 드러난다.
            mark = QFrame()
            mark.setObjectName("StepMark")

            cell = QWidget()
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(4)
            cell_layout.addWidget(label)
            cell_layout.addWidget(mark)

            self.row.addWidget(cell)
            self.steps.append((label, mark, name))
        self.row.addStretch(1)

    def set_current(self, index):
        """현재 단계는 강조, 지나온 단계는 체크로 표시한다."""
        for i, (label, mark, name) in enumerate(self.steps):
            if i < index:
                state = "done"
                label.setText(f"✓ {name}")
            elif i == index:
                state = "current"
                label.setText(name)
            else:
                state = "todo"
                label.setText(name)
            _apply_state(label, state)
            _apply_state(mark, state)


class PageHeader(QWidget):
    """페이지 제목 — 성적서 헤더와 같은 구성.

    왼쪽에 제목·영문 부제, 오른쪽에 적용 규격을 두고 그 아래 accent 룰을 깐다.
    성적서를 펼쳤을 때와 같은 인상을 화면에서도 주기 위한 것이다.
    """

    def __init__(self, title, subtitle="", actions=None, show_standard=True):
        super().__init__()

        title_label = QLabel(title)
        title_label.setObjectName("Title")
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(2)
        left.addWidget(title_label)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("Subtitle")
            left.addWidget(subtitle_label)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.addLayout(left)
        bar.addStretch(1)
        # 규격 표기(오른쪽). 동작 버튼과 나란히 두면 두 줄짜리 표기와 버튼의
        # 상하 정렬이 어긋나 어색하므로, 버튼을 둔 페이지는 show_standard=False
        # 로 뺀다 (규격은 성적서에 어차피 실린다).
        if show_standard:
            standard = QLabel(STANDARD_NAME)
            standard.setObjectName("Standard")
            standard.setAlignment(Qt.AlignmentFlag.AlignRight)
            note = QLabel(STANDARD_NOTE)
            note.setObjectName("StandardNote")
            note.setAlignment(Qt.AlignmentFlag.AlignRight)
            right = QVBoxLayout()
            right.setContentsMargins(0, 0, 0, 0)
            right.setSpacing(1)
            right.addWidget(standard)
            right.addWidget(note)
            bar.addLayout(right)
        # 오른쪽에 페이지 동작 버튼을 둘 수 있다 (예: 조건 입력의 설정·저장).
        # 하단에 두면 화면 키보드가 뜰 때 공간을 크게 잡아먹어 상단으로 올린다.
        if actions:
            bar.addSpacing(24)
            for i, widget in enumerate(actions):
                if i:
                    bar.addSpacing(12)
                bar.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)

        rule = QFrame()
        rule.setObjectName("TitleRule")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        outer.addLayout(bar)
        outer.addWidget(rule)


class SectionTitle(QWidget):
    """섹션 제목 — 성적서처럼 작은 accent 라벨 뒤로 실선을 흘린다."""

    def __init__(self, text):
        super().__init__()
        label = QLabel(text)
        label.setObjectName("Section")

        rule = QFrame()
        rule.setObjectName("SectionRule")

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(label)
        row.addWidget(rule, 1)
