"""BM25 关键词检索：在论文片段上做精确术语匹配。"""

import re

from rank_bm25 import BM25Okapi

from src.vector_store import VectorStore

WORD_PATTERN = re.compile(r"[a-zA-Z0-9]+")


def _tokenize(text: str) -> list[str]:
    """英文分词：提取字母数字组成的单词并小写化。"""
    return [w.lower() for w in WORD_PATTERN.findall(text)]


class BM25Searcher:
    """BM25 索引，在已入库论文上做关键词检索。"""

    def __init__(self, vector_store: VectorStore):
        self._store = vector_store
        self._bm25: BM25Okapi | None = None
        self._chunk_map: list[dict] = []
        self._rebuild_index()

    def _rebuild_index(self):
        """全量重建索引（每次论文增删后需手动调用）。"""
        all_chunks = self._store.get_all_chunks()
        self._chunk_map = []
        tokenized = []

        for chunk in all_chunks:
            self._chunk_map.append(chunk)
            tokenized.append(_tokenize(chunk["text"]))

        if tokenized:
            self._bm25 = BM25Okapi(tokenized)
        else:
            self._bm25 = None

    def search(self, query: str, top_k: int = 15) -> list[dict]:
        """关键词检索，返回 Top K 片段。"""
        if self._bm25 is None:
            return []

        tokens = _tokenize(query)
        scores = self._bm25.get_scores(tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

        results = []
        for i in top_indices:
            if scores[i] > 0:
                chunk = dict(self._chunk_map[i])
                chunk["score"] = float(scores[i])
                results.append(chunk)
        return results

    def refresh(self):
        """论文增删后调用，重建索引。"""
        self._rebuild_index()
