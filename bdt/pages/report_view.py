"""성적서 화면 — 발행한 PDF 를 앱 안에서 그대로 보여준다.

예전엔 성적서를 외부 뷰어(evince)로 띄웠다. 앱이 전체화면인 현장 단말에서
남의 창이 위를 덮고, 작업자가 그 창을 닫아야 앱으로 돌아올 수 있었다.
이제 시험의 마지막 화면까지 앱 안에 둔다.

PDF 를 직접 그리지 않고 pdftoppm 이 렌더한 PNG 한 장을 띄운다. 성적서는
1페이지 고정이고 poppler 는 이미 깔려 있어(성적서 검증에 쓴다) 의존성이
늘지 않는다. 렌더는 tasks.reporting 이 백그라운드에서 미리 해 둔다 —
여기서 하면 화면 전환이 1초쯤 멈춘다.

PDF 파일 자체는 예전과 같은 자리에 그대로 저장된다 (report.pdf).
"""

import os
import shutil

from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QScroller,
    QFrame,
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap

from bdt import paths
from bdt.widgets import alert, toast
from bdt.pages.share_panel import SharePanel


class _UsbCopyTask(QThread):
    """USB 복사를 백그라운드에서 수행한다.

    GUI 스레드에서 copy2 + os.sync() 를 부르면 느린 USB 에서 수 초간 화면이
    통째로 멈추고 아무 피드백이 없다 — 작업자가 멈춘 줄 알고 USB 를 뽑으면
    sync 가 막으려던 바로 그 사고(깨진 파일)가 난다. 복사 동안 버튼은
    '복사 중…' 으로 잠그고, 결과는 done 시그널로 알린다.
    """

    done = pyqtSignal(list, list)  # (복사된 마운트 이름들, 실패 설명들)

    def __init__(self, pdf_path, name, mounts, parent=None):
        super().__init__(parent)
        self._pdf_path = pdf_path
        self._name = name
        self._mounts = mounts

    def run(self):
        copied, failed = [], []
        for mount in self._mounts:
            # 같은 이름이 이미 있으면 덮지 않고 번호를 붙인다 (보관함과 동일)
            dest = os.path.join(mount, self._name)
            stem, ext = os.path.splitext(dest)
            n = 2
            while os.path.exists(dest):
                dest = f"{stem}({n}){ext}"
                n += 1
            try:
                shutil.copy2(self._pdf_path, dest)
                # 뽑을 때 파일이 깨지지 않게 캐시를 디스크로 내린다
                os.sync()
                copied.append(os.path.basename(mount))
            except OSError as exc:
                failed.append(f"{os.path.basename(mount)} ({exc})")
        self.done.emit(copied, failed)


class ReportPage(QWidget):
    """성적서 이미지 + 화면맞춤/100% 전환 + 새 시험."""

    restart = pyqtSignal()  # 새 시험 → 조건 입력부터 다시

    def __init__(self, png_path=None, pdf_path=None, archive_path=None):
        super().__init__()
        self._png_path = png_path or paths.REPORT_PNG
        self._pdf_path = pdf_path or paths.REPORT_PDF
        self._archive_path = archive_path
        self._pixmap = QPixmap(self._png_path)
        self._fit = True   # 처음엔 한 장이 다 보이게

        # 페이지 제목을 따로 두지 않는다. 성적서 지면 자체가 "기밀성능 시험
        # 성적서" 라는 제목을 크게 달고 있어 중복이고, 그 100px 을 성적서에
        # 주는 편이 낫다 (A4 세로를 800px 화면에 넣으면 여유가 없다).
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 14, 40, 14)
        root.setSpacing(10)

        # ── 성적서 이미지(좌) + 폰 공유 QR(우) ─────────────────
        # A4 세로 지면이라 가로로 여백이 남는다 — 그 오른쪽에 QR 을 둔다.
        self.sheet = QLabel()
        self.sheet.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setWidget(self.sheet)
        # '100% 로 보기'에서 지면을 손가락 드래그로 이동할 수 있게 한다 —
        # 폭 10px 스크롤바 핸들은 터치로 잡을 수 없다.
        QScroller.grabGesture(self.scroll.viewport(),
                              QScroller.ScrollerGestureType.LeftMouseButtonGesture)

        # 폰 공유 QR 카드 — 스스로 2초마다 AP·네트워크 상태를 갱신한다.
        self.share = SharePanel(self)
        content = QHBoxLayout()
        content.setSpacing(16)
        content.addWidget(self.scroll, 1)
        content.addWidget(self.share)
        root.addLayout(content, 1)

        # ── 하단 줄 ────────────────────────────────────────────
        self.zoom_button = QPushButton("100% 로 보기")
        self.zoom_button.setObjectName("Secondary")
        self.zoom_button.setMinimumWidth(150)
        self.zoom_button.clicked.connect(self._toggle_zoom)

        # 저장 위치 — 작업자가 성적서를 어디서 찾는지가 이 화면의 핵심 정보다.
        # 예전엔 회색 힌트 한 줄이라 눈에 안 띄었다. 캡션(accent) + 경로(진한
        # 잉크)로 두 줄로 또렷하게 보여준다.
        saved_caption = QLabel("성적서 저장 위치")
        saved_caption.setObjectName("StatName")
        self.saved_label = QLabel(self._where_saved())
        self.saved_label.setObjectName("SavedPath")
        self.saved_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        saved_block = QVBoxLayout()
        saved_block.setSpacing(1)
        saved_block.addWidget(saved_caption)
        saved_block.addWidget(self.saved_label)

        # USB 복사 — USB 저장소가 꽂혀 있을 때만 뜬다. 성적서 화면이 떠 있는
        # 동안 꽂아도 나타나게 주기적으로 확인한다.
        self.usb_button = QPushButton("USB 로 복사")
        self.usb_button.setObjectName("Secondary")
        self.usb_button.setMinimumWidth(150)
        self.usb_button.clicked.connect(self._copy_to_usb)
        self.usb_button.setVisible(False)

        restart_button = QPushButton("새 시험 시작")
        restart_button.setMinimumWidth(180)
        restart_button.clicked.connect(self.restart.emit)

        bottom = QHBoxLayout()
        bottom.setSpacing(16)
        bottom.addWidget(self.zoom_button)
        bottom.addLayout(saved_block)
        bottom.addStretch(1)
        bottom.addWidget(self.usb_button)
        bottom.addWidget(restart_button)
        root.addLayout(bottom)

        # PDF 가 없으면(렌더 실패해도 PDF 는 있어야 정상) USB 복사도 막는다
        self._can_copy = os.path.exists(self._pdf_path)
        self._copy_task = None  # 실행 중인 USB 복사 (중복 실행 방지)
        # USB 가 '새로 꽂히는' 순간에만 안내 토스트를 띄우려고 직전 상태를 든다
        self._usb_present = False
        # USB 유무를 2초마다 확인 (화면 떠 있는 동안 꽂아도 반영되게). 공유 QR
        # 은 SharePanel 이 자체 타이머로 본다.
        self._poll = QTimer(self)
        self._poll.timeout.connect(self._refresh_usb)
        self._poll.start(2000)
        self._refresh_usb()

        if self._pixmap.isNull():
            # 렌더가 없거나 깨졌다 — 성적서 PDF 는 만들어졌으므로 시험은
            # 실패가 아니다. 화면에서만 못 보여준다는 것을 분명히 알린다.
            self.sheet.setText(
                "성적서를 화면에 표시하지 못했습니다.\n\n"
                "성적서는 바탕화면 폴더에서 확인할 수 있습니다.")
            self.sheet.setObjectName("Message")
            self.zoom_button.setEnabled(False)

    def _where_saved(self):
        """성적서를 어디서 찾는지 — 바탕화면 보관함 기준으로 알린다.

        작업자가 찾는 건 저장소 안의 report.pdf 가 아니라 바탕화면의 사본이다
        (report.pdf 는 다음 시험이 덮어쓴다). 폴더 구분자를 ' › ' 로 바꿔
        '바탕화면 › 결과보고서 › …' 처럼 어디를 열어야 하는지 바로 읽히게 한다.
        """
        if not self._archive_path:
            # 보관 실패 폴백 — 최소한 PDF 원본 자리라도 알린다
            return self._pdf_path
        try:
            rel = os.path.relpath(self._archive_path, paths.DESKTOP_DIR)
            crumbs = ["바탕화면"] + rel.split(os.sep)
        except ValueError:
            crumbs = self._archive_path.split(os.sep)
        # NanumSquare 에 '›'(U+203A) 글리프가 없어 공백으로 렌더된다 — '/' 사용
        return "  /  ".join(crumbs)

    # ── USB 복사 ──────────────────────────────────────────────
    def _refresh_usb(self):
        """USB 유무를 확인해 복사 버튼을 켜고 끈다. 새로 꽂히면 안내 토스트."""
        self._usb = paths.usb_mounts() if self._can_copy else []
        present = bool(self._usb)
        # 버튼을 먼저 보이게 해 위치가 잡히면, 토스트를 그 버튼 위에 붙인다.
        self.usb_button.setVisible(present)
        # 없다가 새로 감지된 순간에만 한 번 알린다. 화면이 뜨기 전(__init__ 중
        # 첫 확인)이나 폴링마다 반복해 뜨지 않도록 isVisible 과 직전 상태로 건다.
        if present and not self._usb_present and self.isVisible():
            toast(self, "USB 연결 감지됨",
                  "복사 버튼을 누르면 성적서가 복사됩니다.",
                  anchor=self.usb_button)
        self._usb_present = present

    def _copy_dest_name(self):
        """USB 에 남길 파일 이름 — 보관본과 같은 뜻있는 이름."""
        if self._archive_path:
            return os.path.basename(self._archive_path)
        return "기밀성능시험_성적서.pdf"

    def _copy_to_usb(self):
        """성적서 PDF 를 꽂힌 USB(들)에 복사한다 (백그라운드, _UsbCopyTask).

        복사가 끝났거나 실패했음을 알린다 — USB 는 뽑으면 그만이라 결과를
        분명히 알려야 작업자가 안심하고 뽑는다.
        """
        if self._copy_task is not None and self._copy_task.isRunning():
            return
        mounts = paths.usb_mounts()
        if not mounts:
            # 버튼을 누르는 사이 뽑혔다
            self._refresh_usb()
            alert(self, "USB 없음", "USB 저장소가 연결돼 있지 않습니다.")
            return

        self.usb_button.setEnabled(False)
        self.usb_button.setText("복사 중…")
        # 새 시험으로 넘어가 이 페이지가 파괴돼도 복사는 끝까지 가도록 창을
        # 부모로 둔다. 결과 알림(done→bound method)은 페이지가 살아 있을
        # 때만 온다 — 파괴된 수신자로 가는 시그널은 Qt 가 자동 해제한다.
        task = _UsbCopyTask(self._pdf_path, self._copy_dest_name(), mounts,
                            parent=self.window())
        task.done.connect(self._on_copy_done)
        task.finished.connect(task.deleteLater)
        self._copy_task = task
        task.start()

    def _on_copy_done(self, copied, failed):
        self._copy_task = None
        self.usb_button.setEnabled(True)
        self.usb_button.setText("USB 로 복사")
        name = self._copy_dest_name()
        if copied and not failed:
            where = ", ".join(copied)
            alert(self, "USB 복사 완료",
                  f"성적서를 USB 에 복사했습니다.\n\n"
                  f"저장 위치: {where}\n파일 이름: {name}\n\n"
                  "USB 를 안전하게 뽑아도 됩니다.")
        elif copied and failed:
            alert(self, "일부만 복사됨",
                  f"복사됨: {', '.join(copied)}\n실패: {', '.join(failed)}")
        else:
            alert(self, "USB 복사 실패",
                  "성적서를 USB 에 복사하지 못했습니다.\n\n"
                  f"{', '.join(failed)}\n\n"
                  "USB 가 쓰기 금지(잠금)이거나 공간이 부족할 수 있습니다.")

    # ── 확대 ──────────────────────────────────────────────────
    def _toggle_zoom(self):
        self._fit = not self._fit
        self.zoom_button.setText("100% 로 보기" if self._fit else "화면에 맞추기")
        self._render()

    def _render(self):
        """현재 모드에 맞춰 이미지를 그린다.

        렌더는 300dpi 라 화면보다 훨씬 크다. '화면맞춤'은 뷰포트에 맞춰 줄이고,
        '100%'는 A4 를 원래 크기(96dpi 환산)로 보여준다 — 표의 작은 글씨를
        확인할 때 쓴다.
        """
        if self._pixmap.isNull():
            return
        if self._fit:
            size = self.scroll.viewport().size()
            scaled = self._pixmap.scaled(
                size, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
        else:
            # 300dpi 렌더 → 96dpi 화면 크기로 (약 1/3)
            scaled = self._pixmap.scaledToWidth(
                int(self._pixmap.width() * 96 / 300),
                Qt.TransformationMode.SmoothTransformation)
        self.sheet.setPixmap(scaled)
        self.sheet.resize(scaled.size())

    def resizeEvent(self, event):
        # 화면맞춤일 때만 창 크기를 따라간다 (100% 는 고정 배율이 의미다)
        super().resizeEvent(event)
        if self._fit:
            self._render()

    def showEvent(self, event):
        super().showEvent(event)
        self._render()
