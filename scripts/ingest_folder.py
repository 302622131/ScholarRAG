"""批量导入 data/papers/ 下所有 PDF 到向量数据库。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from src.parser import PDFParser
from src.chunker import TextChunker
from src.embedding import EmbeddingService
from src.vector_store import VectorStore
from src.ingestion import IngestionPipeline


def main():
    parser = PDFParser()
    chunker = TextChunker(
        max_chunk_chars=settings.chunk_max_chars,
        overlap_sentences=settings.overlap_sentences,
        min_chunk_chars=settings.min_chunk_chars,
    )
    embedder = EmbeddingService(
        model_name=settings.embedding_model_name,
        device=settings.embedding_device,
    )
    vector_store = VectorStore(
        persist_dir=str(settings.chroma_persist_dir),
        collection_name=settings.chroma_collection_name,
    )

    pipeline = IngestionPipeline(parser, chunker, embedder, vector_store)

    papers_dir = Path(settings.papers_dir)
    if not papers_dir.exists():
        print(f"论文目录不存在: {papers_dir}")
        return

    pdf_files = sorted(papers_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"目录 {papers_dir} 中没有 PDF 文件")
        return

    print(f"找到 {len(pdf_files)} 个 PDF 文件\n")

    success = 0
    skipped = 0
    for fp in pdf_files:
        print(f"处理: {fp.name} ... ", end="", flush=True)
        pid = pipeline.ingest_file(fp)
        if pid:
            print(f"完成 ({pid})")
            success += 1
        else:
            print("跳过（已存在）")
            skipped += 1

    print(f"\n完成: 成功 {success}, 跳过 {skipped}, 总计 {len(pdf_files)}")


if __name__ == "__main__":
    main()
