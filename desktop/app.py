"""主窗口：三栏布局（PDF 列表 | PDF 阅读器 | Agent 对话）。"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QMessageBox,
)
from PySide6.QtGui import QAction

from config import Settings, settings as global_settings
from desktop.services import Services, init_services
from desktop.panels.project_panel import ProjectPanel
from desktop.panels.agent_panel import AgentPanel
from desktop.widgets.pdf_reader import PdfReader
from desktop.workers import IngestWorker
from desktop.dialogs.settings_dialog import SettingsDialog
from desktop.dialogs.knowledge_dialog import KnowledgeDialog
from desktop.theme import ThemeManager


class MainWindow(QMainWindow):
    """RAG Research IDE 主窗口。"""

    def __init__(self, settings: Settings, services: Services | None = None):
        super().__init__()
        self._settings = settings
        self._services = services

        self.setWindowTitle("RAG Research IDE")
        self.resize(1400, 850)

        self._setup_menu()
        self._setup_ui()
        self._setup_statusbar()

        if self._services:
            self._agent_panel.set_services(self._services)
            self._project_panel.set_ingestion(self._services.ingestion)

    # ── 菜单 ──

    def _setup_menu(self):
        menubar = self.menuBar()

        # 工具
        tools_menu = menubar.addMenu("工具(&T)")

        kb_action = QAction("知识库管理(&K)...", self)
        kb_action.triggered.connect(self._open_knowledge_dialog)
        tools_menu.addAction(kb_action)

        # 设置
        settings_menu = menubar.addMenu("设置(&S)")

        config_action = QAction("模型配置(&C)...", self)
        config_action.triggered.connect(self._open_settings)
        settings_menu.addAction(config_action)

        # 帮助
        help_menu = menubar.addMenu("帮助(&H)")

        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    # ── 三栏布局：PDF 列表 | PDF 阅读器 | Agent ──

    def _setup_ui(self):
        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setHandleWidth(3)
        self._splitter.setStyleSheet(ThemeManager().stylesheet("splitter"))

        # 左侧：PDF 列表
        self._project_panel = ProjectPanel()
        self._project_panel.folder_opened.connect(self._on_folder_opened)
        self._project_panel.file_open_requested.connect(self._open_pdf)
        self._project_panel.ingest_requested.connect(self._on_ingest_file)
        self._splitter.addWidget(self._project_panel)

        # 中间：PDF 阅读器
        self._pdf_reader = PdfReader()
        self._splitter.addWidget(self._pdf_reader)

        # 右侧：Agent 对话
        self._agent_panel = AgentPanel(self._settings, self._services)
        self._splitter.addWidget(self._agent_panel)

        self._splitter.setSizes([240, 560, 400])
        self.setCentralWidget(self._splitter)

    # ── 状态栏 ──

    def _setup_statusbar(self):
        self.statusBar().setStyleSheet(
            f"QStatusBar {{ color: {ThemeManager().color('text-tertiary')}; "
            f"font-size: 11px; padding: 2px 8px; }}"
        )
        self._update_statusbar()

    def _update_statusbar(self):
        model = self._settings.anthropic_model
        folder = self._project_panel.folder_dir or "无"
        self.statusBar().showMessage(f"文件夹: {folder}    模型: {model}")

    # ── PDF 操作 ──

    def _open_pdf(self, filepath: str):
        self._pdf_reader.open_pdf(filepath)

    # ── 入库 ──

    def _on_ingest_file(self, filepath: str):
        if not self._services:
            return
        self._ingest_worker = IngestWorker(self._services.ingestion, Path(filepath))
        self._ingest_worker.progress.connect(lambda msg: self.statusBar().showMessage(msg, 3000))
        self._ingest_worker.finished.connect(lambda ok, pid, fname: self._on_ingest_done(ok, pid, fname))
        self._ingest_worker.start()

    def _on_ingest_done(self, ok: bool, pid_or_msg: str, filename: str):
        if ok:
            self.statusBar().showMessage(f"入库完成: {filename}", 5000)
        else:
            if "已存在" in pid_or_msg:
                QMessageBox.information(
                    self, "重复导入",
                    f"该论文已在向量数据库中，无需重复导入。\n\n文件: {filename}")
            else:
                self.statusBar().showMessage(f"入库失败: {filename} — {pid_or_msg}", 5000)
        self._services.bm25_searcher.refresh()

    # ── 文件夹 ──

    def _on_folder_opened(self, path: str):
        self.setWindowTitle(f"RAG Research IDE - {path}")
        self._update_statusbar()

    # ── 知识库管理 ──

    def _open_knowledge_dialog(self):
        if not self._services:
            return
        dlg = KnowledgeDialog(
            vector_store=self._services.vector_store,
            bm25=self._services.bm25_searcher,
            parent=self,
        )
        dlg.exec()
        self._agent_panel.set_services(self._services)

    # ── 设置 ──

    def _open_settings(self):
        old_embedding = self._settings.embedding_model_name
        dlg = SettingsDialog(self._settings, self,
                             skill_loader=self._services.skill_loader if self._services else None)
        if dlg.exec():
            self._settings = dlg.get_settings()
            new_embedding = self._settings.embedding_model_name

            if old_embedding != new_embedding and self._services and self._services.vector_store.count() > 0:
                reply = QMessageBox.question(
                    self, "嵌入模型已变更",
                    "嵌入模型已变更。新旧模型的向量维度不同，需要清空现有知识库数据并重新导入论文。\n\n"
                    "是否继续？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    self._services.vector_store.reset()
                    self._services.bm25_searcher.refresh()
                    self.statusBar().showMessage("知识库已清空，请重新导入论文。", 5000)
                else:
                    self._settings.embedding_model_name = old_embedding
                    self._settings.save()
                    self._update_statusbar()
                    return

            self._update_statusbar()
            self._agent_panel.update_settings(self._settings)
            self._rebuild_services()

    def _rebuild_services(self):
        try:
            self._services = init_services(self._settings)
            self._agent_panel.set_services(self._services)
            self._project_panel.set_ingestion(self._services.ingestion)
        except Exception as e:
            QMessageBox.warning(
                self, "服务初始化失败",
                f"无法使用新配置初始化服务:\n{e}\n\n请检查 API Key 和 Base URL 是否正确。")

    def _show_about(self):
        QMessageBox.about(
            self, "关于 RAG Research IDE",
            "RAG Research IDE\n\n"
            "基于检索增强生成的科研论文助手\n"
            "支持论文入库、PDF 阅读和智能对话\n\n"
            "技术栈: PySide6 + ChromaDB + sentence-transformers")

    # ── 关闭 ──

    def closeEvent(self, event):
        self._settings.save()
        super().closeEvent(event)
