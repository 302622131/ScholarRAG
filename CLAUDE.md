# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
conda activate rag                    # Python 3.11, D:\anaconda\envs\rag
pip install -r requirements.txt       # 安装依赖
python desktop/main.py                # 启动应用
python scripts/ingest_folder.py       # 批量导入 data/papers/ 下的 PDF
```

无测试、无 lint。注意：`README.md` 描述的是已废弃的 Streamlit 界面。

## Architecture

PySide6 桌面科研助手，三栏布局。RAG 引擎（`src/`）被桌面层（`desktop/`）直接 import，不走 HTTP。

```
┌──────────────┬──────────────────┬──────────────────┐
│ 左侧 PDF 列表 │ 中间 PDF 阅读器   │ 右侧 Agent 对话  │
│ project_panel│ pdf_reader       │ agent_panel      │
└──────────────┴──────────────────┴──────────────────┘
 菜单: 工具→知识库管理 | 设置→模型配置 | 帮助→关于
```

### 启动流程

`main.py` → `config.py` 加载 Settings → `services.py` 创建所有单例 → `app.py` 启动 MainWindow

### 核心模块（src/）

- `agent.py` — Agent 核心。Anthropic SDK，`while` 循环 + `stop_reason` 自然终止。无意图预分类，统一 system prompt，LLM 自行决定何时调工具
- `tools.py` — 8 个工具（dict 映射调度，Anthropic `input_schema` 格式）：search_papers、list_papers、ingest_paper、ingest_all_papers、list_local_files、get_paper_info、load_skill、run_python。`get_catalog()` 自动从工具定义生成 prompt 描述
- `ingestion.py` — 入库管线：parse → chunk → embed → store，SHA-256 前 12 位去重。`is_ingested()` 供 UI 快速检查
- `chunker.py` — 段落优先 → 超长按句子切分 → 重叠 2 句。章节检测用段落索引比对，噪音段落（标题、数字行）自动过滤
- `vector_store.py` — ChromaDB，单集合 `research_papers`，余弦相似度
- `embedding.py` — sentence-transformers（all-MiniLM-L6-v2），延迟加载
- `parser.py` — PyMuPDF PDF 解析，`compute_file_hash()` 供其他模块复用
- `bm25_search.py` — BM25Okapi 关键词检索（增删后需 `refresh()`）
- `downloader.py` — arxiv SDK 下载（Agent 工具不暴露，仅 UI 用）
- `reranker.py` — BGE CrossEncoder 精排（已启用，默认本地模型）
- `hyde.py` — Anthropic SDK 生成假设文档增强检索（已启用）

### 主题系统（desktop/theme.py）

三层设计令牌（primitive → semantic → component），JSON 驱动。`ThemeManager` 单例提供 `color()`、`font()`、`spacing()`、`radius()`、`stylesheet()` 方法。

### Skill 系统（desktop/skills_loader.py）

扫描 `desktop/resources/skills/<name>/SKILL.md`，解析 YAML frontmatter（name + description + Markdown body）。
Skill 目录可附带 Python 脚本，Agent 通过 `run_python` 工具执行。`refresh()` 支持热加载。

**已内置 5 个 skill**：literature-review（文献综述）、paper-quick-read（论文速读）、method-comparison（方法对比）、research-gaps（找研究空白）、statistics-report（论文统计，含 analyze.py）。

**两条加载路径**：
- 用户选指令 → `_on_command()` → `Services.inject_skill(body)` → system prompt，不进消息历史
- 自由输入提 skill 名 → LLM 调 `load_skill` 工具获取全文

`inject_skill()` 注入的 body 会持久保留在 system prompt 中，`refresh_skills()` 不会清除它（通过 `_injected_skill_body` 恢复）。

### 桌面层关键文件

- `desktop/services.py` — `init_services()` 创建所有单例，`refresh_skills()` 热加载
- `desktop/workers.py` — `IngestWorker` 和 `AgentChatWorker`（QThread）避免阻塞 UI
- `desktop/panels/agent_panel.py` — 右侧对话面板，管理 `_history: list[dict]`，`_on_command()` 将指令 skill 注入消息
- `desktop/panels/project_panel.py` — 左侧 PDF 文件夹浏览面板
- `desktop/widgets/chat_widget.py` — 聊天气泡 + 指令下拉框 + 输入框
- `desktop/widgets/pdf_reader.py` — PDF 阅读器（PyMuPDF 渲染），中间面板
- `desktop/dialogs/settings_dialog.py` — Anthropic 配置 + 检索参数 + Reranker + Skill 管理

## Agent 对话逻辑

统一 system prompt，LLM 自行判断：
- 闲聊 → 直接回答
- 科研问题 → 调 search_papers → 拿结果 → 回答
- 用户选指令 → harness 注入 skill body 到 system prompt → 按指引执行（多轮保留，不丢上下文）
- 自由输入提 skill 名 → LLM 调 load_skill → 按指引执行

循环：`while True`，`stop_reason != "tool_use"` 时自然终止，无人工轮数上限。thinking/redacted_thinking 块原样传回。Agent 返回的 `updated_history`（含完整 tool_use/tool_result/thinking）直接替换 `self._history`，不丢上下文。

System prompt 中注入的 skill 指引优先于通用规则（"Skill 的步骤优先于本系统提示词的规则"）。

## Configuration

`config.py` Settings dataclass，加载顺序：JSON（`%APPDATA%/RAGAssistant/config.json`）→ `.env` → 环境变量。兼容旧 `openai_*` 字段名自动迁移。

| 字段 | 默认 | 说明 |
|---|---|---|
| `anthropic_api_key` | — | API Key（也可设 `ANTHROPIC_API_KEY` 环境变量） |
| `anthropic_base_url` | `https://api.deepseek.com/anthropic` | 留空用 Anthropic 默认 |
| `anthropic_model` | `deepseek-chat` | 主模型 |
| `anthropic_fast_model` | `deepseek-chat` | HyDE 用 |
| `embedding_model_name` | 本地路径 | all-MiniLM-L6-v2 |
| `reranker_model` | 本地路径 | 空则不启用 |
| `top_k_default` | `5` | 检索片段数 |
| `max_output_tokens` | `8000` | Agent 单次输出最大 token 数（范围 1024-65536） |

## Key design decisions

- **paper_id = SHA-256(file) 前 12 位**：内容去重
- **向量数据库全局单例**：`%APPDATA%/RAGAssistant/chroma_db`
- **不预注入论文上下文**：LLM 自行调 search_papers
- **嵌入模型内置**：all-MiniLM-L6-v2 随项目分发
- **检索管线**：HyDE → Dense 双路 + BM25 → 加权融合 → Reranker 精排 → Top K
- **入库由用户手动操作**：左侧按钮或右键菜单
- **Skill 全局路径**：`desktop/resources/skills/`，通过设置页可见
