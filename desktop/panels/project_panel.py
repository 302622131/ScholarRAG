"""左侧面板：PDF 文件夹浏览。"""

import os
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QLabel,
)

from desktop.widgets.file_tree import FileTree
from desktop.theme import ThemeManager


class ProjectPanel(QWidget):
    """左侧面板：选择论文文件夹，展示 PDF 文件列表。"""

    folder_opened = Signal(str)        # 文件夹路径
    file_open_requested = Signal(str)  # 请求在中间 PDF 阅读器打开
    ingest_requested = Signal(str)     # 请求导入 PDF 到知识库

    def __init__(self, parent=None):
        super().__init__(parent)
        self._folder_dir: str | None = None
        self._ingestion = None

        self._setup_ui()

    def set_ingestion(self, ingestion):
        """注入 IngestionPipeline，用于检查入库状态。"""
        self._ingestion = ingestion
        self._file_tree.set_ingest_checker(self._check_ingested)

    def _check_ingested(self, filepath: str) -> bool:
        if not self._ingestion:
            return False
        try:
            return self._ingestion.is_ingested(Path(filepath))
        except Exception:
            return False

    def _setup_ui(self):
        theme = ThemeManager()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部：文件夹标签 + 按钮
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(theme.spacing("sm"), theme.spacing("xs"), theme.spacing("sm"), theme.spacing("xs"))

        self._folder_label = QLabel("未打开文件夹")
        self._folder_label.setStyleSheet(
            f"font-weight: bold; color: {theme.color('text-primary')}; padding: 4px 0;"
        )
        toolbar.addWidget(self._folder_label)
        toolbar.addStretch()

        open_btn = QPushButton("打开文件夹")
        open_btn.setStyleSheet(theme.stylesheet("button-secondary"))
        open_btn.clicked.connect(self._open_folder)
        toolbar.addWidget(open_btn)

        ingest_btn = QPushButton("入库")
        ingest_btn.setStyleSheet(theme.stylesheet("button-primary"))
        ingest_btn.clicked.connect(self._browse_ingest)
        toolbar.addWidget(ingest_btn)

        layout.addLayout(toolbar)

        # 文件树
        self._file_tree = FileTree()
        self._file_tree.setStyleSheet(theme.stylesheet("tree"))
        self._file_tree.file_open_requested.connect(self.file_open_requested.emit)
        self._file_tree.ingest_requested.connect(self.ingest_requested.emit)
        layout.addWidget(self._file_tree)

    def _open_folder(self):
        path = QFileDialog.getExistingDirectory(self, "打开论文文件夹")
        if path:
            self.set_folder(path)

    def set_folder(self, path: str):
        """程序化设置文件夹路径。"""
        if os.path.isdir(path):
            self._folder_dir = path
            self._folder_label.setText(os.path.basename(path) or path)
            self._file_tree.set_root_dir(path)
            self.folder_opened.emit(path)

    def _browse_ingest(self):
        from config import settings
        start_dir = settings.papers_dir if settings.papers_dir else str(Path.home())
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择要入库的 PDF", start_dir, "PDF 文件 (*.pdf)")
        if filepath:
            self.ingest_requested.emit(filepath)

    @property
    def folder_dir(self) -> str | None:
        return self._folder_dir
