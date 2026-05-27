import chromadb
import numpy as np


class VectorStore:
    """ChromaDB 封装：管理 research_papers 集合的增删查。"""

    def __init__(self, persist_dir: str, collection_name: str = "research_papers"):
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=chromadb.Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks: list[dict], embeddings: np.ndarray) -> None:
        ids = []
        documents = []
        metadatas = []
        for chunk in chunks:
            meta = chunk["metadata"]
            paper_id = meta.get("paper_id", "unknown")
            chunk_idx = meta.get("chunk_index", 0)
            chunk_id = f"{paper_id}_chunk_{chunk_idx:04d}"
            ids.append(chunk_id)
            documents.append(chunk["text"])
            metadatas.append({
                k: str(v) if isinstance(v, (list, dict)) else v
                for k, v in meta.items()
                if v is not None
            })

        self._collection.add(ids=ids, documents=documents, embeddings=embeddings.tolist(),
                             metadatas=metadatas)

    def query(self, query_embedding: np.ndarray, top_k: int = 5,
              where: dict | None = None) -> list[dict]:
        result = self._collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        hits = []
        if result["ids"] and result["ids"][0]:
            for i, chunk_id in enumerate(result["ids"][0]):
                hits.append({
                    "id": chunk_id,
                    "text": result["documents"][0][i],
                    "metadata": result["metadatas"][0][i],
                    "distance": result["distances"][0][i],
                })
        return hits

    def delete_paper(self, paper_id: str) -> int:
        existing = self._collection.get(where={"paper_id": paper_id})
        if existing["ids"]:
            self._collection.delete(ids=existing["ids"])
            return len(existing["ids"])
        return 0

    def list_papers(self) -> list[dict]:
        """汇总所有论文的基本信息。"""
        all_data = self._collection.get(include=["metadatas"])
        papers: dict[str, dict] = {}
        if all_data["metadatas"]:
            for meta in all_data["metadatas"]:
                pid = meta.get("paper_id", "unknown")
                if pid not in papers:
                    papers[pid] = {
                        "paper_id": pid,
                        "paper_title": meta.get("paper_title", meta.get("source", "unknown")),
                        "source": meta.get("source", ""),
                        "arxiv_id": meta.get("arxiv_id"),
                        "chunk_total": meta.get("chunk_total", "0"),
                    }
        return list(papers.values())

    def paper_exists(self, paper_id: str) -> bool:
        existing = self._collection.get(where={"paper_id": paper_id})
        return len(existing["ids"]) > 0

    def get_paper_chunks(self, paper_id: str) -> list[dict]:
        """获取某篇论文的所有分块（按 chunk_index 排序）。"""
        result = self._collection.get(
            where={"paper_id": paper_id},
            include=["documents", "metadatas"],
        )
        items = []
        if result["ids"]:
            for i, cid in enumerate(result["ids"]):
                items.append({
                    "id": cid,
                    "text": result["documents"][i],
                    "metadata": result["metadatas"][i],
                })
        items.sort(key=lambda x: int(x["metadata"].get("chunk_index", 0)))
        return items

    def get_all_chunks(self) -> list[dict]:
        """返回全部已入库的分块（供 BM25Searcher 等外部索引使用）。"""
        all_data = self._collection.get(include=["documents", "metadatas"])
        items = []
        if all_data["ids"]:
            for i, cid in enumerate(all_data["ids"]):
                items.append({
                    "id": cid,
                    "text": all_data["documents"][i],
                    "metadata": all_data["metadatas"][i],
                })
        return items

    def count(self) -> int:
        return self._collection.count()

    def reset(self) -> None:
        self._client.delete_collection(self._collection.name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection.name,
            metadata={"hnsw:space": "cosine"},
        )
