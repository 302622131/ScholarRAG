"""PDF 阅读器：基于 PyMuPDF 渲染全部页面，Ctrl+滚轮缩放。"""

from pathlib import Path

import fitz
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
    QSizePolicy,
)

from desktop.theme import ThemeManager


class PdfReader(QWidget):
    """PDF 阅读器：顶部工具栏 + 全部页面垂直连续渲染。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc = None
        self._zoom = 1.0

        theme = ThemeManager()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(theme.spacing("sm"), theme.spacing("xs"),
                                   theme.spacing("sm"), theme.spacing("xs"))

        self._title_label = QLabel("未打开文件")
        self._title_label.setMaximumWidth(300)
        self._title_label.setStyleSheet(
            f"color: {theme.color('text-primary')}; font-weight: bold;"
        )
        self._title_label.setToolTip("")
        toolbar.addWidget(self._title_label)

        toolbar.addStretch()

        self._page_label = QLabel("")
        self._page_label.setStyleSheet(f"color: {theme.color('text-tertiary')};")
        toolbar.addWidget(self._page_label)

        layout.addLayout(toolbar)

        # 滚动区域
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setAlignment(Qt.AlignHCenter)
        self._scroll.setStyleSheet(
            f"background-color: {theme.color('bg-secondary')}; border: none;"
        )

        self._page_container = QWidget()
        self._page_container.setStyleSheet("background: transparent;")
        self._page_layout = QVBoxLayout(self._page_container)
        self._page_layout.setContentsMargins(0, 0, 0, 0)
        self._page_layout.setSpacing(4)
        self._page_layout.setAlignment(Qt.AlignHCenter)
        self._scroll.setWidget(self._page_container)

        layout.addWidget(self._scroll, stretch=1)

        # Ctrl+滚轮缩放（事件过滤器）
        self._scroll.viewport().installEventFilter(self)

    def open_pdf(self, filepath: str):
        """打开并渲染全部 PDF 页面。"""
        self._doc = fitz.open(filepath)
        self._zoom = 1.0
        name = Path(filepath).name
        self._title_label.setText(name)
        self._title_label.setToolTip(name)
        self._render_all()
        self._scroll.verticalScrollBar().setValue(0)

    def _clear_pages(self):
        while self._page_layout.count():
            item = self._page_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _render_all(self):
        if not self._doc:
            return
        self._clear_pages()

        mat = fitz.Matrix(self._zoom, self._zoom)
        for i in range(self._doc.page_count):
            pix = self._doc[i].get_pixmap(matrix=mat)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            page_lbl = QLabel()
            page_lbl.setAlignment(Qt.AlignCenter)
            page_lbl.setPixmap(QPixmap.fromImage(img))
            page_lbl.setFixedSize(pix.width, pix.height)
            self._page_layout.addWidget(page_lbl)

        self._page_label.setText(f"共 {self._doc.page_count} 页")

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj is self._scroll.viewport() and event.type() == QEvent.Wheel:
            if event.modifiers() & Qt.ControlModifier:
                delta = event.angleDelta().y()
                if delta > 0:
                    self._zoom = min(4.0, self._zoom + 0.15)
                elif delta < 0:
                    self._zoom = max(0.25, self._zoom - 0.15)
                self._render_all()
                return True
        return super().eventFilter(obj, event)
