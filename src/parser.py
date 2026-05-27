import hashlib
from pathlib import Path

import fitz


def compute_file_hash(filepath: Path) -> str:
    """计算文件的 SHA-256 哈希（前 12 位用于 paper_id 去重）。"""
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


class PDFParser:
    """用 PyMuPDF 提取 PDF 文本和元数据。"""

    def parse(self, filepath: Path) -> dict:
        doc = fitz.open(str(filepath))
        pages = []
        full_text_parts = []

        for i, page in enumerate(doc, start=1):
            text = page.get_text(sort=True)
            pages.append({"page_num": i, "text": text})
            full_text_parts.append(text)

        doc.close()

        full_text = "\n".join(full_text_parts)
        file_hash = compute_file_hash(filepath)

        return {
            "text": full_text,
            "pages": pages,
            "metadata": {
                "source": filepath.name,
                "filepath": str(filepath.resolve()),
                "file_hash": file_hash,
                "pages_count": len(pages),
                "file_size_bytes": filepath.stat().st_size,
            },
        }
