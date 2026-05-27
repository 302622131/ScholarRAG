"""桌面应用入口。"""

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中（兼容 python desktop/main.py 和 python -m desktop.main）
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from config import Settings, CONFIG_PATH, APP_DATA_DIR, settings as global_settings
from desktop.app import MainWindow
from desktop.services import Services, init_services
from desktop.theme import ThemeManager


def _first_run_setup(settings: Settings) -> bool:
    """首次运行时弹出配置引导。返回 True 表示用户完成了配置。"""
    from desktop.dialogs.settings_dialog import SettingsDialog

    # 简单的首次运行提示
    msg = QMessageBox()
    msg.setWindowTitle("欢迎使用 RAG Research IDE")
    msg.setText("检测到首次运行。\n\n请配置 LLM 连接信息（API Key、Base URL、模型名称）。"
                "\n嵌入模型已内置，无需额外配置。")
    msg.setIcon(QMessageBox.Information)
    msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
    if msg.exec() != QMessageBox.Ok:
        return False

    dlg = SettingsDialog(settings)
    if dlg.exec():
        return True
    return False


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("RAG Research IDE")
    app.setOrganizationName("RAGAssistant")
    app.setWindowIcon(QIcon(str(_PROJECT_ROOT / "aigei.png")))

    # 主题（全局字体 + 样式表）
    ThemeManager().apply_global(app)

    # 加载配置
    settings = global_settings

    # 检查是否首次运行（无 API Key 且无配置文件）
    is_first_run = not settings.anthropic_api_key and not CONFIG_PATH.exists()

    if is_first_run:
        # 确保数据目录存在
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not _first_run_setup(settings):
            return  # 用户取消

    # 初始化服务
    services: Services | None = None
    if settings.anthropic_api_key:
        try:
            services = init_services(settings)
        except Exception as e:
            QMessageBox.warning(
                None, "服务初始化失败",
                f"部分服务无法启动:\n{e}\n\n请检查配置后重试。")
            # 仍然启动 UI，用户可以去设置中修正
    else:
        QMessageBox.information(
            None, "未配置 LLM",
            "请先完成模型配置（菜单 → 设置 → 模型配置）。\n"
            "配置完成后对话功能才可用。")

    # 启动主窗口
    window = MainWindow(settings, services)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
