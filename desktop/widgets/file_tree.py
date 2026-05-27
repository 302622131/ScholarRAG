"""文件树 widget：基于 QTreeView + QFileSystemModel，仅展示 PDF 文件。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeView, QFileSystemModel, QMenu


class FileTree(QTreeView):
    """论文文件夹浏览器，仅显示 PDF 文件。"""
    file_open_requested = Signal(str)   # 双击打开 PDF
    ingest_requested = Signal(str)      # 右键请求导入单个 PDF

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = QFileSystemModel()
        self._model.setReadOnly(True)
        self._model.setNameFilters(["*.pdf"])
        self._model.setNameFilterDisables(False)
        self.setModel(self._model)

        self.setColumnHidden(1, True)
        self.setColumnHidden(2, True)
        self.setColumnHidden(3, True)
        self.setHeaderHidden(True)
        self.setAnimated(True)
        self.setSelectionMode(QTreeView.ExtendedSelection)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        self._ingest_checker = None

    def set_ingest_checker(self, fn):
        """注入检查函数 fn(filepath: str) -> bool，返回 True 表示已入库。"""
        self._ingest_checker = fn

    def set_root_dir(self, path: str):
        if not path:
            return
        root = self._model.setRootPath(path)
        self.setRootIndex(root)
        self.expandToDepth(2)

    def current_project_dir(self) -> str:
        return self._model.rootPath()

    def _on_context_menu(self, pos):
        index = self.indexAt(pos)
        selected = self.selectedIndexes()

        selected_paths = []
        seen = set()
        for idx in selected:
            fp = self._model.filePath(idx)
            if fp not in seen and not self._model.isDir(idx):
                selected_paths.append(fp)
                seen.add(fp)

        if index.isValid() and index not in selected:
            fp = self._model.filePath(index)
            if not self._model.isDir(index):
                selected_paths = [fp]

        menu = QMenu(self)

        if index.isValid():
            filepath = self._model.filePath(index)
            if not self._model.isDir(index):
                menu.addAction("打开", lambda fp=filepath: self._open_file(fp))
                menu.addSeparator()

                pdf_files = [fp for fp in selected_paths if fp.lower().endswith(".pdf")]
                if pdf_files:
                    self._add_ingest_actions(menu, pdf_files)

        menu.exec(self.viewport().mapToGlobal(pos))

    def _add_ingest_actions(self, menu, pdf_files: list[str]):
        if not self._ingest_checker:
            # 无检查函数时仍显示导入选项
            label = f"导入知识库 ({len(pdf_files)} 篇)" if len(pdf_files) > 1 else "导入知识库"
            action = menu.addAction(label)
            action.triggered.connect(lambda: self._emit_ingest(pdf_files))
            return

        ingested = []
        not_ingested = []
        for fp in pdf_files:
            try:
                if self._ingest_checker(fp):
                    ingested.append(fp)
                else:
                    not_ingested.append(fp)
            except Exception:
                not_ingested.append(fp)

        if not_ingested:
            label = f"导入知识库 ({len(not_ingested)} 篇)" if len(not_ingested) > 1 else "导入知识库"
            action = menu.addAction(label)
            action.triggered.connect(lambda: self._emit_ingest(not_ingested))

        if ingested:
            label = f"已入库 ✓ ({len(ingested)} 篇)" if len(ingested) > 1 else "已入库 ✓"
            action = menu.addAction(label)
            action.setEnabled(False)

    def _emit_ingest(self, pdf_files: list[str]):
        for fp in pdf_files:
            self.ingest_requested.emit(fp)

    def _open_file(self, filepath: str):
        if self._model.isDir(self._model.index(filepath)):
            return
        self.file_open_requested.emit(filepath)

    def mouseDoubleClickEvent(self, event):
        index = self.indexAt(event.pos())
        if index.isValid():
            filepath = self._model.filePath(index)
            if not self._model.isDir(index):
                self.file_open_requested.emit(filepath)
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            for index in self.selectedIndexes():
                filepath = self._model.filePath(index)
                if not self._model.isDir(index):
                    self.file_open_requested.emit(filepath)
        super().keyPressEvent(event)
