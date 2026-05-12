"""知识条目 JSON 文件校验工具。

校验 knowledge/articles/ 目录下的 JSON 文件是否符合规范。

使用示例:
    $ python hooks/validate_json.py knowledge/articles/20260509-github-01.json
    $ python hooks/validate_json.py knowledge/articles/*.json
    $ python hooks/validate_json.py knowledge/articles/file1.json knowledge/articles/file2.json
"""

import json
import logging
import re
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

REQUIRED_FIELDS: dict[str, type] = {
    "id": str,
    "title": str,
    "source": str,
    "source_url": str,
    "summary": str,
    "tags": list,
    "status": str,
}

VALID_STATUSES = frozenset({"pending_review", "approved", "rejected"})

URL_PATTERN = re.compile(r"^https?://.+")


def validate_file(file_path: Path) -> list[str]:
    """校验单个 JSON 文件。

    Args:
        file_path: JSON 文件路径。

    Returns:
        错误信息列表（无错误时返回空列表）。
    """
    errors: list[str] = []
    try:
        with file_path.open(encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"JSON 解析失败: {e.msg} (行 {e.lineno}, 列 {e.colno})")
        return errors
    except Exception as e:
        errors.append(f"文件读取失败: {e}")
        return errors

    if not isinstance(data, dict):
        errors.append("根对象必须是 dict")
        return errors

    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in data:
            errors.append(f"缺少必填字段: {field}")
        elif not isinstance(data[field], expected_type):
            errors.append(f"字段类型错误: {field} (期望 {expected_type.__name__}, 实际 {type(data[field]).__name__})")

    if "status" in data:
        if data["status"] not in VALID_STATUSES:
            errors.append(f"status 值无效: {data['status']} (必须是 {', '.join(sorted(VALID_STATUSES))} 之一)")

    if "source_url" in data:
        if isinstance(data["source_url"], str) and not URL_PATTERN.match(data["source_url"]):
            errors.append(f"source_url 格式无效: {data['source_url']}")

    if "summary" in data:
        if isinstance(data["summary"], str) and len(data["summary"]) < 50:
            errors.append(f"summary 长度不足 50 字: 当前 {len(data['summary'])} 字")

    if "tags" in data:
        if isinstance(data["tags"], list) and len(data["tags"]) < 1:
            errors.append("tags 至少需要 1 个标签")

    if "score" in data:
        if isinstance(data["score"], (int, float)):
            if not 0.0 <= data["score"] <= 10.0:
                errors.append(f"score 超出范围: {data['score']} (必须是 0.0 ~ 10.0)")
        else:
            errors.append(f"score 类型错误: {type(data['score']).__name__} (期望 int 或 float)")

    return errors


def collect_files(paths: list[str]) -> list[Path]:
    """收集所有待校验的文件路径，支持通配符。

    Args:
        paths: 命令行输入的路径或通配符列表。

    Returns:
        所有匹配的 JSON 文件路径列表。
    """
    files: list[Path] = []
    for path_str in paths:
        path = Path(path_str)
        if path.is_dir():
            files.extend(path.glob("*.json"))
        elif "*" in path_str or "?" in path_str:
            pattern_path = Path(path_str)
            parent = pattern_path.parent if pattern_path.parent != Path(".") else Path.cwd()
            base = pattern_path.name
            files.extend(parent.glob(base))
        elif path.is_file():
            files.append(path)
    return sorted(set(files))


def main() -> int:
    """主入口。"""
    if len(sys.argv) < 2:
        logger.error("用法: python hooks/validate_json.py <json_file> [json_file2 ...]")
        sys.exit(1)

    files = collect_files(sys.argv[1:])
    if not files:
        logger.error("未找到匹配的 JSON 文件")
        sys.exit(1)

    total = 0
    passed = 0
    failed = 0

    for file_path in files:
        total += 1
        errors = validate_file(file_path)
        if errors:
            failed += 1
            logger.error(f"✗ {file_path}")
            for err in errors:
                logger.error(f"  - {err}")
        else:
            passed += 1
            logger.info(f"✓ {file_path}")

    logger.info(f"\n{'=' * 40}")
    logger.info(f"校验完成: 总计 {total} | 通过 {passed} | 失败 {failed}")

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
