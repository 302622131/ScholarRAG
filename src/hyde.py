"""HyDE：生成假设性文档，缩小查询与论文片段之间的语义差距。"""

from anthropic import Anthropic


HYDE_PROMPT = """你是一个学术论文作者。用学术论文的写作风格，写一段 150-250 字的段落来回答以下问题。

要求：
- 使用机器学习/深度学习论文的专业术语
- 模仿 NeurIPS/ICML 论文的写作风格
- 不需要保证完全正确，只需要风格和结构像真实的论文段落
- 直接输出段落，不要加"根据研究"之类的开头

问题：{question}

假设性文档："""


class HydeGenerator:
    """Anthropic 假设文档生成器。"""

    def __init__(self, client: Anthropic, model: str):
        self._client = client
        self._model = model

    def generate(self, question: str) -> str | None:
        """生成假设文档。失败返回 None，调用方降级为原问题。"""
        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=400,
                temperature=0.3,
                messages=[
                    {"role": "user", "content": HYDE_PROMPT.format(question=question)},
                ],
            )
            content = resp.content[0].text
            return content.strip() if content else None
        except Exception:
            return None
