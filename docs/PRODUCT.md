# RAG Research IDE

基于检索增强生成的桌面端科研论文助手。

一句话：将论文 PDF 导入本地向量知识库，用自然语言对话检索、阅读、分析论文内容。所有数据本地存储，不依赖云服务。

- 🖥️ 三栏 IDE 布局：文件浏览 | 多标签编辑器 | AI 对话
- 🔍 多路智能检索：HyDE + 向量 + 关键词 + Reranker
- 🏠 数据完全本地：ChromaDB 向量库 + 内置嵌入模型
- 🔌 灵活模型接入：兼容 OpenAI / DeepSeek / 任意兼容 API

## 核心功能

### 论文管理

- PDF 拖拽或浏览导入，自动解析 → 分块 → 向量化入库
- SHA-256 内容去重，重复导入自动提醒
- 知识库管理面板：查看、搜索、删除已入库论文

### 智能对话

- 自然语言提问，Agent 自动判断是否需要检索论文
- 引用标注：回答中标注来源论文标题和页码
- 支持事实查询、概括总结、对比分析、探索调研

### 本地检索引擎

- 混合检索：向量语义搜索 + BM25 关键词搜索 + 加权融合
- HyDE 查询增强：自动生成学术风格假设文档，缩小语义差距
- Reranker 精排：交叉编码器对候选片段二次排序

### 辅助工具

- 多标签代码编辑器：Python 语法高亮、行号显示
- 远程 SSH 管理：独立窗口，支持终端操作和 SFTP 文件传输
- 项目文件树：浏览本地项目文件，PDF 右键一键入库

## 技术架构

### 检索管线

```
用户提问 → 意图识别 → HyDE 查询增强 → 多路检索（向量+BM25）
→ 加权融合 → Reranker 精排 → LLM 生成回答
```

### 桌面架构

```
┌──────────────┬───────────────────┬──────────────────┐
│  ProjectPanel │    EditorArea     │   AgentPanel     │
│  (文件树/入库) │  (多标签代码编辑)  │  (对话+检索)     │
└──────────────┴───────────────────┴──────────────────┘
                    ↑ 信号/Slot 通信
┌──────────────────────────────────────────────────────┐
│                 Services (单例容器)                    │
│  Embedder │ VectorStore │ Agent │ BM25 │ Reranker    │
└──────────────────────────────────────────────────────┘
```

- GUI 层：PySide6 三栏 QSplitter，QThread 异步避免 UI 阻塞
- 服务层：所有 RAG 组件通过 Services 容器统一初始化
- 存储层：ChromaDB 持久化向量库，全局单例，跨项目共享

### Agent 对话流程

```
意图分类（fast model）→ System Prompt 注入工具列表
→ LLM 自行判断是否调用 search_papers 等工具
→ 工具返回检索结果 → LLM 生成引用标注的回答
```

## 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| GUI 框架 | PySide6 | 三栏 IDE 布局、多标签编辑器 |
| 嵌入模型 | all-MiniLM-L6-v2 (内置) | 文本向量化，离线可用 |
| 向量数据库 | ChromaDB | 本地持久化，余弦相似度检索 |
| 关键词检索 | BM25Okapi (rank-bm25) | 精确术语匹配 |
| 重排序 | BAAI/bge-reranker-v2-m3 (可选) | Cross-Encoder 精排 |
| LLM 接入 | OpenAI 兼容 API | 支持 DeepSeek / OpenAI / 自定义端点 |
| PDF 解析 | PyMuPDF | 文本提取与元数据读取 |
| 远程连接 | paramiko | SSH 终端 + SFTP 文件传输 |

## 快速开始

### 环境要求

- Python 3.11+（推荐 conda 环境）
- Windows / macOS / Linux

### 安装与启动

```bash
# 1. 创建并激活环境
conda create -n rag python=3.11
conda activate rag

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动桌面应用
python desktop/main.py
```

### 首次使用

1. 菜单栏 → 设置 → 模型配置，填入 API Key 和 Base URL
2. 打开一个本地文件夹作为项目目录
3. 点击"入库"按钮或右键 PDF → 导入知识库
4. 在右侧对话面板提问，Agent 自动检索论文回答

### 配置项速查

| 配置 | 说明 | 默认值 |
|------|------|--------|
| API Key | LLM API 密钥 | — |
| Base URL | API 端点地址 | api.openai.com/v1 |
| 主模型 | 对话与检索推理 | gpt-4o |
| 快速模型 | 意图识别等轻量任务 | gpt-4o-mini |
| Top-K | 每次检索返回片段数 | 5 |
| Reranker | 可选精排模型路径 | (空，不启用) |
