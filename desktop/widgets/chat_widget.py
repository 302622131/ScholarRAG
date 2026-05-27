"""聊天消息展示与输入 widget。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
    QTextEdit, QPushButton, QFrame, QSizePolicy, QComboBox,
)

from desktop.theme import ThemeManager


class _InputContainer(QWidget):
    """输入区容器，将发送按钮固定在右下角."""

    def __init__(self, input_widget: QTextEdit, send_btn: QPushButton, parent=None):
        super().__init__(parent)
        self._btn = send_btn
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(input_widget)
        self._btn.setParent(self)
        self._btn.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        margin = 8
        self._btn.move(
            self.width() - self._btn.width() - margin,
            self.height() - self._btn.height() - margin,
        )


class MessageBubble(QFrame):
    """单条聊天消息气泡。"""

    def __init__(self, role: str, content: str, tool_calls: list[str] | None = None,
                 parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

        theme = ThemeManager()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # 角色标签
        role_label = QLabel("You" if role == "user" else "Assistant")
        role_font = theme.font("font-heading")
        role_label.setFont(role_font)
        role_label.setStyleSheet(f"color: {theme.color('text-primary')}; background: transparent;")
        layout.addWidget(role_label)

        # 内容 — 将纯文本换行转为 HTML 段落
        if not content.startswith('<'):
            paragraphs = content.split('\n\n')
            html = ''.join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs)
        else:
            html = content
        content_label = QLabel(html)
        content_label.setWordWrap(True)
        content_label.setTextFormat(Qt.RichText)
        content_label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        content_label.setOpenExternalLinks(True)
        content_label.setStyleSheet(f"color: {theme.color('text-secondary')}; background: transparent;")
        layout.addWidget(content_label)

        # 工具调用
        if tool_calls:
            tc_label = QLabel(f"<i>调用工具: {', '.join(tool_calls)}</i>")
            tc_label.setStyleSheet(
                f"color: {theme.color('text-tertiary')}; font-size: {theme.typo_spec('font-small')['size']}px; background: transparent;"
            )
            layout.addWidget(tc_label)

        # 样式
        bubble_bg = theme.color("user-bubble") if role == "user" else theme.color("assistant-bubble")
        margin = "6px 20px 6px 80px" if role == "user" else "6px 80px 6px 20px"
        radius = theme.radius("md")
        self.setStyleSheet(f"""
            MessageBubble {{
                background-color: {bubble_bg};
                border-radius: {radius}px;
                margin: {margin};
                border: 1px solid {theme.color('border')};
            }}
        """)


class ChatWidget(QWidget):
    """完整的聊天区域：历史消息 + 输入框 + 发送按钮。"""

    message_sent = Signal(str)  # 用户输入后发射
    command_selected = Signal(str)  # 用户选择研究指令后发射
    clear_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._theme = ThemeManager()
        theme = self._theme

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._loading_label: QLabel | None = None

        # 知识库统计栏
        self._stats_label = QLabel("知识库: 加载中...")
        self._stats_label.setStyleSheet(
            f"padding: {theme.spacing('xs')}px {theme.spacing('sm')}px; "
            f"color: {theme.color('text-tertiary')}; font-size: 11px;"
        )
        self._layout.addWidget(self._stats_label)

        # 滚动消息区域
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.NoFrame)

        self._msg_container = QWidget()
        self._msg_container.setStyleSheet(f"background: transparent;")
        self._msg_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self._msg_layout = QVBoxLayout(self._msg_container)
        self._msg_layout.setContentsMargins(0, 0, 0, 0)
        self._msg_layout.setAlignment(Qt.AlignTop)
        self._msg_layout.setSpacing(theme.spacing("xs"))
        self._msg_layout.addStretch()
        self._scroll.setWidget(self._msg_container)
        self._layout.addWidget(self._scroll, stretch=1)

        # 输入区
        self._input = QTextEdit()
        self._input.setPlaceholderText("输入你的问题... (Enter 发送, Shift+Enter 换行)")
        self._input.setMaximumHeight(120)
        self._input.setFont(theme.font("font-ui"))
        self._input.setStyleSheet(f"""
            QTextEdit {{
                border: 1px solid {theme.color('border')};
                border-radius: {theme.radius('md')}px;
                padding: {theme.spacing('sm')}px;
                padding-right: 40px;
                background-color: {theme.color('bg-tertiary')};
                color: {theme.color('text-secondary')};
            }}
            QTextEdit:focus {{
                border-color: {theme.color('accent')};
            }}
        """)

        send_btn = QPushButton("↑")
        send_btn.setFixedSize(32, 32)
        send_btn.setCursor(Qt.PointingHandCursor)
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.color('border')};
                color: white;
                border: none;
                border-radius: 16px;
                font-size: 15px;
                font-weight: bold;
                padding: 0;
            }}
            QPushButton:hover {{
                background-color: {theme.color('accent')};
            }}
            QPushButton:pressed {{
                background-color: {theme.color('accent-hover')};
            }}
        """)
        send_btn.clicked.connect(self._on_send)

        input_container = _InputContainer(self._input, send_btn)

        # 指令选择器 + 输入框
        self._cmd_combo = QComboBox()
        self._cmd_combo.setMinimumWidth(100)
        self._cmd_combo.setMaximumWidth(140)
        self._cmd_combo.setFont(theme.font("font-ui"))
        self._cmd_combo.setCursor(Qt.PointingHandCursor)
        self._cmd_combo.setStyleSheet(f"""
            QComboBox {{
                border: 1px solid {theme.color('border')};
                border-radius: {theme.radius('md')}px;
                padding: 6px 8px;
                background-color: {theme.color('bg-tertiary')};
                color: {theme.color('text-secondary')};
            }}
            QComboBox:hover {{
                border-color: {theme.color('accent')};
            }}
            QComboBox QAbstractItemView {{
                background-color: {theme.color('bg-tertiary')};
                color: {theme.color('text-secondary')};
                selection-background-color: {theme.color('accent')};
                selection-color: white;
                border: 1px solid {theme.color('border')};
                outline: none;
            }}
        """)
        self._cmd_combo.currentIndexChanged.connect(self._on_command_changed)
        self._cmd_combo.hide()

        input_row = QHBoxLayout()
        input_row.setContentsMargins(theme.spacing("xs"), 0, theme.spacing("xs"), theme.spacing("xs"))
        input_row.setSpacing(6)
        input_row.addWidget(self._cmd_combo)
        input_row.addWidget(input_container, stretch=1)
        self._layout.addLayout(input_row)

        # Enter 发送 / Shift+Enter 换行
        self._input.installEventFilter(self)
        self._scroll.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj is self._input and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers() & Qt.ShiftModifier:
                self._on_send()
                return True
        if obj is self._scroll.viewport() and event.type() == QEvent.Resize:
            self._msg_container.setMaximumWidth(event.size().width())
        return super().eventFilter(obj, event)

    def update_stats(self, paper_count: int, chunk_count: int):
        self._stats_label.setText(f"知识库: {paper_count} 篇论文, {chunk_count} 个分块")

    def add_message(self, role: str, content: str, tool_calls: list[str] | None = None):
        """添加一条消息到聊天区域。"""
        bubble = MessageBubble(role, content, tool_calls)
        # 插入到 stretch 之前
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, bubble)

    def set_loading(self, loading: bool):
        """设置"思考中"状态。"""
        if loading:
            self._loading_label = QLabel("<i>思考中...</i>")
            self._loading_label.setStyleSheet(
                f"color: {self._theme.color('text-tertiary')}; padding: {self._theme.spacing('xs')}px;"
            )
            self._msg_layout.insertWidget(self._msg_layout.count() - 1, self._loading_label)
        else:
            if self._loading_label is not None:
                self._msg_layout.removeWidget(self._loading_label)
                self._loading_label.deleteLater()
                self._loading_label = None

    def clear(self):
        """清空聊天历史。"""
        while self._msg_layout.count() > 1:  # 保留底部 stretch
            item = self._msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def set_commands(self, skills: list):
        """根据 skill 列表填充指令下拉框。"""
        self._cmd_combo.blockSignals(True)
        self._cmd_combo.clear()

        if not skills:
            self._cmd_combo.hide()
            self._cmd_combo.blockSignals(False)
            return

        self._cmd_combo.addItem("研究指令")
        # 占位项不可选
        self._cmd_combo.model().item(0).setEnabled(False)

        for s in skills:
            self._cmd_combo.addItem(s.name)
            self._cmd_combo.setItemData(self._cmd_combo.count() - 1, s.description, Qt.ToolTipRole)

        self._cmd_combo.setCurrentIndex(0)
        self._cmd_combo.show()
        self._cmd_combo.blockSignals(False)

    def _on_command_changed(self, index: int):
        if index <= 0:
            return
        skill_name = self._cmd_combo.currentText()
        self._cmd_combo.blockSignals(True)
        self._cmd_combo.setCurrentIndex(0)
        self._cmd_combo.blockSignals(False)
        self.command_selected.emit(skill_name)

    def _on_send(self):
        text = self._input.toPlainText().strip()
        if not text:
            return
        self._input.clear()
        self.add_message("user", text)
        self.message_sent.emit(text)
