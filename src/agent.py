from anthropic import Anthropic

from config import Settings
from src.tools import ToolRegistry


SYSTEM_PROMPT = """你是 RAG Research IDE 的 AI Agent，底层由 {model_name} 驱动。

当被问及"你是谁"或"你是什么模型"时，如实说明你是 {model_name}。

## 核心行为准则

**先规划，再执行。** 收到请求后：
1. 判断需要哪些工具、调用顺序，然后逐步执行
2. 工具调用是为了你自己收集信息，不是为了展示给用户看
3. 如果用户消息中包含完整的 Skill 指引，严格按照其中的步骤执行，Skill 的步骤优先于本系统提示词的规则

## 可用工具

{tool_catalog}

## 工具使用规则

- 论文相关问题应 search_papers 获取信息后回答，引用来源（论文标题、页码）
- Skill 目录下可能包含 Python 脚本，可以调用 run_python 执行。script 只能填文件名，不能包含路径
- 闲聊时直接回答，不需要搜索
- 使用中文回答

## 输出格式

- 自然的段落，不同主题之间用空行分隔
- 不用 emoji 作为内容标记
- 不用 markdown 表格（| 分隔）
- 列举时用简单的编号（1. 2. 3.）
- 引用论文用书名号，如《DARTS: Differentiable Architecture Search》"""


class ResearchAgent:
    """RAG Agent：Anthropic SDK，LLM 自行判断何时调用工具，自然终止."""

    def __init__(self, settings: Settings, tool_registry: ToolRegistry,
                 skill_catalog: str = ""):
        base_url = settings.anthropic_base_url or None
        self._client = Anthropic(api_key=settings.anthropic_api_key, base_url=base_url)
        self._model = settings.anthropic_model
        self._max_tokens = settings.max_output_tokens
        self._tools = tool_registry
        self._tool_defs = tool_registry.get_definitions()
        self._base_system = SYSTEM_PROMPT.format(
            model_name=self._model,
            tool_catalog=tool_registry.get_catalog(),
        )
        self._system = self._base_system
        if skill_catalog:
            self._append_skill_catalog(skill_catalog)

    def _append_skill_catalog(self, catalog: str) -> None:
        self._skill_catalog = catalog
        if catalog:
            self._system = self._base_system + (
                f"\n\n## 可用技能 (Skills)\n\n{catalog}\n\n"
                "当用户请求涉及上述 skill 的功能时，先调用 load_skill 加载完整内容再执行。"
            )

    def reload_skill_catalog(self, catalog: str) -> None:
        self._system = self._base_system
        self._append_skill_catalog(catalog)
        if hasattr(self, '_injected_skill_body'):
            self._system += f"\n\n## 当前任务指引（优先级高于上述通用规则）\n\n{self._injected_skill_body}"

    def inject_skill(self, skill_body: str) -> None:
        """将 skill 全文注入 system prompt，不进消息历史。"""
        self._injected_skill_body = skill_body
        self._system = self._base_system
        self._append_skill_catalog(self._skill_catalog or "")
        self._system += f"\n\n## 当前任务指引（优先级高于上述通用规则）\n\n{skill_body}"

    def chat(self, user_message: str, history: list[dict]) -> dict:
        messages = list(history)
        messages.append({"role": "user", "content": user_message})

        tool_calls_made: list[str] = []

        while True:
            response = self._client.messages.create(
                model=self._model,
                system=self._system,
                messages=messages,
                tools=self._tool_defs,
                max_tokens=self._max_tokens,
            )

            if response.stop_reason != "tool_use":
                text = _extract_text(response.content)
                messages.append({"role": "assistant", "content": text})
                return {
                    "answer": text,
                    "tool_calls_made": tool_calls_made,
                    "updated_history": messages,
                }

            # 构建 assistant 消息（含所有 content blocks，thinking 也必须传回）
            assistant_content = []
            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
                elif block.type in ("thinking", "redacted_thinking"):
                    entry: dict = {
                        "type": block.type,
                        "thinking" if block.type == "thinking" else "data": (
                            block.thinking if block.type == "thinking" else block.data
                        ),
                    }
                    if block.type == "thinking":
                        entry["signature"] = block.signature
                    assistant_content.append(entry)
            messages.append({"role": "assistant", "content": assistant_content})

            # 执行工具
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result = self._tools.execute(block.name, block.input)
                tool_calls_made.append(block.name)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

            messages.append({"role": "user", "content": tool_results})


def _extract_text(content: list) -> str:
    """从 Anthropic 响应 content blocks 中拼接文本."""
    parts = []
    for block in content:
        if block.type == "text":
            parts.append(block.text)
    return "\n".join(parts) or "(模型未生成文本回答)"
