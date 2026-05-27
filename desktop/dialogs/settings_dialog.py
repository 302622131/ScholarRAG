"""模型配置对话框。"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QSpinBox, QGroupBox, QPushButton, QTextEdit,
    QDialogButtonBox, QLabel, QFileDialog, QComboBox, QListWidget,
)
from PySide6.QtCore import Qt

from config import Settings
from desktop.skills_loader import SkillLoader
from desktop.theme import ThemeManager


_SKILL_HELP_TEXT = """<b>SKILL.md 格式说明</b>

每个 skill 是一个包含 SKILL.md 文件的子文件夹，存放在：
<code>desktop/resources/skills/&lt;名称&gt;/SKILL.md</code>

<b>文件格式：</b>
<pre>---
name: my-skill
description: 一句话描述 skill 的功能
---
这里是 skill 的具体内容，用 Markdown 编写。
告诉 Agent 在什么情况下使用、按什么步骤执行。</pre>

<b>name</b> 和 <b>description</b> 会出现在 Agent 的 system prompt 中，Agent 根据 description 判断是否调用。body 是 load_skill 加载后 Agent 看到的完整内容。"""


class SettingsDialog(QDialog):
    """LLM 和检索参数配置。"""

    def __init__(self, settings: Settings, parent=None,
                 skill_loader: SkillLoader | None = None):
        super().__init__(parent)
        self.setWindowTitle("配置")
        self.setMinimumWidth(520)
        self._settings = settings
        self._skill_loader = skill_loader
        self._help_expanded = False
        self._setup_ui()
        self._load()

    def _setup_ui(self):
        theme = ThemeManager()
        layout = QVBoxLayout(self)
        layout.setSpacing(theme.spacing("md"))

        # ── Anthropic 配置 ──
        llm_group = QGroupBox("Anthropic 配置")
        llm_group.setStyleSheet(theme.stylesheet("group-box"))
        llm_form = QFormLayout(llm_group)

        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.Password)
        self._api_key.setPlaceholderText("sk-ant-...")
        llm_form.addRow("API Key:", self._api_key)

        self._base_url = QLineEdit()
        self._base_url.setPlaceholderText("https://api.deepseek.com/anthropic")
        llm_form.addRow("Base URL:", self._base_url)

        self._model = QLineEdit()
        llm_form.addRow("主模型:", self._model)

        self._fast_model = QLineEdit()
        llm_form.addRow("快速模型:", self._fast_model)

        layout.addWidget(llm_group)

        # ── 嵌入模型 ──
        emb_group = QGroupBox("嵌入模型")
        emb_group.setStyleSheet(theme.stylesheet("group-box"))
        emb_form = QFormLayout(emb_group)

        emb_path_row = QHBoxLayout()
        self._embedding_model = QLineEdit()
        self._embedding_model.setPlaceholderText("本地路径或 HuggingFace 模型名（如 BAAI/bge-m3）")
        emb_path_row.addWidget(self._embedding_model)
        emb_browse = QPushButton("浏览...")
        emb_browse.clicked.connect(lambda: self._browse_model_dir("选择嵌入模型目录", self._embedding_model))
        emb_path_row.addWidget(emb_browse)
        emb_form.addRow("模型路径:", emb_path_row)

        self._embedding_device = QComboBox()
        self._embedding_device.addItems(["cpu", "cuda"])
        emb_form.addRow("运行设备:", self._embedding_device)

        emb_warning = QLabel("更换嵌入模型后需清空知识库并重新入库")
        emb_warning.setStyleSheet(f"color: {theme.color('warning')}; font-size: 11px;")
        emb_form.addRow(emb_warning)

        layout.addWidget(emb_group)

        # ── 检索配置 ──
        ret_group = QGroupBox("检索配置")
        ret_group.setStyleSheet(theme.stylesheet("group-box"))
        ret_form = QFormLayout(ret_group)

        self._top_k = QSpinBox()
        self._top_k.setRange(1, 20)
        self._top_k.setValue(5)
        ret_form.addRow("Top-K 检索块数:", self._top_k)

        self._max_tokens = QSpinBox()
        self._max_tokens.setRange(1024, 65536)
        self._max_tokens.setSingleStep(1024)
        ret_form.addRow("最大输出 Token 数:", self._max_tokens)

        layout.addWidget(ret_group)

        # ── Reranker ──
        rerank_group = QGroupBox("Reranker（可选）")
        rerank_group.setStyleSheet(theme.stylesheet("group-box"))
        rerank_form = QFormLayout(rerank_group)

        rerank_path_row = QHBoxLayout()
        self._reranker_model = QLineEdit()
        self._reranker_model.setPlaceholderText("留空则禁用 Reranker")
        rerank_path_row.addWidget(self._reranker_model)
        rerank_browse = QPushButton("浏览...")
        rerank_browse.clicked.connect(lambda: self._browse_model_dir("选择 Reranker 模型目录", self._reranker_model))
        rerank_path_row.addWidget(rerank_browse)
        rerank_form.addRow("模型路径:", rerank_path_row)

        layout.addWidget(rerank_group)

        # ── Skill 配置 ──
        skill_group = QGroupBox("Skill 配置")
        skill_group.setStyleSheet(theme.stylesheet("group-box"))
        skill_layout = QVBoxLayout(skill_group)

        # 路径展示
        path_layout = QFormLayout()
        global_skill_path = QLabel(str(SkillLoader.default_global_dir().resolve()))
        global_skill_path.setStyleSheet(f"color: {theme.color('text-tertiary')}; font-size: 11px;")
        global_skill_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        path_layout.addRow("存放路径:", global_skill_path)
        skill_layout.addLayout(path_layout)

        # 帮助文本（折叠）
        help_row = QHBoxLayout()
        self._help_btn = QPushButton("格式说明 ▸")
        self._help_btn.setStyleSheet(theme.stylesheet("button-secondary"))
        self._help_btn.clicked.connect(self._toggle_help)
        help_row.addWidget(self._help_btn)
        help_row.addStretch()
        skill_layout.addLayout(help_row)

        self._help_text = QTextEdit()
        self._help_text.setReadOnly(True)
        self._help_text.setHtml(_SKILL_HELP_TEXT)
        self._help_text.setStyleSheet(f"color: {theme.color('text-secondary')}; font-size: 11px;")
        self._help_text.setMaximumHeight(200)
        self._help_text.hide()
        skill_layout.addWidget(self._help_text)

        # skill 列表 + 刷新
        list_header = QHBoxLayout()
        list_header.addWidget(QLabel("已加载 Skill:"))
        list_header.addStretch()
        self._skill_count_label = QLabel()
        self._skill_count_label.setStyleSheet(f"color: {theme.color('text-tertiary')}; font-size: 11px;")
        list_header.addWidget(self._skill_count_label)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setStyleSheet(theme.stylesheet("button-secondary"))
        refresh_btn.clicked.connect(self._refresh_skill_list)
        list_header.addWidget(refresh_btn)
        skill_layout.addLayout(list_header)

        self._skill_list = QListWidget()
        self._skill_list.setMaximumHeight(100)
        self._skill_list.setStyleSheet(theme.stylesheet("table"))
        skill_layout.addWidget(self._skill_list)

        # 错误展示
        self._error_label = QLabel()
        self._error_label.setStyleSheet(
            f"color: {theme.color('danger')}; font-size: 11px; padding: 4px;"
        )
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        skill_layout.addWidget(self._error_label)

        layout.addWidget(skill_group)

        # ── 按钮 ──
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save_and_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _toggle_help(self):
        self._help_expanded = not self._help_expanded
        if self._help_expanded:
            self._help_text.show()
            self._help_btn.setText("格式说明 ▾")
        else:
            self._help_text.hide()
            self._help_btn.setText("格式说明 ▸")

    def _load(self):
        s = self._settings
        self._api_key.setText(s.anthropic_api_key)
        self._base_url.setText(s.anthropic_base_url)
        self._model.setText(s.anthropic_model)
        self._fast_model.setText(s.anthropic_fast_model)
        self._embedding_model.setText(s.embedding_model_name)
        self._embedding_device.setCurrentText(s.embedding_device)
        self._top_k.setValue(s.top_k_default)
        self._max_tokens.setValue(s.max_output_tokens)
        self._reranker_model.setText(s.reranker_model)
        self._refresh_skill_list()

    def _refresh_skill_list(self):
        self._skill_list.clear()
        self._error_label.hide()

        if not self._skill_loader:
            self._skill_count_label.setText("(未初始化)")
            return

        skills = self._skill_loader.skills
        self._skill_count_label.setText(f"共 {len(skills)} 个")

        for s in skills:
            self._skill_list.addItem(f"{s.name} — {s.description}")

        errors = self._skill_loader.errors
        if errors:
            text = "以下 SKILL.md 解析失败:\n" + "\n".join(errors)
            self._error_label.setText(text)
            self._error_label.show()

    def _save_and_accept(self):
        s = self._settings
        s.anthropic_api_key = self._api_key.text()
        s.anthropic_base_url = self._base_url.text()
        s.anthropic_model = self._model.text() or "deepseek-chat"
        s.anthropic_fast_model = self._fast_model.text() or "deepseek-chat"
        s.embedding_model_name = self._embedding_model.text()
        s.embedding_device = self._embedding_device.currentText()
        s.top_k_default = self._top_k.value()
        s.max_output_tokens = self._max_tokens.value()
        s.reranker_model = self._reranker_model.text()

        s.save()
        self.accept()

    def _browse_model_dir(self, title: str, target: QLineEdit):
        path = QFileDialog.getExistingDirectory(self, title)
        if path:
            target.setText(path)

    def get_settings(self) -> Settings:
        return self._settings
