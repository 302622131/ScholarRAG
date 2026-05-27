"""三层设计令牌主题管理器：primitive → semantic → component."""

import json
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

_TOKENS_PATH = Path(__file__).parent / "resources" / "theme" / "tokens.json"

# 系统可用的等宽字体优先级列表
_CODE_FONT_CANDIDATES = ["Cascadia Code", "Cascadia Mono", "Consolas", "Courier New"]


def _resolve_code_font() -> str:
    """返回系统上第一个可用的等宽字体."""
    from PySide6.QtGui import QFontDatabase

    available = set(QFontDatabase.families())
    for family in _CODE_FONT_CANDIDATES:
        if family in available:
            return family
    return "Consolas"  # Windows 必定有


class ThemeManager:
    """单例主题管理器，从 JSON 加载三层设计令牌."""

    _instance: "ThemeManager | None" = None

    def __new__(cls) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def _load(self) -> None:
        if self._loaded:
            return
        with open(_TOKENS_PATH, encoding="utf-8") as f:
            data = json.load(f)

        self._primitive: dict[str, str] = data["primitive"]
        self._semantic_map: dict[str, str] = data["semantic"]
        self._typo: dict[str, dict] = data["typography"]
        self._spacing: dict[str, int] = data["spacing"]
        self._radius: dict[str, int] = data["radius"]
        self._component_qss: dict[str, str] = {k: v["qss"] for k, v in data["component"].items()}

        self._code_font = _resolve_code_font()
        self._loaded = True

    def color(self, semantic_key: str) -> str:
        """根据语义令牌名返回原始 hex 颜色，未命中则尝试原始令牌."""
        self._load()
        primitive_key = self._semantic_map.get(semantic_key, semantic_key)
        return self._primitive.get(primitive_key, self._primitive.get(semantic_key, "#000000"))

    def font(self, token: str) -> QFont:
        """根据排版令牌名创建 QFont."""
        spec = self.typo_spec(token)
        family = spec["family"]
        if token == "font-code":
            family = self._code_font
        font = QFont(family, spec["size"])
        weight = spec.get("weight", 400)
        if weight >= 700:
            font.setBold(True)
        return font

    def typo_spec(self, token: str) -> dict:
        """返回排版令牌原始规格字典（调用方不应修改返回值）."""
        self._load()
        return self._typo[token]

    def spacing(self, token: str) -> int:
        """返回间距像素值."""
        self._load()
        return self._spacing[token]

    def radius(self, token: str) -> int:
        """返回圆角像素值."""
        self._load()
        return self._radius[token]

    def stylesheet(self, component: str) -> str:
        """返回预定义的组件 QSS 样式表."""
        self._load()
        return self._component_qss.get(component, "")

    def apply_global(self, app: QApplication) -> None:
        """设置应用级全局字体和样式表."""
        self._load()
        spec = self._typo["font-ui"]
        font = QFont(spec["family"], spec["size"])
        app.setFont(font)
        app.setStyleSheet(self.stylesheet("global") + self.stylesheet("scrollbar"))



