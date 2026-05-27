import numpy as np
from sentence_transformers import SentenceTransformer


class EmbeddingService:
    """嵌入服务：延迟加载 sentence-transformers 模型。"""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", device: str = "cpu"):
        self._model_name = model_name
        self._device = device
        self._model: SentenceTransformer | None = None
        self._dimension: int = 0

    def _load(self) -> None:
        if self._model is not None:
            return
        self._model = SentenceTransformer(self._model_name, device=self._device)
        self._dimension = self._model.get_embedding_dimension()

    def embed_texts(self, texts: list[str], show_progress: bool = False) -> np.ndarray:
        self._load()
        return self._model.encode(texts, show_progress_bar=show_progress, convert_to_numpy=True)

    def embed_query(self, query: str) -> np.ndarray:
        self._load()
        return self._model.encode([query], convert_to_numpy=True)[0]

    @property
    def dimension(self) -> int:
        if self._dimension == 0:
            self._load()
        return self._dimension
