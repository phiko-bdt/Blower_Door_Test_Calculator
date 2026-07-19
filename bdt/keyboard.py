"""앱 내장 온스크린 키보드 — 터치스크린에서 입력창을 채운다.

물리 키보드가 없는 현장 단말용. 입력창(QLineEdit)에 포커스가 가면 화면 아래에
키보드가 뜨고, 숫자 칸이면 숫자 키패드, 텍스트 칸이면 한글/영문 키보드가 나온다.

Qt 가상 키보드(qtvirtualkeyboard)는 QML 앱에는 붙지만 이 위젯 앱(QtWidgets)에는
자동 팝업이 안 떠서, 앱이 직접 그린다. 한글은 초성·중성·종성을 조합하는
오토마타(HangulAutomaton)로 완성형 음절을 만든다.

숫자 칸 판별: 입력창에 property("numeric", True) 가 있으면 숫자 키패드.
"""

from PyQt6.QtWidgets import (QWidget, QPushButton, QGridLayout, QVBoxLayout,
                             QHBoxLayout, QLineEdit, QApplication)
from PyQt6.QtCore import Qt, pyqtSignal

# ── 한글 자모 테이블 ──────────────────────────────────────────
CHO = ['ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ',
       'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ']
JUNG = ['ㅏ', 'ㅐ', 'ㅑ', 'ㅒ', 'ㅓ', 'ㅔ', 'ㅕ', 'ㅖ', 'ㅗ', 'ㅘ',
        'ㅙ', 'ㅚ', 'ㅛ', 'ㅜ', 'ㅝ', 'ㅞ', 'ㅟ', 'ㅠ', 'ㅡ', 'ㅢ', 'ㅣ']
JONG = ['', 'ㄱ', 'ㄲ', 'ㄳ', 'ㄴ', 'ㄵ', 'ㄶ', 'ㄷ', 'ㄹ', 'ㄺ', 'ㄻ',
        'ㄼ', 'ㄽ', 'ㄾ', 'ㄿ', 'ㅀ', 'ㅁ', 'ㅂ', 'ㅄ', 'ㅅ', 'ㅆ', 'ㅇ',
        'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ']

CHO_IDX = {c: i for i, c in enumerate(CHO)}
JUNG_IDX = {c: i for i, c in enumerate(JUNG)}
JONG_IDX = {c: i for i, c in enumerate(JONG) if c}

JUNG_COMBINE = {('ㅗ', 'ㅏ'): 'ㅘ', ('ㅗ', 'ㅐ'): 'ㅙ', ('ㅗ', 'ㅣ'): 'ㅚ',
                ('ㅜ', 'ㅓ'): 'ㅝ', ('ㅜ', 'ㅔ'): 'ㅞ', ('ㅜ', 'ㅣ'): 'ㅟ',
                ('ㅡ', 'ㅣ'): 'ㅢ'}
JONG_COMBINE = {('ㄱ', 'ㅅ'): 'ㄳ', ('ㄴ', 'ㅈ'): 'ㄵ', ('ㄴ', 'ㅎ'): 'ㄶ',
                ('ㄹ', 'ㄱ'): 'ㄺ', ('ㄹ', 'ㅁ'): 'ㄻ', ('ㄹ', 'ㅂ'): 'ㄼ',
                ('ㄹ', 'ㅅ'): 'ㄽ', ('ㄹ', 'ㅌ'): 'ㄾ', ('ㄹ', 'ㅍ'): 'ㄿ',
                ('ㄹ', 'ㅎ'): 'ㅀ', ('ㅂ', 'ㅅ'): 'ㅄ'}
JUNG_SPLIT = {v: k for k, v in JUNG_COMBINE.items()}
JONG_SPLIT = {v: k for k, v in JONG_COMBINE.items()}

_JAMO = set(CHO) | set(JUNG) | set(JONG_IDX)


def is_jamo(ch):
    return ch in _JAMO


def _syllable(cho, jung, jong):
    """(초성idx, 중성idx, 종성idx)로 완성형 음절 문자."""
    return chr(0xAC00 + (cho * 21 + jung) * 28 + jong)


class HangulAutomaton:
    """자모를 받아 완성형 한글을 조합한다 (두벌식).

    add(jamo) / backspace() 는 (동작, 인자) 를 돌려준다. 동작:
      'update'  현재 조합 중인 마지막 글자를 인자 글자로 바꾼다.
      'new'     이전 글자는 확정, 인자 글자를 새로 덧붙인다.
      'split'   마지막 글자를 인자[0]로 바꾸고 인자[1]을 덧붙인다.
      'delete'  마지막 글자를 지운다 (조합 취소).
      'pass'    한글이 아니다 — 호출부가 그대로 삽입한다.
    상태가 비어 있으면(조합 중 아님) 자모는 'new' 로 시작한다.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.cho = self.jung = None
        self.jong = 0  # 0 = 종성 없음

    def _cur(self):
        """현재 조합 상태의 표시 글자."""
        if self.cho is not None and self.jung is not None:
            return _syllable(self.cho, self.jung, self.jong)
        if self.cho is not None:
            return CHO[self.cho]
        if self.jung is not None:
            return JUNG[self.jung]
        return ''

    def add(self, jamo):
        if jamo in JUNG_IDX:
            return self._add_vowel(jamo)
        if jamo in CHO_IDX or jamo in JONG_IDX:
            return self._add_consonant(jamo)
        return ('pass', jamo)

    def _add_consonant(self, c):
        composing = self.cho is not None or self.jung is not None
        # 완성 음절(초+중)에 종성을 붙일 수 있으면 붙인다
        if self.cho is not None and self.jung is not None:
            if self.jong == 0 and c in JONG_IDX:
                self.jong = JONG_IDX[c]
                return ('update', self._cur())
            # 종성이 있으면 겹받침 시도
            if self.jong != 0:
                pair = (JONG[self.jong], c)
                if pair in JONG_COMBINE:
                    self.jong = JONG_IDX[JONG_COMBINE[pair]]
                    return ('update', self._cur())
        # 그 외 — 이전 글자 확정, 새 초성 시작
        self.reset()
        self.cho = CHO_IDX.get(c)
        return ('new', c) if composing else ('new', c)

    def _add_vowel(self, v):
        # 초성만 있는 상태 → 초+중 음절
        if self.cho is not None and self.jung is None:
            self.jung = JUNG_IDX[v]
            return ('update', self._cur())
        # 초+중(+종) 상태
        if self.cho is not None and self.jung is not None:
            if self.jong == 0:
                # 겹모음 시도 (고+ㅏ→과)
                pair = (JUNG[self.jung], v)
                if pair in JUNG_COMBINE:
                    self.jung = JUNG_IDX[JUNG_COMBINE[pair]]
                    return ('update', self._cur())
                # 안 되면 새 모음 글자 시작
                self.reset()
                self.jung = JUNG_IDX[v]
                return ('new', v)
            # 종성이 있다 → 종성이 새 음절의 초성으로 넘어간다 (각+ㅏ→가가)
            jong_char = JONG[self.jong]
            if jong_char in JONG_SPLIT:      # 겹받침이면 뒤 자음만 넘어감
                keep, move = JONG_SPLIT[jong_char]
                self.jong = JONG_IDX[keep]
                finalized = self._cur()
                moved = move
            else:
                self.jong = 0
                finalized = self._cur()
                moved = jong_char
            new_char = _syllable(CHO_IDX[moved], JUNG_IDX[v], 0)
            self.reset()
            self.cho = CHO_IDX[moved]
            self.jung = JUNG_IDX[v]
            return ('split', (finalized, new_char))
        # 조합 중 아님 → 홀로 모음
        self.reset()
        self.jung = JUNG_IDX[v]
        return ('new', v)

    def backspace(self):
        """조합 중인 글자를 한 자모 되돌린다. 조합 아니면 'pass'."""
        if self.jong != 0:
            jong_char = JONG[self.jong]
            if jong_char in JONG_SPLIT:      # 겹받침 → 앞 자음만 남긴다
                self.jong = JONG_IDX[JONG_SPLIT[jong_char][0]]
            else:
                self.jong = 0
            return ('update', self._cur())
        if self.jung is not None:
            jung_char = JUNG[self.jung]
            if jung_char in JUNG_SPLIT:      # 겹모음 → 앞 모음만 남긴다
                self.jung = JUNG_IDX[JUNG_SPLIT[jung_char][0]]
                return ('update', self._cur())
            self.jung = None
            if self.cho is not None:
                return ('update', self._cur())
            self.reset()
            return ('delete', None)
        if self.cho is not None:
            self.reset()
            return ('delete', None)
        return ('pass', None)


# ── 키보드 위젯 ────────────────────────────────────────────────
# 두벌식 배열 (기본 / Shift)
_KO_ROWS = [
    list("ㅂㅈㄷㄱㅅㅛㅕㅑㅐㅔ"),
    list("ㅁㄴㅇㄹㅎㅗㅓㅏㅣ"),
    list("ㅋㅌㅊㅍㅠㅜㅡ"),
]
_KO_SHIFT = {'ㅂ': 'ㅃ', 'ㅈ': 'ㅉ', 'ㄷ': 'ㄸ', 'ㄱ': 'ㄲ', 'ㅅ': 'ㅆ',
             'ㅐ': 'ㅒ', 'ㅔ': 'ㅖ'}
_EN_ROWS = [
    list("qwertyuiop"),
    list("asdfghjkl"),
    list("zxcvbnm"),
]
# 문자·기호 레이어 오른쪽에 붙는 텐키 (넓은 가로폭 활용)
_TENKEY_ROWS = [list("789"), list("456"), list("123"), ['0', '.', '⌫']]
# 텍스트 칸에서 한/영 옆 버튼으로 여는 숫자·특수문자 레이어
_SYM_ROWS = [
    list("1234567890"),
    list("@#₩%&-+()/"),
    list(".,?!'\":;~"),
]


class OnScreenKeyboard(QWidget):
    """화면 아래에 붙는 온스크린 키보드. 포커스된 QLineEdit 에 입력한다."""

    done = pyqtSignal()   # 완료 → 키보드 닫기 요청

    def __init__(self):
        super().__init__()
        self.setObjectName("Keyboard")
        self._auto = HangulAutomaton()
        self._composing = False
        self._hangul = True     # 한글/영문 토글
        self._shift = False
        self._numeric = False   # 필드가 강제하는 숫자 키패드
        self._symbol = False    # 텍스트 칸에서 연 숫자·특수문자 레이어
        self._field = None      # attach() 로 붙인 현재 입력창
        self._editing = False   # 키보드 자신이 입력창을 고치는 중 (커서 감시 무시)

        self._grid_host = QVBoxLayout(self)
        self._grid_host.setContentsMargins(8, 6, 8, 8)
        self._grid_host.setSpacing(6)
        self._build()

    # ── 대상 입력창 ───────────────────────────────────────────
    def _target(self):
        w = QApplication.focusWidget()
        return w if isinstance(w, QLineEdit) else None

    def attach(self, field):
        """입력창의 커서 이동을 감시한다 — 조합 중 커서를 옮기면 리셋.

        조합 중(예: "서" 까지 입력) 사용자가 입력창을 탭해 커서를 다른 자리로
        옮기면, 다음 자모의 'update' 가 backspace 로 **커서 왼쪽의 엉뚱한
        글자**를 지운다. 커서가 움직이는 순간 조합을 확정(리셋)해 막는다.
        키보드 자신의 insert/backspace 도 커서를 움직이므로 _editing 플래그로
        구분한다.
        """
        if field is self._field:
            return
        if self._field is not None:
            try:
                self._field.cursorPositionChanged.disconnect(self._on_cursor_moved)
                self._field.selectionChanged.disconnect(self._on_cursor_moved)
            except (TypeError, RuntimeError):
                pass  # 필드가 이미 파괴됐거나 연결이 끊겨 있다
        self._field = field
        if field is not None:
            field.cursorPositionChanged.connect(self._on_cursor_moved)
            field.selectionChanged.connect(self._on_cursor_moved)

    def _on_cursor_moved(self, *_args):
        if not self._editing:
            self.reset_compose()

    def set_numeric(self, numeric):
        # 새 필드로 포커스가 옮겨질 때마다 문자 레이어로 돌아온다
        if numeric != self._numeric or self._symbol or self._shift:
            self._numeric = numeric
            self._symbol = False
            self._shift = False
            self._build()

    def reset_compose(self):
        self._auto.reset()
        self._composing = False

    # ── 키 처리 ───────────────────────────────────────────────
    def _key(self, ch):
        field = self._target()
        if not field:
            return
        if self._hangul and not self._numeric and is_jamo(ch):
            self._feed_hangul(field, ch)
        else:
            self.reset_compose()
            field.insert(ch)
        if self._shift:
            self._shift = False
            self._build()

    def _feed_hangul(self, field, jamo):
        action, arg = self._auto.add(jamo)
        self._editing = True
        try:
            if action == 'update':
                if self._composing:
                    field.backspace()
                field.insert(arg)
            elif action == 'new':
                field.insert(arg)
            elif action == 'split':
                field.backspace()
                field.insert(arg[0])
                field.insert(arg[1])
            else:                    # pass
                field.insert(jamo)
        finally:
            self._editing = False
        self._composing = True

    def _backspace(self):
        field = self._target()
        if not field:
            return
        self._editing = True
        try:
            if self._composing:
                action, arg = self._auto.backspace()
                if action == 'update':
                    field.backspace()
                    field.insert(arg)
                    return
                if action == 'delete':
                    field.backspace()
                    self._composing = False
                    return
            field.backspace()
        finally:
            self._editing = False

    def _toggle_lang(self):
        self.reset_compose()
        self._hangul = not self._hangul
        self._shift = False
        self._build()

    def _toggle_shift(self):
        self._shift = not self._shift
        self._build()

    def _toggle_symbol(self):
        self.reset_compose()
        self._symbol = not self._symbol
        self._shift = False
        self._build()

    def _space(self):
        field = self._target()
        if field:
            self.reset_compose()
            field.insert(" ")

    # ── 배열 그리기 ───────────────────────────────────────────
    def _clear(self):
        while self._grid_host.count():
            item = self._grid_host.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                self._drop_layout(item.layout())

    def _drop_layout(self, lay):
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                self._drop_layout(it.layout())

    def _btn(self, text, slot, kind=""):
        # QPushButton 은 '&' 를 니모닉 접두어로 먹으므로 표시용만 이스케이프.
        # 실제 입력 문자는 slot 이 원본을 그대로 넣는다.
        b = QPushButton(text.replace("&", "&&"))
        b.setObjectName("Key" + kind)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # 입력창 포커스를 뺏지 않게
        b.clicked.connect(slot)
        return b

    def _build(self):
        self._clear()
        if self._numeric:
            self._build_numeric()
        elif self._symbol:
            self._build_symbol()
        else:
            self._build_text()

    def _build_numeric(self):
        # 숫자 칸은 0~9 · 점 · 음수 부호 · 지우기를 한 줄로만 둔다 — 문자가
        # 없으니 아주 얇게. 음수 부호는 팬 보정식 절편이 음수로 나올 수 있어
        # 필요하다 (물리 키보드 없는 단말에서 유일한 입력 수단이다).
        # 확정/닫기는 헤더의 동작 버튼(저장 등)이 맡으므로 완료 키는 없다.
        r = QHBoxLayout()
        r.setSpacing(6)
        for ch in "0123456789.-":
            r.addWidget(self._btn(ch, lambda _=None, c=ch: self._key(c)))
        r.addWidget(self._btn("⌫", lambda: self._backspace()))
        self._grid_host.addLayout(r)

    def _tenkey_column(self):
        """오른쪽에 붙는 텐키. 넓은 가로폭을 채우고 숫자 입력을 빠르게 한다."""
        col = QVBoxLayout()
        col.setSpacing(5)
        for row in _TENKEY_ROWS:
            r = QHBoxLayout()
            r.setSpacing(5)
            for ch in row:
                if ch == "⌫":
                    r.addWidget(self._btn("⌫", lambda: self._backspace()))
                else:
                    r.addWidget(self._btn(ch, lambda _=None, c=ch: self._key(c)))
            col.addLayout(r)
        return col

    def _build_text(self):
        left = QVBoxLayout()
        left.setSpacing(5)
        rows = _KO_ROWS if self._hangul else _EN_ROWS
        for i, row in enumerate(rows):
            r = QHBoxLayout()
            r.setSpacing(5)
            if i == 2:           # 세 번째 줄 앞에 Shift
                r.addWidget(self._btn("▲", lambda: self._toggle_shift(),
                                      "Mod" + ("On" if self._shift else "")))
            for ch in row:
                label = ch
                if self._hangul and self._shift and ch in _KO_SHIFT:
                    label = _KO_SHIFT[ch]
                elif not self._hangul and self._shift:
                    label = ch.upper()
                r.addWidget(self._btn(label,
                                      lambda _=None, c=label: self._key(c)))
            if i == 2:           # 세 번째 줄 끝에 지우기
                r.addWidget(self._btn("⌫", lambda: self._backspace(), "Mod"))
            left.addLayout(r)
        # 맨 아랫줄: !#1(기호) · 한/영 · 스페이스 · 완료
        bottom = QHBoxLayout()
        bottom.setSpacing(5)
        bottom.addWidget(self._btn("!#1", lambda: self._toggle_symbol(), "Mod"))
        bottom.addWidget(self._btn("한/영", lambda: self._toggle_lang(), "Mod"))
        bottom.addWidget(self._btn("스페이스", lambda: self._space(), "Space"))
        bottom.addWidget(self._btn("완료", lambda: self.done.emit(), "Done"))
        left.addLayout(bottom)
        self._grid_host.addLayout(self._frame(left))

    def _build_symbol(self):
        left = QVBoxLayout()
        left.setSpacing(5)
        for i, row in enumerate(_SYM_ROWS):
            r = QHBoxLayout()
            r.setSpacing(5)
            for ch in row:
                r.addWidget(self._btn(ch, lambda _=None, c=ch: self._key(c)))
            if i == len(_SYM_ROWS) - 1:      # 마지막 줄 끝에 지우기
                r.addWidget(self._btn("⌫", lambda: self._backspace(), "Mod"))
            left.addLayout(r)
        # 맨 아랫줄: 가/A(문자로) · 스페이스 · 완료
        bottom = QHBoxLayout()
        bottom.setSpacing(5)
        bottom.addWidget(self._btn("가·A", lambda: self._toggle_symbol(), "Mod"))
        bottom.addWidget(self._btn("스페이스", lambda: self._space(), "Space"))
        bottom.addWidget(self._btn("완료", lambda: self.done.emit(), "Done"))
        left.addLayout(bottom)
        self._grid_host.addLayout(self._frame(left))

    def _frame(self, left):
        """왼쪽 문자 키보드 + 오른쪽 텐키를 한 줄에 배치."""
        outer = QHBoxLayout()
        outer.setSpacing(8)
        outer.addLayout(left, 3)
        outer.addLayout(self._tenkey_column(), 1)
        return outer
