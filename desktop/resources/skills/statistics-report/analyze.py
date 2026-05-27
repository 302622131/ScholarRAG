"""论文统计脚本：读取 JSON 数据，输出统计结果。"""

import json
import sys
from collections import Counter
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "缺少参数: _data.json"}, ensure_ascii=False))
        return

    data_path = Path(__file__).parent / sys.argv[1]
    if not data_path.exists():
        print(json.dumps({"error": f"数据文件不存在: {data_path}"}, ensure_ascii=False))
        return

    papers = json.loads(data_path.read_text(encoding="utf-8"))

    total = len(papers)
    if total == 0:
        print(json.dumps({"error": "无数据"}, ensure_ascii=False))
        return

    years = [p.get("year", 0) for p in papers if p.get("year", 0) > 1900]
    pages = [p.get("pages", 0) for p in papers if p.get("pages", 0) > 0]

    year_counter = Counter(years)
    year_dist = {str(y): c for y, c in sorted(year_counter.items())}

    result = {
        "total": total,
        "year_range": f"{min(years)} - {max(years)}" if years else "未知",
        "year_distribution": year_dist,
        "avg_pages": round(sum(pages) / len(pages), 1) if pages else 0,
        "trend": _trend(year_counter),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _trend(year_counter: Counter) -> str:
    if len(year_counter) < 2:
        return "数据不足，无法判断趋势"
    sorted_years = sorted(year_counter.items())
    first_half = sum(c for y, c in sorted_years[:len(sorted_years)//2])
    second_half = sum(c for y, c in sorted_years[len(sorted_years)//2:])
    if second_half > first_half * 1.2:
        return "上升趋势"
    elif first_half > second_half * 1.2:
        return "下降趋势"
    else:
        return "平稳"


if __name__ == "__main__":
    main()
