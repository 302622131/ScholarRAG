# RAG 检索增强技术文档

## 总览

当前项目的检索流程是单线式的：

```
用户提问 → 向量检索 → Top K 片段 → 拼接上下文 → LLM 回答
```

本方案引入三个增强技术，将其升级为：

```
用户提问
  → 意图识别（判断用户要做什么）
  → HyDE 假设答案生成（缩小语义差距）
  → 多路并行检索（向量 + 关键词 + 元数据 + 子问题拆分）
  → 融合去重（合并多路结果）
  → Reranker 重排序（精排 Top N）
  → 根据意图选择 Prompt 模板
  → LLM 生成回答
```

---

## 一、意图识别（Intent Router）

### 原理

用户对论文库的提问可以归为几类，不同类型的查询适合不同的检索策略：

| 意图类型 | 示例 | 最佳检索策略 |
|---|---|---|
| **事实检索** | "S4 的状态转移矩阵是什么形式" | 高精度向量检索，小块优先 |
| **概括总结** | "这篇论文的主要贡献是什么" | 更大上下文窗口，多块聚合 |
| **对比分析** | "S4 和 Mamba 在长序列建模上有什么区别" | 多篇论文分别检索，各自取 Top 片段 |
| **调研探索** | "最近有哪些状态空间模型的改进工作" | 跨论文搜索，多样性优先，可能触发下载 |
| **操作指令** | "帮我把这篇文章下载入库" | 无需检索，直接调工具 |

### 实现方式

在检索之前，用一次轻量级 LLM 调用做分类。Prompt 设计原则：**短、结构化、输出受限**。

```
你是一个意图分类器。根据用户输入，判断意图并输出 JSON。

用户输入：{user_message}

输出格式：
{"intent": "fact_lookup" | "summarize" | "compare" | "explore" | "action"}

规则：
- fact_lookup: 询问具体的技术细节、公式、参数
- summarize: 要求总结、概括、梳理
- compare: 涉及多篇论文或多种方法的对比
- explore: 探索性询问，没有明确指向某篇论文
- action: 指令性操作，如下载、入库、删除
```

实现代码结构：

```python
# src/intent.py — 意图识别器
import json
from openai import OpenAI

class IntentRouter:
    """用 LLM 做意图分类，输出结构化结果。"""

    INTENT_PROMPT = """你是一个意图分类器..."""

    def __init__(self, client: OpenAI, model: str):
        self._client = client
        self._model = model

    def classify(self, user_message: str) -> str:
        """返回意图类型字符串。"""
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": self.INTENT_PROMPT},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            temperature=0,   # 分类任务不需要创造性
            max_tokens=100,
        )
        return json.loads(resp.choices[0].message.content)["intent"]
```

`temperature=0` 保证每次相同输入得到相同分类，`response_format={"type": "json_object"}` 强制 LLM 输出合法 JSON。

后续 agent 可以根据 intent 选择不同的：
- 检索 `top_k`（事实检索多取、概括少取）
- chunk 大小偏好（细节用小块、概括用大块）
- prompt 模板（总结模板、对比模板、探索模板）
- 是否触发工具调用

---

## 二、多路检索（Multi-Path Retrieval）

### 原理

单路向量检索的问题：用户查询和论文片段之间是**不同域**的语言。用户用自然语言提问，论文用学术语言写作。仅靠嵌入向量的余弦相似度来桥接，存在语义错配。

多路检索的思路：从不同角度同时发起检索，各路互补，融合后送 Reranker 精排。

### 四路检索设计

**路 1：原文向量检索（已有）**

当前项目已实现，直接复用。用 sentence-transformers 对用户查询做 embedding → ChromaDB 余弦相似度查询。

```python
def _dense_retrieval(self, query: str, top_k: int = 20) -> list[dict]:
    embedding = self._embedder.embed_query(query)
    return self._vector_store.query(embedding, top_k=top_k)
```

**路 2：BM25 关键词检索（新增）**

BM25 是经典的词频-逆文档频率（TF-IDF）的改进版本，对精确术语匹配远超向量检索。比如用户搜"HiPPO matrix initialization"，向量检索可能偏到含义相近但不是讲 HiPPO 的内容，BM25 能直接命中包含这个词的段落。

```python
# 实现：用 rank_bm25 库（轻量、纯 Python）
from rank_bm25 import BM25Okapi
import jieba  # 或 nltk.word_tokenize

class BM25Searcher:
    """在已入库论文上构建 BM25 索引。"""

    def __init__(self, vector_store: VectorStore):
        self._store = vector_store
        self._rebuild_index()

    def _rebuild_index(self):
        """全量重建 BM25 索引（增删论文时触发）。"""
        all_chunks = self._get_all_chunks()
        tokenized = [jieba.lcut(c["text"]) for c in all_chunks]
        self._bm25 = BM25Okapi(tokenized)
        self._chunk_map = all_chunks

    def search(self, query: str, top_k: int = 20) -> list[dict]:
        tokens = jieba.lcut(query)
        scores = self._bm25.get_scores(tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [self._chunk_map[i] for i in top_indices]
```

**路 3：元数据过滤检索（新增）**

利用 ChromaDB 的 `where` 子句。不生成新的向量，而是用结构化条件缩小范围。

```python
def _metadata_retrieval(self, query: str, filters: dict, top_k: int = 10) -> list[dict]:
    """按章节、论文等元数据条件过滤后检索。"""
    embedding = self._embedder.embed_query(query)
    # 例如：只搜 Introduction 章、只看 2024 年的论文
    return self._vector_store.query(embedding, top_k=top_k, where=filters)
```

常用过滤条件：
- `{"section": "introduction"}` — 只看引言中的段落（适合找研究背景）
- `{"section": {"$in": ["method", "proposed"]}}` — 只看方法部分（适合找实现细节）
- `{"paper_id": "a1b2c3"}` — 限定在某篇论文内搜索

**路 4：子问题拆分检索（新增）**

复杂问题拆成多个子问题，每个子问题独立检索，结果合并。

```python
def _decomposed_retrieval(self, complex_query: str, top_k: int = 5) -> list[dict]:
    """复杂问题 → 拆分子问题 → 各自检索 → 合并。"""
    sub_queries = self._decompose_query(complex_query)  # LLM 拆分
    all_hits = []
    seen_ids = set()
    for sub_q in sub_queries:
        hits = self._dense_retrieval(sub_q, top_k=top_k)
        for h in hits:
            if h["id"] not in seen_ids:
                all_hits.append(h)
                seen_ids.add(h["id"])
    return all_hits
```

拆分 prompt 示例：
```
将以下复杂问题拆分成 2-4 个可以独立检索的子问题：
"对比 S4 和 Mamba 在长序列建模上的性能和处理速度"
→ ["S4 model long sequence performance", "Mamba model long sequence performance", "S4 inference speed comparison"]
```

### 融合策略

四路结果各自返回不同数量的候选（比如每路 10 个），汇聚后可能重复。融合步骤：

1. **去重**：按 chunk_id 去重（同一 chunk 可能被多路命中）
2. **归一化分数**：各路的分数量纲不同（余弦距离 vs BM25 分数），做 min-max 归一化
3. **加权合并**：给每路设权重（向量 0.4、BM25 0.3、元数据 0.1、子问题 0.2），加权求和
4. **取 Top N**：合并后取出 Top 20，送 Reranker

```python
def _merge_results(self, results_by_path: dict[str, list[dict]]) -> list[dict]:
    """多路结果融合去重。"""
    weights = {"dense": 0.4, "bm25": 0.3, "metadata": 0.1, "decomposed": 0.2}
    merged: dict[str, dict] = {}  # chunk_id → chunk + weighted_score

    for path_name, hits in results_by_path.items():
        if not hits:
            continue
        # 归一化该路的分数
        scores = [1 - h.get("distance", 0) if path_name == "dense"
                  else h.get("score", 0) for h in hits]
        min_s, max_s = min(scores), max(scores)
        range_s = max_s - min_s or 1  # 避免除零

        for h, raw_score in zip(hits, scores):
            cid = h.get("id", "")
            norm_score = (raw_score - min_s) / range_s
            weighted = norm_score * weights.get(path_name, 0.2)
            if cid not in merged or weighted > merged[cid].get("_weight", 0):
                h["_weight"] = weighted
                merged[cid] = h

    sorted_items = sorted(merged.values(), key=lambda x: x.get("_weight", 0), reverse=True)
    return sorted_items[:20]
```

---

## 三、问题假设（HyDE）

### 原理

HyDE = Hypothetical Document Embeddings（假设文档嵌入），由 Gao et al. 在 2022 年提出。

核心问题：用户问题和知识库中的文档片段是**不同种类**的文本。

- 用户问："那个用矩阵运算加速注意力的方法是什么"
- 论文原文："We propose a novel linear-time attention mechanism based on low-rank matrix factorization..."

这两段话的向量相似度可能很低——因为用词、句式、缩写完全不一样。但 LLM 很擅长生成论文风格的文本。

HyDE 的思路：

```
用户提问
  ↓
LLM 生成一个"假设性文档"（假装自己是论文，回答这个问题）
  ↓
用这个生成的文本去做向量检索（而不是用原问题）
  ↓
生成的文本和真实论文风格接近 → 向量相似度更高 → 召回率提升
```

例如用户问"怎么解决长序列训练中的梯度消失问题"，LLM 生成的假设文档：

> "To address the vanishing gradient problem in long sequence training, we employ a structured state space model (SSM) with HiPPO matrix initialization. The HiPPO operator projects the input sequence onto a set of orthogonal polynomial bases, allowing the model to capture long-range dependencies without exponential decay of gradients..."

这段生成文本的用词风格（structured state space model、HiPPO matrix、orthogonal polynomial bases）和真实论文非常接近，检索效果显著好于直接用"梯度消失怎么解决"去搜。

### 实现方式

```python
# src/hyde.py — HyDE 假设文档生成器

HYDE_PROMPT = """你是一个学术论文作者。请用学术论文的风格和语言，
写一段 200-300 字的段落，回答以下问题。

回答要用专业术语，模仿机器学习论文的写作风格（如 NeurIPS/ICML 论文）。
不要求回答完全正确，只需要风格和结构像真实的论文段落即可。

问题：{question}

假设性文档："""


class HydeGenerator:
    """用 LLM 生成假设性文档，缩小查询和论文之间的语义差距。"""

    def __init__(self, client: OpenAI, model: str):
        self._client = client
        self._model = model

    def generate(self, question: str) -> str | None:
        """生成假设文档。失败时返回 None，降级为直接用原问题检索。"""
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": HYDE_PROMPT.format(question=question)}],
                temperature=0.3,  # 需要一定的多样性，但不要完全随机
                max_tokens=400,
            )
            return resp.choices[0].message.content
        except Exception:
            return None  # 降级：用原问题直接检索
```

`temperature=0.3` 权衡：太低（0.0）生成的内容过于模板化，太高（1.0）可能跑偏，0.3 既有学术风格的变化又不失准确性。

**使用方式**：在 agent 的检索步骤中，把原来的 `embedder.embed_query(user_message)` 替换为：

```python
# 原始检索
query_vec = embedder.embed_query(user_message)       # "怎么解决梯度消失"

# HyDE 检索
hypo_doc = hyde_gen.generate(user_message)            # LLM 生成学术风格假设文档
query_vec = embedder.embed_query(hypo_doc)            # 用假设文档去搜
```

失败降级：如果 LLM 生成失败（网络超时等），直接用原问题检索，不影响系统可用性。

---

## 四、整合后的 Agent 流程

三样技术整合后，`agent.chat()` 的完整流程：

```python
def chat(self, user_message: str, history: list[dict]) -> dict:
    # 1. 意图识别
    intent = self._intent_router.classify(user_message)

    # 2. 操作指令 — 跳过检索，直接走工具
    if intent == "action":
        return self._handle_action(user_message, history)

    # 3. HyDE 生成假设文档（事实检索和比较分析受益最大）
    if intent in ("fact_lookup", "compare"):
        hyde_doc = self._hyde_gen.generate(user_message)
        search_query = hyde_doc or user_message
    else:
        search_query = user_message

    # 4. 多路检索
    dense_results = self._dense_retrieval(search_query, top_k=15)
    bm25_results = self._bm25_searcher.search(user_message, top_k=15)
    meta_results = self._metadata_retrieval(search_query, filters=self._build_filter(intent), top_k=10)
    decomp_results = self._decomposed_retrieval(user_message, top_k=5) if self._is_complex(user_message) else []

    # 5. 融合
    merged = self._merge_results({
        "dense": dense_results,
        "bm25": bm25_results,
        "metadata": meta_results,
        "decomposed": decomp_results,
    })

    # 6. Reranker 精排（取 Top 20 → 精排 → Top 5）
    reranked = self._reranker.rerank(search_query, merged, top_k=5)

    # 7. 根据意图选 prompt + 构建上下文
    context = self._build_context(reranked)
    prompt = self._select_prompt(intent).format(context=context)

    # 8. LLM 生成（带工具调用）
    return self._llm_chat(prompt, user_message, history, self._tool_defs)
```

---

## 五、新增依赖

```
rank-bm25>=0.2.2       # BM25 关键词检索（纯 Python，无需安装数据库）
jieba>=0.42.1          # 中文分词（BM25 需要，英文可换成 nltk）
```

Reranker 模型（可选，推荐 `BAAI/bge-reranker-v2-m3`）通过 ModelScope 下载到本地，与嵌入模型同样方式。

---

## 六、对现有代码的影响

| 文件 | 变更 |
|---|---|
| `src/intent.py` | **新增** — IntentRouter 意图分类 |
| `src/hyde.py` | **新增** — HydeGenerator 假设文档生成 |
| `src/bm25_search.py` | **新增** — BM25Searcher 关键词检索 |
| `src/reranker.py` | **新增** — Reranker 重排序 |
| `src/agent.py` | **修改** — 检索步骤从单路变多路融合 |
| `src/api.py` | **不改** — HTTP 接口层无变化 |
| `ui/` | **不改** — 前端无变化 |
