from pathlib import Path

from src.parser import PDFParser
from src.chunker import TextChunker
from src.embedding import EmbeddingService
from src.vector_store import VectorStore


class IngestionPipeline:
    """入库管线：解析 → 分块 → 向量化 → 存储。按文件哈希去重。"""

    def __init__(self, parser: PDFParser, chunker: TextChunker,
                 embedder: EmbeddingService, vector_store: VectorStore):
        self._parser = parser
        self._chunker = chunker
        self._embedder = embedder
        self._vector_store = vector_store

    def ingest_file(self, filepath: Path, arxiv_metadata: dict | None = None,
                    force: bool = False) -> str | None:
        """入库单个 PDF。返回 paper_id，已存在则返回 None。"""
        parsed = self._parser.parse(filepath)
        file_hash = parsed["metadata"]["file_hash"]
        paper_id = file_hash[:12]

        if not force and self._vector_store.paper_exists(paper_id):
            return None

        if force:
            self._vector_store.delete_paper(paper_id)

        # 尝试从 PDF 文本第一页提取标题
        paper_title = parsed["pages"][0]["text"].split("\n")[0].strip() if parsed["pages"] else filepath.stem
        if len(paper_title) > 200:
            paper_title = paper_title[:200]

        base_metadata = {
            "paper_id": paper_id,
            "paper_title": paper_title,
            "source": parsed["metadata"]["source"],
            "file_hash": file_hash,
        }

        if arxiv_metadata:
            base_metadata["paper_title"] = arxiv_metadata.get("title", paper_title)
            base_metadata["arxiv_id"] = arxiv_metadata.get("arxiv_id", "")

        # 分页处理：每页关联页码
        all_chunks = []
        for page in parsed["pages"]:
            page_chunks = self._chunker.chunk(page["text"], base_metadata)
            for c in page_chunks:
                c["metadata"]["page_number"] = page["page_num"]
            all_chunks.extend(page_chunks)

        # 重新编号 chunk_index
        for i, c in enumerate(all_chunks):
            c["metadata"]["chunk_index"] = i
            c["metadata"]["chunk_total"] = len(all_chunks)

        if not all_chunks:
            return None

        texts = [c["text"] for c in all_chunks]
        embeddings = self._embedder.embed_texts(texts)
        self._vector_store.add_chunks(all_chunks, embeddings)

        return paper_id

    def is_ingested(self, filepath: Path) -> bool:
        parsed = self._parser.parse(filepath)
        return self._vector_store.paper_exists(parsed["metadata"]["file_hash"][:12])
