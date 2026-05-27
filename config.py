"""桌面应用配置管理。

配置优先级：JSON 配置文件 > 环境变量 > 默认值。
首次运行自动生成默认配置文件。
"""

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path

from dotenv import load_dotenv


# ── 应用数据目录（Windows: %APPDATA%/RAGAssistant） ──
def _get_app_data_dir() -> Path:
    appdata = os.environ.get("APPDATA", str(Path.home()))
    return Path(appdata) / "RAGAssistant"


APP_DATA_DIR = _get_app_data_dir()
CONFIG_PATH = APP_DATA_DIR / "config.json"
PROJECT_ROOT = Path(__file__).parent.resolve()

load_dotenv(PROJECT_ROOT / ".env", override=False)

# 开发阶段：嵌入模型默认指向项目本地路径；打包后改为 APP_DATA_DIR
_DEFAULT_LOCAL_MODELS = PROJECT_ROOT / "data" / "local_models"
_DEFAULT_EMBEDDING = str(_DEFAULT_LOCAL_MODELS / "sentence-transformers" / "all-MiniLM-L6-v2")
_DEFAULT_RERANKER = str(_DEFAULT_LOCAL_MODELS / "BAAI" / "bge-reranker-v2-m3" if (_DEFAULT_LOCAL_MODELS / "BAAI" / "bge-reranker-v2-m3").exists() else "")


@dataclass
class Settings:
    """全局配置，可通过 JSON 文件或环境变量覆盖。"""

    # ── LLM (Anthropic SDK) ──
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.deepseek.com/anthropic"
    anthropic_model: str = "deepseek-chat"
    anthropic_fast_model: str = "deepseek-chat"

    # ── 嵌入模型（内置，指向本地路径） ──
    embedding_model_name: str = _DEFAULT_EMBEDDING
    embedding_device: str = "cpu"

    # ── ChromaDB（全局单例，固定在 APP_DATA_DIR） ──
    chroma_persist_dir: str = ""
    chroma_collection_name: str = "research_papers"

    # ── 论文存储 ──
    papers_dir: str = ""

    # ── 分块参数 ──
    chunk_max_chars: int = 800
    overlap_sentences: int = 2
    min_chunk_chars: int = 20

    # ── 检索参数 ──
    top_k_default: int = 5
    max_output_tokens: int = 8000

    # ── Reranker（为空则不启用） ──
    reranker_model: str = _DEFAULT_RERANKER

    def __post_init__(self):
        # 解析相对路径为绝对路径
        for attr in ("chroma_persist_dir", "papers_dir", "embedding_model_name", "reranker_model"):
            val = getattr(self, attr, "")
            if val and not Path(val).is_absolute():
                setattr(self, attr, str(PROJECT_ROOT / val))
        if not self.chroma_persist_dir:
            self.chroma_persist_dir = str(APP_DATA_DIR / "chroma_db")
        if not self.papers_dir:
            self.papers_dir = str(APP_DATA_DIR / "papers")

    # ── JSON 持久化 ──

    def to_dict(self) -> dict:
        """仅序列化用户可配置的字段。"""
        return asdict(self)

    def save(self, path: Path | None = None):
        """保存到 JSON 文件。"""
        target = path or CONFIG_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
                          encoding="utf-8")

    @classmethod
    def from_json(cls, path: Path | None = None) -> "Settings":
        """从 JSON 文件加载配置，环境变量可覆盖。"""
        target = path or CONFIG_PATH
        data = {}
        if target.exists():
            try:
                data = json.loads(target.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

        # 兼容旧 OpenAI 字段名 → 新 Anthropic 字段名
        for old_key, new_key in [
            ("openai_api_key", "anthropic_api_key"),
            ("openai_base_url", "anthropic_base_url"),
            ("openai_model", "anthropic_model"),
            ("openai_fast_model", "anthropic_fast_model"),
        ]:
            if old_key in data and new_key not in data:
                data[new_key] = data.pop(old_key)

        # 环境变量覆盖
        env_overrides = {
            "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY"),
            "anthropic_base_url": os.getenv("ANTHROPIC_BASE_URL") or os.getenv("OPENAI_BASE_URL"),
            "anthropic_model": os.getenv("ANTHROPIC_MODEL") or os.getenv("OPENAI_MODEL"),
            "anthropic_fast_model": os.getenv("ANTHROPIC_FAST_MODEL") or os.getenv("OPENAI_FAST_MODEL"),
            "embedding_model_name": os.getenv("EMBEDDING_MODEL_NAME"),
            "embedding_device": os.getenv("EMBEDDING_DEVICE"),
            "chunk_max_chars": os.getenv("CHUNK_MAX_CHARS"),
            "overlap_sentences": os.getenv("OVERLAP_SENTENCES"),
            "top_k_default": os.getenv("TOP_K_DEFAULT"),
            "max_output_tokens": os.getenv("MAX_OUTPUT_TOKENS"),
            "reranker_model": os.getenv("RERANKER_MODEL"),
            "papers_dir": os.getenv("PAPERS_DIR"),
            "chroma_persist_dir": os.getenv("CHROMA_PERSIST_DIR"),
        }
        for key, val in env_overrides.items():
            if val is not None:
                if key in ("chunk_max_chars", "overlap_sentences", "top_k_default", "max_output_tokens"):
                    data[key] = int(val)
                else:
                    data[key] = val

        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ── 全局单例 ──
settings = Settings.from_json()
