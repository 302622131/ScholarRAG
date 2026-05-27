import re
from pathlib import Path

import arxiv

from src.parser import compute_file_hash


class ArxivDownloader:
    """从 arxiv 下载论文 PDF 并搜索。"""

    _ID_PATTERN = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")
    _URL_PATTERN = re.compile(r"arxiv\.org/abs/(\d{4}\.\d{4,5})(v\d+)?")

    def __init__(self, papers_dir: Path):
        self.papers_dir = Path(papers_dir)
        self.papers_dir.mkdir(parents=True, exist_ok=True)
        self._client = arxiv.Client(
            delay_seconds=5.0,
            num_retries=3,
        )

    def download(self, arxiv_id_or_url: str) -> dict:
        arxiv_id = self.extract_arxiv_id(arxiv_id_or_url)
        if not arxiv_id:
            raise ValueError(f"无法解析 arxiv ID: {arxiv_id_or_url}")

        search = arxiv.Search(id_list=[arxiv_id])
        result = next(self._client.results(search))

        filepath = self.papers_dir / f"{arxiv_id}.pdf"
        result.download_pdf(dirpath=str(self.papers_dir), filename=f"{arxiv_id}.pdf")

        file_hash = compute_file_hash(filepath)

        return {
            "arxiv_id": arxiv_id,
            "title": result.title,
            "authors": [a.name for a in result.authors],
            "year": result.published.year if result.published else None,
            "summary": result.summary,
            "filepath": str(filepath),
            "file_hash": file_hash,
            "downloaded": True,
        }

    @classmethod
    def extract_arxiv_id(cls, raw: str) -> str | None:
        raw = raw.strip()
        # 支持完整 URL
        m = cls._URL_PATTERN.search(raw)
        if m:
            return m.group(1)
        # 支持直接传 ID
        m = cls._ID_PATTERN.match(raw)
        if m:
            return m.group(1)
        return None

    @classmethod
    def is_valid_arxiv_id(cls, raw: str) -> bool:
        return cls.extract_arxiv_id(raw) is not None
