"""知识库管理面板：查看、删除已入库论文。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QMessageBox, QTextEdit,
)
from src.vector_store import VectorStore
from src.bm25_search import BM25Searcher
from desktop.theme import ThemeManager


class PaperDetailDialog(QDialog):
    """论文详情弹窗。"""

    def __init__(self, paper: dict, chunks: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle(paper.get("paper_title", "详情"))
        self.resize(600, 450)

        theme = ThemeManager()
        layout = QVBoxLayout(self)

        title = QLabel(paper.get("paper_title", "未知"))
        title.setFont(theme.font("font-heading"))
        title.setWordWrap(True)
        title.setStyleSheet(f"color: {theme.color('text-primary')};")
        layout.addWidget(title)

        arxiv_id = paper.get("arxiv_id", "")
        source = paper.get("source", "")
        info = QLabel(f"arxiv: {arxiv_id or '无'}    源文件: {source}")
        info.setStyleSheet(f"color: {theme.color('text-tertiary')};")
        layout.addWidget(info)

        layout.addWidget(QLabel(f"共 {len(chunks)} 个分块:"))

        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setFont(theme.font("font-mono"))
        lines = []
        for c in chunks[:20]:
            text = c["text"][:200].replace("\n", " ")
            page = c["metadata"].get("page_number", "?")
            section = c["metadata"].get("section", "")
            sec = f" [{section}]" if section else ""
            lines.append(f"[第{page}页{sec}] {text}...")
        preview.setText("\n\n".join(lines))
        layout.addWidget(preview)

        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet(theme.stylesheet("button-secondary"))
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)


class KnowledgeDialog(QDialog):
    """知识库管理弹窗。"""

    def __init__(self, vector_store: VectorStore,
                 bm25: BM25Searcher | None = None, parent=None):
        super().__init__(parent)
        self._vector_store = vector_store
        self._bm25 = bm25

        self.setWindowTitle("知识库管理")
        self.resize(750, 500)

        self._setup_ui()
        self._load()

    def _setup_ui(self):
        theme = ThemeManager()
        layout = QVBoxLayout(self)

        # 顶部按钮
        top = QHBoxLayout()
        top.addStretch()
        refresh_btn = QPushButton("刷新")
        refresh_btn.setStyleSheet(theme.stylesheet("button-secondary"))
        refresh_btn.clicked.connect(self._load)
        top.addWidget(refresh_btn)
        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet(theme.stylesheet("button-secondary"))
        close_btn.clicked.connect(self.close)
        top.addWidget(close_btn)
        layout.addLayout(top)

        # 表格
        self._table = QTableWidget()
        self._table.setStyleSheet(theme.stylesheet("table"))
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["标题", "arxiv ID", "分块", "源文件"])
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.doubleClicked.connect(self._show_detail)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        layout.addWidget(self._table)

        # 底部统计 + 操作
        bottom = QHBoxLayout()
        self._stats = QLabel()
        self._stats.setStyleSheet(f"color: {theme.color('text-tertiary')};")
        bottom.addWidget(self._stats)
        bottom.addStretch()

        del_btn = QPushButton("删除选中")
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.color('danger')};
                color: white;
                border: none;
                padding: 6px 14px;
                border-radius: {theme.radius('sm')}px;
            }}
            QPushButton:hover {{ background-color: #dc2626; }}
        """)
        del_btn.clicked.connect(self._delete_selected)
        bottom.addWidget(del_btn)

        detail_btn = QPushButton("查看详情")
        detail_btn.setStyleSheet(theme.stylesheet("button-secondary"))
        detail_btn.clicked.connect(self._show_detail)
        bottom.addWidget(detail_btn)
        layout.addLayout(bottom)

    def _load(self):
        self._papers = self._vector_store.list_papers()
        chunks_total = self._vector_store.count()
        self._stats.setText(f"共 {len(self._papers)} 篇论文，{chunks_total} 个分块")

        self._table.setRowCount(len(self._papers))
        for i, p in enumerate(self._papers):
            self._table.setItem(i, 0, QTableWidgetItem(p.get("paper_title", "未知")))
            self._table.setItem(i, 1, QTableWidgetItem(p.get("arxiv_id", "")))
            self._table.setItem(i, 2, QTableWidgetItem(p.get("chunk_total", "0")))
            self._table.setItem(i, 3, QTableWidgetItem(p.get("source", "")))

    def _get_selected_paper(self) -> dict | None:
        row = self._table.currentRow()
        if 0 <= row < len(self._papers):
            return self._papers[row]
        return None

    def _show_detail(self):
        paper = self._get_selected_paper()
        if not paper:
            return
        pid = paper.get("paper_id", "")
        chunks = self._vector_store.get_paper_chunks(pid)
        dlg = PaperDetailDialog(paper, chunks, self)
        dlg.exec()

    def _delete_selected(self):
        paper = self._get_selected_paper()
        if not paper:
            return
        title = paper.get("paper_title", "未知")
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除论文 '{title}' 吗？\n\n这将移除其所有分块，但不会删除原始 PDF 文件。",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            pid = paper.get("paper_id", "")
            count = self._vector_store.delete_paper(pid)
            if count > 0:
                if self._bm25:
                    self._bm25.refresh()
                self._load()
