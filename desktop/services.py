"""服务容器：初始化并持有所有单例服务."""

from dataclasses import dataclass
from pathlib import Path

from anthropic import Anthropic

from config import Settings
from src.embedding import EmbeddingService
from src.vector_store import VectorStore
from src.parser import PDFParser
from src.chunker import TextChunker
from src.downloader import ArxivDownloader
from src.ingestion import IngestionPipeline
from src.tools import ToolRegistry
from src.agent import ResearchAgent
from src.bm25_search import BM25Searcher
from src.reranker import Reranker
from src.hyde import HydeGenerator
from desktop.skills_loader import SkillLoader


@dataclass
class Services:
    """所有全局服务单例的容器。应用启动时初始化一次。"""
    embedder: EmbeddingService
    vector_store: VectorStore
    downloader: ArxivDownloader
    ingestion: IngestionPipeline
    tool_registry: ToolRegistry
    agent: ResearchAgent
    bm25_searcher: BM25Searcher
    reranker: Reranker | None
    skill_loader: SkillLoader | None

    def refresh_skills(self) -> None:
        """热加载 skill：重新扫描全局目录并更新 agent prompt。"""
        if not self.skill_loader:
            return
        self.skill_loader.refresh()
        catalog = self.skill_loader.get_skills_prompt()
        self.agent.reload_skill_catalog(catalog)

    def inject_skill(self, skill_body: str) -> None:
        """将 skill 全文注入 system prompt（不进消息历史）。"""
        self.agent.inject_skill(skill_body)


def _make_client(settings: Settings) -> Anthropic:
    base_url = settings.anthropic_base_url or None
    return Anthropic(api_key=settings.anthropic_api_key, base_url=base_url)


def init_services(settings: Settings) -> Services:
    """初始化所有服务。应用启动时调用一次。"""

    settings.papers_dir = str(Path(settings.papers_dir))
    settings.chroma_persist_dir = str(Path(settings.chroma_persist_dir))
    Path(settings.papers_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.chroma_persist_dir).mkdir(parents=True, exist_ok=True)

    embedder = EmbeddingService(
        model_name=settings.embedding_model_name,
        device=settings.embedding_device,
    )

    vector_store = VectorStore(
        persist_dir=settings.chroma_persist_dir,
        collection_name=settings.chroma_collection_name,
    )

    parser = PDFParser()
    chunker = TextChunker(
        max_chunk_chars=settings.chunk_max_chars,
        overlap_sentences=settings.overlap_sentences,
        min_chunk_chars=settings.min_chunk_chars,
    )

    downloader = ArxivDownloader(papers_dir=Path(settings.papers_dir))

    ingestion = IngestionPipeline(
        parser=parser,
        chunker=chunker,
        embedder=embedder,
        vector_store=vector_store,
    )

    bm25_searcher = BM25Searcher(vector_store)

    reranker = None
    if settings.reranker_model:
        reranker = Reranker(
            model_name_or_path=settings.reranker_model,
            device=settings.embedding_device,
        )

    client = _make_client(settings)
    hyde_gen = HydeGenerator(client=client, model=settings.anthropic_fast_model)

    skill_dir = SkillLoader.default_global_dir()
    if not skill_dir.is_dir():
        skill_dir.mkdir(parents=True, exist_ok=True)
    skill_loader = SkillLoader(skill_dir)

    tool_registry = ToolRegistry(
        vector_store=vector_store,
        embedder=embedder,
        downloader=downloader,
        ingestion=ingestion,
        bm25_searcher=bm25_searcher,
        reranker=reranker,
        hyde_gen=hyde_gen,
        skill_loader=skill_loader,
    )

    skill_catalog = skill_loader.get_skills_prompt()
    agent = ResearchAgent(
        settings=settings,
        tool_registry=tool_registry,
        skill_catalog=skill_catalog,
    )

    return Services(
        embedder=embedder,
        vector_store=vector_store,
        downloader=downloader,
        ingestion=ingestion,
        tool_registry=tool_registry,
        agent=agent,
        bm25_searcher=bm25_searcher,
        reranker=reranker,
        skill_loader=skill_loader,
    )
