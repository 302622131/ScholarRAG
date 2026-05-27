import re


class TextChunker:
    """混合分块策略：段落优先 → 超长按句子切分 → 带重叠 + 跳过参考文献。"""

    # 常见章节标题模式
    SECTION_PATTERNS = [
        re.compile(r, re.IGNORECASE)
        for r in [
            r"^\d+\.?\s*(introduction|related\s*work|background|preliminaries)\b",
            r"^\d+\.?\s*(method|approach|methodology|proposed|model|architecture)\b",
            r"^\d+\.?\s*(experiment|evaluation|result|analysis)\b",
            r"^\d+\.?\s*(discussion|conclusion|future\s*work|summary)\b",
            r"^\d+\.?\s*(appendix|supplementary)\b",
            r"^(abstract|acknowledgment|acknowledgements)\s*$",
        ]
    ]

    # 参考文献区域的标题
    REFERENCE_HEADERS = re.compile(
        r"^(references|bibliography|citations|works\s*cited)\s*$",
        re.IGNORECASE,
    )

    # 句子边界
    SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?。！？])\s+")

    def __init__(self, max_chunk_chars: int = 800, overlap_sentences: int = 2,
                 min_chunk_chars: int = 20):
        self._max_chunk_chars = max_chunk_chars
        self._overlap_sentences = overlap_sentences
        self._min_chunk_chars = min_chunk_chars

    def chunk(self, text: str, base_metadata: dict) -> list[dict]:
        paragraphs = self._split_paragraphs(text)
        ref_boundary = self._find_references_boundary(paragraphs)
        if ref_boundary is not None:
            paragraphs = paragraphs[:ref_boundary]

        # 先对段落做噪音过滤和分块，同时记录每个块的来源段落索引
        chunks_with_para_idx: list[tuple[str, int]] = []
        for pi, para in enumerate(paragraphs):
            if self._is_noise(para):
                continue
            subs = self._split_long_paragraph(para)
            for sub in subs:
                if len(sub.strip()) < self._min_chunk_chars:
                    continue
                chunks_with_para_idx.append((sub.strip(), pi))

        if not chunks_with_para_idx:
            return []

        sections = self._detect_sections(paragraphs)
        chunks = [c for c, _ in chunks_with_para_idx]
        chunks_with_overlap = self._apply_overlap(chunks)
        result = []
        for i, c in enumerate(chunks_with_overlap):
            para_idx = chunks_with_para_idx[i % len(chunks_with_para_idx)][1]
            section_name = None
            for start, name in sections:
                if start <= para_idx:
                    section_name = name
                else:
                    break

            meta = {**base_metadata, "chunk_index": i, "chunk_total": len(chunks_with_overlap)}
            if section_name:
                meta["section"] = section_name
            result.append({"text": c, "metadata": meta})

        return result

    def _split_paragraphs(self, text: str) -> list[str]:
        raw = text.split("\n\n")
        return [p.strip() for p in raw if p.strip()]

    def _split_long_paragraph(self, para: str) -> list[str]:
        if len(para) <= self._max_chunk_chars:
            return [para]

        sentences = self.SENTENCE_BOUNDARY.split(para)
        chunks = []
        current = ""
        for sent in sentences:
            if len(current) + len(sent) <= self._max_chunk_chars:
                current += sent if current == "" else " " + sent
            else:
                if current:
                    chunks.append(current)
                # 单个句子超长则接受它
                if len(sent) > self._max_chunk_chars:
                    chunks.append(sent)
                    current = ""
                else:
                    current = sent
        if current:
            chunks.append(current)
        return chunks

    def _detect_sections(self, paragraphs: list[str]) -> list[tuple[int, str]]:
        """识别段落中哪些是章节标题，返回 [(段落序号, 章节名), ...]。"""
        sections = []
        for i, para in enumerate(paragraphs):
            for pat in self.SECTION_PATTERNS:
                m = pat.match(para.strip())
                if m:
                    sections.append((i, m.group(0).strip()))
                    break
        return sections

    def _find_references_boundary(self, paragraphs: list[str]) -> int | None:
        """找到参考文献起始位置。只匹配独立成行的参考文献标题。"""
        for i, para in enumerate(paragraphs):
            # 参考文献标题通常很短且单独成段
            if len(para.split()) <= 3 and self.REFERENCE_HEADERS.match(para.strip()):
                return i
        return None

    def _apply_overlap(self, chunks: list[str]) -> list[str]:
        if self._overlap_sentences <= 0 or len(chunks) <= 1:
            return chunks

        result = []
        prev_tail = ""
        for chunk in chunks:
            sentences = self.SENTENCE_BOUNDARY.split(chunk)
            if prev_tail and sentences:
                # 拼接上一块的尾句（作为上下文）
                result.append(prev_tail + " " + chunk)
            else:
                result.append(chunk)

            # 取当前块尾部的几个句子作为下一块的前缀
            tail_count = min(self._overlap_sentences, len(sentences))
            prev_tail = " ".join(sentences[-tail_count:]) if tail_count > 0 else ""

        return result

    def _is_noise(self, text: str) -> bool:
        """判断文本是否为无检索价值的噪音。"""
        stripped = text.strip()
        if len(stripped) < self._min_chunk_chars:
            return True
        # 纯数字/符号行（如图表编号、页码）
        alpha_ratio = sum(1 for c in stripped if c.isalpha() or c.isspace()) / max(len(stripped), 1)
        if alpha_ratio < 0.3:
            return True
        return False
