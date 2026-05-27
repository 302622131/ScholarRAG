"""中间 Agent 对话面板：聊天界面 + Agent 调用逻辑。"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
)

from config import Settings
from desktop.services import Services
from desktop.widgets.chat_widget import ChatWidget
from desktop.workers import AgentChatWorker
from desktop.theme import ThemeManager


class AgentPanel(QWidget):
    """中间面板：聊天界面，连接 ResearchAgent。"""

    def __init__(self, settings: Settings, services: Services | None = None, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._services = services
        self._history: list[dict] = []
        self._worker: AgentChatWorker | None = None

        self._setup_ui()
        self._chat.update_stats(0, 0)

    def set_services(self, services: Services):
        self._services = services
        self._refresh_stats()

    def update_settings(self, settings: Settings):
        self._settings = settings

    def _setup_ui(self):
        theme = ThemeManager()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部按钮行
        top = QHBoxLayout()
        top.setContentsMargins(theme.spacing("sm"), theme.spacing("xs"), theme.spacing("sm"), theme.spacing("xs"))

        refresh_skills_btn = QPushButton("刷新技能")
        refresh_skills_btn.setStyleSheet(theme.stylesheet("button-secondary"))
        refresh_skills_btn.clicked.connect(self._refresh_skills)
        top.addWidget(refresh_skills_btn)

        top.addStretch()

        clear_btn = QPushButton("清空对话")
        clear_btn.setStyleSheet(theme.stylesheet("button-secondary"))
        clear_btn.clicked.connect(self._clear_chat)
        top.addWidget(clear_btn)

        layout.addLayout(top)

        # 聊天区域
        self._chat = ChatWidget()
        self._chat.message_sent.connect(self._on_message)
        self._chat.command_selected.connect(self._on_command)
        layout.addWidget(self._chat)

    def _refresh_stats(self):
        if self._services:
            papers = self._services.vector_store.list_papers()
            chunks = self._services.vector_store.count()
            self._chat.update_stats(len(papers), chunks)
            self._update_commands()
        else:
            self._chat.update_stats(0, 0)

    def _refresh_skills(self):
        """手动刷新技能：重新扫描目录并更新 agent prompt。"""
        if self._services:
            self._services.refresh_skills()
            self._update_commands()

    def _update_commands(self):
        """同步 skill 列表到指令按钮。"""
        if self._services and self._services.skill_loader:
            self._chat.set_commands(self._services.skill_loader.skills)
        else:
            self._chat.set_commands([])

    def _on_command(self, skill_name: str):
        """用户选择研究指令：skill body 注入 system prompt，不污染消息历史。"""
        if not self._services or not self._services.skill_loader:
            self._chat.add_message("assistant", "Skill 系统未初始化。")
            return

        if self._worker and self._worker.isRunning():
            return

        skill = self._services.skill_loader.get_skill(skill_name)
        if not skill:
            self._chat.add_message("assistant", f"未找到 skill: {skill_name}")
            return

        # 聊天区显示指令名
        self._chat.add_message("user", f"研究指令: {skill.name}")

        # 热加载 skill 并注入 system prompt（不进 history）
        self._services.refresh_skills()
        self._services.inject_skill(skill.body)
        self._chat.set_loading(True)

        self._worker = AgentChatWorker(
            agent=self._services.agent,
            user_message="请根据 system prompt 中的当前任务指引开始执行。",
            history=self._history,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_response)
        self._worker.start()

    def _on_message(self, text: str):
        if not self._services:
            self._chat.add_message("assistant", "服务未初始化，请先完成配置。")
            return

        # 防止并发：上一轮没结束前忽略新消息
        if self._worker and self._worker.isRunning():
            return

        # 热加载 skill 目录（不覆盖已注入的 skill body）
        self._services.refresh_skills()

        self._chat.set_loading(True)

        self._worker = AgentChatWorker(
            agent=self._services.agent,
            user_message=text,
            history=self._history,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_response)
        self._worker.start()

    def _on_progress(self, msg: str):
        pass  # loading indicator 已显示

    def _on_response(self, result: dict):
        self._chat.set_loading(False)

        answer = result.get("answer", "")
        tool_calls = result.get("tool_calls_made", [])

        self._chat.add_message("assistant", answer, tool_calls)

        # 使用 Agent 返回的完整历史（含 tool_use / tool_result / thinking）
        self._history = result.get("updated_history", [])

        # 入库类工具调用后刷新知识库统计和 BM25 索引
        if tool_calls:
            if any(t in ("ingest_paper", "ingest_all_papers") for t in tool_calls):
                self._refresh_stats()
                if self._services:
                    self._services.bm25_searcher.refresh()

        self._worker = None

    def _clear_chat(self):
        self._chat.clear()
        self._history = []
