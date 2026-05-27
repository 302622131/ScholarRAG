"""Skill 加载器：扫描全局 SKILL.md。"""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Skill:
    name: str
    description: str
    body: str
    dir_path: Path


def _parse_skill_md(filepath: Path) -> tuple[Skill | None, str | None]:
    """解析单个 SKILL.md 文件。返回 (Skill, None) 成功, (None, 错误原因) 失败。"""
    text = filepath.read_text(encoding="utf-8")

    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if not m:
        return None, "缺少 YAML frontmatter"

    try:
        frontmatter = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        return None, f"YAML 解析失败: {e}"

    name = frontmatter.get("name", "")
    description = frontmatter.get("description", "")
    body = m.group(2).strip()

    if not name:
        return None, "缺少 name 字段"

    return Skill(name=name, description=description, body=body, dir_path=filepath.parent), None


class SkillLoader:
    """扫描全局 skill 目录，加载所有 skill。"""

    def __init__(self, global_dir: Path):
        self._skills: dict[str, Skill] = {}
        self._errors: list[str] = []
        self._global_dir = global_dir
        self._scan(global_dir)

    def _scan(self, root: Path):
        for md_file in root.rglob("SKILL.md"):
            skill, error = _parse_skill_md(md_file)
            if skill:
                self._skills[skill.name] = skill
            else:
                self._errors.append(f"{md_file}: {error}")

    def refresh(self) -> None:
        """重新扫描全局 skill 目录，用于热加载。"""
        self._skills.clear()
        self._errors.clear()
        self._scan(self._global_dir)

    @property
    def skills(self) -> list[Skill]:
        return list(self._skills.values())

    @property
    def errors(self) -> list[str]:
        return list(self._errors)

    def get_skill(self, name: str) -> Skill | None:
        """按名称获取单个 skill."""
        return self._skills.get(name)

    def get_skills_prompt(self) -> str:
        """生成给 LLM 看的可用 skill 列表。"""
        if not self._skills:
            return ""
        lines = []
        for s in self._skills.values():
            lines.append(f"- `{s.name}` — {s.description}")
        return "\n".join(lines)

    @staticmethod
    def default_global_dir() -> Path:
        """软件内置 skill 目录。"""
        return Path(__file__).parent / "resources" / "skills"
