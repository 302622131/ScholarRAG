"""Reranker：对多路检索结果做交叉编码重排序。"""

from sentence_transformers import CrossEncoder


class Reranker:
    """用 CrossEncoder 对候选片段精排。

    与 bi-encoder（embedding）不同，cross-encoder 同时输入 query 和 document，
    输出一个相似度分数。精度更高，但需要对每一对 (query, doc) 都做一次推理，
    所以只对粗排后的少量候选（如 Top 20）使用。

    推荐模型：BAAI/bge-reranker-v2-m3（可从 ModelScope 下载）
    """

    def __init__(self, model_name_or_path: str = "BAAI/bge-reranker-v2-m3", device: str = "cpu"):
        self._model = CrossEncoder(model_name_or_path, device=device)

    def rerank(self, query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
        """对候选片段重排序，返回 Top K。

        每个 candidate dict 需包含 "text" 字段。
        """
        if not candidates:
            return []

        pairs = [(query, c["text"]) for c in candidates]
        scores = self._model.predict(pairs, show_progress_bar=False)

        for i, s in enumerate(scores):
            candidates[i]["rerank_score"] = float(s)

        candidates.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        return candidates[:top_k]
