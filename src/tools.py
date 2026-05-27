import sys

from src.vector_store import VectorStore
from src.embedding import EmbeddingService
from src.downloader import ArxivDownloader
from src.ingestion import IngestionPipeline
from src.bm25_search import BM25Searcher
from src.reranker import Reranker
from src.hyde import HydeGenerator


class ToolRegistry:
    """工具注册表：dict 映射调度."""

    def __init__(self, vector_store: VectorStore, embedder: EmbeddingService,
                 downloader: ArxivDownloader, ingestion: IngestionPipeline,
                 bm25_searcher: BM25Searcher | None = None,
                 reranker: Reranker | None = None,
                 hyde_gen: HydeGenerator | None = None,
                 skill_loader=None):
        self._vector_store = vector_store
        self._embedder = embedder
        self._downloader = downloader
        self._ingestion = ingestion
        self._bm25 = bm25_searcher
        self._reranker = reranker
        self._hyde_gen = hyde_gen
        self._skill_loader = skill_loader

        self._handlers = {
            "search_papers": self._search_papers,
            "list_papers": self._list_papers,
            "ingest_paper": self._ingest_paper,
            "list_local_files": self._list_local_files,
            "ingest_all_papers": self._ingest_all_papers,
            "get_paper_info": self._get_paper_info,
            "load_skill": self._load_skill,
            "run_python": self._run_python,
        }

    def get_definitions(self) -> list[dict]:
        return _TOOL_DEFINITIONS

    def get_catalog(self) -> str:
        """从工具定义自动生成一句话描述列表，注入 system prompt."""
        lines = []
        for t in _TOOL_DEFINITIONS:
            lines.append(f"- {t['name']}: {t['description']}")
        return "\n".join(lines)

    def execute(self, tool_name: str, arguments: dict) -> str:
        handler = self._handlers.get(tool_name)
        if not handler:
            return f"未知工具: {tool_name}"
        try:
            return handler(arguments)
        except Exception as e:
            return f"工具执行失败: {e}"

    # ── 工具实现 ──

    def _search_papers(self, args: dict) -> str:
        query = args["query"]
        top_k = min(args.get("top_k", 5), 20)
        paper_id = args.get("paper_id")

        where = {"paper_id": paper_id} if paper_id else None

        search_query = query
        if self._hyde_gen:
            hyde_doc = self._hyde_gen.generate(query)
            if hyde_doc:
                search_query = hyde_doc

        dense_hits = self._dense_search(search_query, top_k=15, where=where)
        seen = {h["id"] for h in dense_hits}
        if search_query != query:
            for h in self._dense_search(query, top_k=10, where=where):
                if h["id"] not in seen:
                    dense_hits.append(h)
                    seen.add(h["id"])

        bm25_hits = []
        if self._bm25 and not where:
            bm25_hits = self._bm25.search(query, top_k=15)

        merged = self._fusion(dense_hits, bm25_hits)

        if not merged:
            return "未找到相关论文内容。"

        if self._reranker:
            merged = self._reranker.rerank(query, merged, top_k=top_k)
        else:
            merged = merged[:top_k]

        lines = []
        for i, h in enumerate(merged):
            meta = h.get("metadata", {})
            src = meta.get("paper_title", meta.get("source", "unknown"))
            page = meta.get("page_number", "?")
            lines.append(f"[{i+1}] 来源: {src} (第{page}页)\n{h['text']}\n")

        return "\n---\n".join(lines)

    def _dense_search(self, query: str, top_k: int,
                       where: dict | None = None) -> list[dict]:
        embedding = self._embedder.embed_query(query)
        return self._vector_store.query(embedding, top_k=top_k, where=where)

    def _fusion(self, dense: list[dict], bm25: list[dict]) -> list[dict]:
        merged: dict[str, dict] = {}

        if dense:
            scores = [1 - h.get("distance", 0) for h in dense]
            min_s, max_s = min(scores), max(scores)
            score_range = max_s - min_s or 1
            for h, raw in zip(dense, scores):
                cid = h.get("id", "")
                norm = (raw - min_s) / score_range
                merged[cid] = {**h, "_weight": norm * 0.5}

        if bm25:
            scores = [h.get("score", 0) for h in bm25]
            min_s, max_s = min(scores), max(scores) if scores else 1
            score_range = max_s - min_s or 1
            for h, raw in zip(bm25, scores):
                cid = h.get("id", "")
                norm = (raw - min_s) / score_range
                w = norm * 0.5
                if cid not in merged or w > merged[cid].get("_weight", 0):
                    merged[cid] = {**h, "_weight": w}

        return sorted(merged.values(), key=lambda x: x.get("_weight", 0), reverse=True)

    def _list_papers(self, _args: dict) -> str:
        papers = self._vector_store.list_papers()
        if not papers:
            return "知识库中还没有论文。可以通过下载 arxiv 论文或导入本地 PDF 来添加。"

        lines = [f"知识库中共有 {len(papers)} 篇论文:\n"]
        for p in papers:
            title = p.get("paper_title", "未知")
            pid = p.get("paper_id", "")
            arxiv_id = p.get("arxiv_id", "")
            chunks = p.get("chunk_total", "?")
            extra = f" [arxiv: {arxiv_id}]" if arxiv_id else ""
            lines.append(f"- {title}{extra}")
            lines.append(f"  paper_id: {pid}, 分块数: {chunks}")

        return "\n".join(lines)

    def _ingest_paper(self, args: dict) -> str:
        filename = args["filename"]
        force = args.get("force", False)
        filepath = self._downloader.papers_dir / filename

        if not filepath.exists():
            return f"文件不存在: {filepath}"

        try:
            pid = self._ingestion.ingest_file(filepath, force=force)
            if pid:
                return f"已入库: {filename} (paper_id: {pid})"
            else:
                return f"该论文已入库。如需重新入库请使用 force=True"
        except Exception as e:
            return f"入库失败: {e}"

    def _list_local_files(self, _args: dict) -> str:
        papers_dir = self._downloader.papers_dir
        if not papers_dir.exists():
            return f"papers 目录不存在: {papers_dir}"

        pdf_files = sorted(papers_dir.glob("*.pdf"))
        if not pdf_files:
            return f"目录 {papers_dir} 中没有 PDF 文件。"

        ingested = set()
        for p in self._vector_store.list_papers():
            src = p.get("source", "")
            if src:
                ingested.add(src)

        lines = [f"本地 papers 目录共 {len(pdf_files)} 个 PDF 文件:\n"]
        for fp in pdf_files:
            status = "已入库" if fp.name in ingested else "未入库"
            lines.append(f"- {fp.name} [{status}] ({fp.stat().st_size / 1024:.0f} KB)")

        return "\n".join(lines)

    def _ingest_all_papers(self, args: dict) -> str:
        force = args.get("force", False)
        papers_dir = self._downloader.papers_dir

        if not papers_dir.exists():
            return f"papers 目录不存在: {papers_dir}"

        pdf_files = sorted(papers_dir.glob("*.pdf"))
        if not pdf_files:
            return f"目录 {papers_dir} 中没有 PDF 文件。"

        success = []
        skipped = []
        failed = []

        for fp in pdf_files:
            try:
                pid = self._ingestion.ingest_file(fp, force=force)
                if pid:
                    success.append(f"{fp.name} (paper_id: {pid})")
                else:
                    skipped.append(fp.name)
            except Exception as e:
                failed.append(f"{fp.name}: {e}")

        lines = []
        if success:
            lines.append(f"成功入库 {len(success)} 篇:")
            for s in success:
                lines.append(f"  - {s}")
        if skipped:
            lines.append(f"跳过 {len(skipped)} 篇（已存在）:")
            for s in skipped:
                lines.append(f"  - {s}")
        if failed:
            lines.append(f"失败 {len(failed)} 篇:")
            for f in failed:
                lines.append(f"  - {f}")
        if not lines:
            lines.append("没有需要处理的 PDF 文件。")

        return "\n".join(lines)

    def _get_paper_info(self, args: dict) -> str:
        paper_id = args["paper_id"]
        chunks = self._vector_store.get_paper_chunks(paper_id)

        if not chunks:
            return f"未找到 paper_id 为 {paper_id} 的论文"

        first_meta = chunks[0]["metadata"]
        title = first_meta.get("paper_title", "未知")
        source = first_meta.get("source", "")
        arxiv_id = first_meta.get("arxiv_id", "")
        total = first_meta.get("chunk_total", len(chunks))

        preview = "\n\n".join(c["text"][:300] for c in chunks[:3])

        lines = [
            f"论文标题: {title}",
            f"来源文件: {source}",
        ]
        if arxiv_id:
            lines.append(f"arxiv ID: {arxiv_id}")
        lines.append(f"总块数: {total}")
        lines.append(f"\n内容预览（前 3 块）:\n{preview}")

        return "\n".join(lines)


    def _load_skill(self, args: dict) -> str:
        if not self._skill_loader:
            return "Skill 系统未初始化。"
        name = args["name"]
        skill = self._skill_loader.get_skill(name)
        if not skill:
            available = ", ".join(s.name for s in self._skill_loader.skills) or "(无)"
            return f"未找到 skill: {name}。可用: {available}"

        lines = [
            f"已加载 skill: {skill.name}",
            f"描述: {skill.description}",
            "",
            "=== 指令 ===",
            skill.body,
        ]

        # 列出目录下的附带文件（脚本、数据等）
        companion: list[str] = []
        for f in sorted(skill.dir_path.iterdir()):
            if f.name == "SKILL.md":
                continue
            suffix = ""
            if f.is_file():
                size_kb = f.stat().st_size / 1024
                suffix = f" ({size_kb:.1f} KB)"
            elif f.is_dir():
                suffix = " [目录]"
            companion.append(f"  {f.name}{suffix}")

        if companion:
            lines.append("")
            lines.append("=== 附带文件 ===")
            lines.extend(companion)

        lines.append("")
        lines.append(f"=== 目录路径 ===")
        lines.append(str(skill.dir_path))
        lines.append("")
        lines.append("你可以使用 run_python 工具执行该目录下的 Python 脚本。")

        return "\n".join(lines)

    def _run_python(self, args: dict) -> str:
        """执行 skill 目录下的 Python 脚本。"""
        skill_name = args["skill_name"]
        script = args["script"]
        cli_args: list[str] = args.get("args", []) or []

        if not self._skill_loader:
            return "Skill 系统未初始化。"

        skill = self._skill_loader.get_skill(skill_name)
        if not skill:
            return f"未找到 skill: {skill_name}"

        # 安全检查：script 只能填文件名，不能包含路径片段
        if "/" in script or "\\" in script or ".." in script:
            return f"安全限制: script 参数只能填文件名，不能包含路径。收到: {script}"

        script_path = skill.dir_path / script
        if not script_path.exists():
            return f"脚本不存在: {script}（skill 目录: {skill.dir_path}）"

        if not script_path.suffix == ".py":
            return f"只支持执行 .py 脚本。收到: {script}"

        # 确保 script_path 确实在 skill.dir_path 下（防止符号链接绕过）
        try:
            script_path.resolve().relative_to(skill.dir_path.resolve())
        except ValueError:
            return f"安全限制: 脚本必须在 skill 目录内。收到: {script}"

        import subprocess

        try:
            proc = subprocess.run(
                [sys.executable, str(script_path)] + cli_args,
                cwd=str(skill.dir_path),
                capture_output=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            return f"脚本执行超时（60 秒）: {script}"

        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")

        max_len = 4000
        if len(stdout) > max_len:
            stdout = stdout[:max_len] + "\n... (输出已截断)"
        if len(stderr) > max_len:
            stderr = stderr[:max_len] + "\n... (输出已截断)"

        parts = []
        if stdout:
            parts.append(f"[stdout]\n{stdout}")
        if stderr:
            parts.append(f"[stderr]\n{stderr}")
        if not parts:
            parts.append("(无输出)")

        parts.append(f"\n[返回码: {proc.returncode}]")
        return "\n".join(parts)


# ── 工具定义（Anthropic tool_use 格式） ──

_TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "search_papers",
        "description": "在已入库的论文中进行语义搜索，返回最相关的文本片段及来源标注",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "描述你需要查找什么信息的自然语言查询",
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回的片段数量，默认 5，最多 20",
                },
                "paper_id": {
                    "type": "string",
                    "description": "可选，限制只搜索某篇特定论文",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_papers",
        "description": "列出知识库中所有已入库的论文，包含标题、paper_id 等信息",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "ingest_paper",
        "description": "将本地 PDF 文件导入向量数据库使其可被搜索",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "papers 文件夹中的 PDF 文件名",
                },
                "force": {
                    "type": "boolean",
                    "description": "是否强制重新入库（即使已入库过），默认 False",
                },
            },
            "required": ["filename"],
        },
    },
    {
        "name": "list_local_files",
        "description": "列出本地 papers 文件夹中所有 PDF 文件，标注已入库/未入库状态",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "ingest_all_papers",
        "description": "将本地 papers 文件夹中所有未入库的 PDF 批量导入",
        "input_schema": {
            "type": "object",
            "properties": {
                "force": {
                    "type": "boolean",
                    "description": "是否强制重新入库，默认 False",
                },
            },
        },
    },
    {
        "name": "get_paper_info",
        "description": "获取某篇论文的详细信息和内容预览",
        "input_schema": {
            "type": "object",
            "properties": {
                "paper_id": {
                    "type": "string",
                    "description": "论文的唯一标识 paper_id，可通过 list_papers 获取",
                },
            },
            "required": ["paper_id"],
        },
    },
    {
        "name": "load_skill",
        "description": "加载指定 skill 的全量内容以获得详细的操作指引，返回指令、附带文件列表和目录路径",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "skill 名称，可从 system prompt 中的可用技能列表获取",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "run_python",
        "description": "执行 skill 目录下的 Python 脚本。仅在加载 skill 后使用，script 只能填文件名。",
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "skill 名称，用于定位脚本所在目录",
                },
                "script": {
                    "type": "string",
                    "description": "要执行的 Python 文件名（仅文件名，不含路径），如 analyze.py",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "传给脚本的命令行参数列表，可选",
                },
            },
            "required": ["skill_name", "script"],
        },
    },
]
