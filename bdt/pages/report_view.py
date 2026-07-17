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

from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap

from bdt import paths


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

        # ── 성적서 이미지 ──────────────────────────────────────
        self.sheet = QLabel()
        self.sheet.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sheet.setObjectName("ReportSheet")

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setWidget(self.sheet)
        root.addWidget(self.scroll, 1)

        # ── 하단 줄 ────────────────────────────────────────────
        self.zoom_button = QPushButton("100% 로 보기")
        self.zoom_button.setObjectName("Secondary")
        self.zoom_button.setMinimumHeight(48)
        self.zoom_button.setMinimumWidth(150)
        self.zoom_button.clicked.connect(self._toggle_zoom)

        self.saved_label = QLabel(self._where_saved())
        self.saved_label.setObjectName("Hint")

        restart_button = QPushButton("새 시험 시작")
        restart_button.setMinimumHeight(48)
        restart_button.setMinimumWidth(180)
        restart_button.clicked.connect(self.restart.emit)

        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        bottom.addWidget(self.zoom_button)
        bottom.addSpacing(8)
        bottom.addWidget(self.saved_label)
        bottom.addStretch(1)
        bottom.addWidget(restart_button)
        root.addLayout(bottom)

        if self._pixmap.isNull():
            # 렌더가 없거나 깨졌다 — 성적서 PDF 는 만들어졌으므로 시험은
            # 실패가 아니다. 화면에서만 못 보여준다는 것을 분명히 알린다.
            self.sheet.setText(
                "성적서를 화면에 표시하지 못했습니다.\n\n"
                f"PDF 파일은 저장돼 있습니다: {self._pdf_path}")
            self.sheet.setObjectName("Message")
            self.zoom_button.setEnabled(False)

    def _where_saved(self):
        """성적서를 어디서 찾는지 — 바탕화면 보관함 기준으로 알린다.

        작업자가 찾는 건 저장소 안의 report.pdf 가 아니라 바탕화면의 사본이다
        (report.pdf 는 다음 시험이 덮어쓴다).
        """
        if not self._archive_path:
            return f"PDF 저장됨 · {self._pdf_path}"
        try:
            shown = os.path.relpath(self._archive_path, paths.DESKTOP_DIR)
        except ValueError:
            shown = self._archive_path
        return f"바탕화면에 보관됨 · {shown}"

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
