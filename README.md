# RAG Research IDE

基于 RAG 的本地科研论文助手，支持 PDF 阅读、论文入库、语义检索和 AI 对话。

## 功能

- **PDF 阅读**：支持打开文件夹浏览论文，连续滚动阅读，Ctrl+滚轮缩放
- **论文入库**：自动解析 PDF，分块、向量化后存入 ChromaDB，SHA-256 去重
- **智能对话**：基于论文内容的 RAG 对话，Agent 自主搜索、阅读、回答，带来源引用
- **研究指令**：内置文献综述、论文速读、方法对比、找研究空白、论文统计等 skill，下拉即可使用
- **Skill 扩展**：可在 `desktop/resources/skills/` 目录下添加自定义 skill（SKILL.md + Python 脚本）

## 安装

```bash
conda create -n rag python=3.11
conda activate rag
pip install -r requirements.txt
```

## 配置

复制 `.env.example` 为 `.env`，填入你的 API Key：

```
ANTHROPIC_API_KEY=sk-your-api-key-here
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
ANTHROPIC_MODEL=deepseek-chat
```

也可以通过 GUI（菜单 → 设置 → 模型配置）修改所有配置。

## 启动

```bash
python desktop/main.py
```

## 嵌入模型和 Reranker

首次启动时会自动从 HuggingFace 下载以下模型（需联网）：

- 嵌入模型：`all-MiniLM-L6-v2`（约 90MB，Sentence-Transformers 自动缓存）
- Reranker：`BAAI/bge-reranker-v2-m3`（约 2.3GB，可选，留空则禁用）

国内用户可设置 HuggingFace 镜像加速：

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

如果已有本地模型，在设置页填入本地路径即可，无需重新下载。

## ChromaDB

知识库数据存储在 `%APPDATA%/RAGAssistant/chroma_db`（Windows）下。首次导入论文时自动创建，用户无需手动配置。

## 批量导入论文

```bash
python scripts/ingest_folder.py
```

将 PDF 论文放入 `data/papers/` 目录后运行此命令。也可通过 GUI 左侧面板的"入库"按钮逐篇导入。

## 项目结构

```
RAG/
├── config.py                    # 配置管理（Settings dataclass）
├── src/                         # RAG 引擎
│   ├── agent.py                 # Agent 核心（Anthropic SDK，while True + stop_reason）
│   ├── tools.py                 # 8 个工具（search_papers, run_python 等）
│   ├── ingestion.py             # 入库管线
│   ├── vector_store.py          # ChromaDB 封装
│   ├── embedding.py             # Sentence-Transformers 嵌入
│   ├── chunker.py               # 智能分块（段落优先 + 重叠）
│   ├── parser.py                # PDF 解析（PyMuPDF）
│   ├── bm25_search.py           # BM25 关键词检索
│   ├── reranker.py              # CrossEncoder 精排
│   ├── hyde.py                  # HyDE 查询增强
│   └── downloader.py            # Arxiv 下载
├── desktop/                     # PySide6 桌面应用
│   ├── app.py                   # 主窗口（三栏布局）
│   ├── main.py                  # 入口
│   ├── services.py              # 服务初始化
│   ├── workers.py               # 后台线程
│   ├── skills_loader.py         # Skill 加载器
│   ├── theme.py                 # 主题系统
│   ├── panels/
│   │   ├── project_panel.py     # 左侧 PDF 列表
│   │   └── agent_panel.py       # 右侧 Agent 对话
│   ├── widgets/
│   │   ├── pdf_reader.py        # PDF 阅读器
│   │   ├── chat_widget.py       # 聊天气泡 + 指令下拉
│   │   └── file_tree.py         # 文件树
│   ├── dialogs/
│   │   ├── settings_dialog.py   # 配置对话框
│   │   └── knowledge_dialog.py  # 知识库管理
│   └── resources/
│       ├── skills/              # 内置 Skill（5 个）
│       └── theme/tokens.json    # 主题令牌
└── scripts/
    └── ingest_folder.py         # 批量导入 CLI
```

## 技术栈

- **GUI**：PySide6
- **LLM**：Anthropic 兼容 API（DeepSeek / OpenAI / Claude）
- **嵌入模型**：Sentence-Transformers（all-MiniLM-L6-v2，本地运行）
- **向量数据库**：ChromaDB（本地持久化）
- **PDF 解析**：PyMuPDF
- **重排序**：CrossEncoder（BAAI/bge-reranker-v2-m3）
