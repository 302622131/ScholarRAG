"""后台工作线程：将耗时操作放入 QThread，避免阻塞 UI。"""

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from src.agent import ResearchAgent
from src.ingestion import IngestionPipeline


class IngestWorker(QThread):
    """PDF 入库线程：解析 → 分块 → 嵌入 → 存储。"""
    progress = Signal(str)     # 当前状态描述
    finished = Signal(bool, str, str)  # success, paper_id or error, filename

    def __init__(self, ingestion: IngestionPipeline, filepath: Path,
                 force: bool = False, parent=None):
        super().__init__(parent)
        self._ingestion = ingestion
        self._filepath = filepath
        self._force = force

    def run(self):
        filename = self._filepath.name
        try:
            self.progress.emit(f"正在解析: {filename}")
            pid = self._ingestion.ingest_file(self._filepath, force=self._force)
            if pid:
                self.finished.emit(True, pid, filename)
            else:
                self.finished.emit(False, "已存在，跳过", filename)
        except Exception as e:
            self.finished.emit(False, str(e), filename)


class AgentChatWorker(QThread):
    """Agent 对话线程：调用 agent.chat()。"""
    progress = Signal(str)
    finished = Signal(dict)  # agent.chat() 返回的完整 result dict

    def __init__(self, agent: ResearchAgent, user_message: str,
                 history: list[dict], parent=None):
        super().__init__(parent)
        self._agent = agent
        self._user_message = user_message
        self._history = history

    def run(self):
        try:
            self.progress.emit("思考中...")
            result = self._agent.chat(self._user_message, self._history)
            self.finished.emit(result)
        except Exception as e:
            self.finished.emit({
                "answer": f"出错了: {e}",
                "tool_calls_made": [],
                "updated_history": [],
            })
