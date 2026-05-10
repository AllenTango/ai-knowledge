"""知识条目 5 维度质量评分工具。

对 knowledge/articles/ 目录下的 JSON 文件进行质量评分，支持单文件和多文件模式。

使用示例:
    $ python hooks/check_quality.py knowledge/articles/20260509-github-01.json
    $ python hooks/check_quality.py knowledge/articles/*.json
    $ python hooks/check_quality.py knowledge/articles/file1.json knowledge/articles/file2.json

评分维度（满分 100 分）:
    摘要质量 (25分): >= 50字满分，>= 20字基本分，含技术关键词加 5 分
    技术深度 (25分): 基于 score 字段（1-10 映射到 0-25）
    格式规范 (20分): id、title、source_url、status、时间戳五项各 4 分
    标签精度 (15分): 1-3 个标签最佳，有标准标签列表校验
    空洞词检测 (15分): 不含空洞词黑名单中的词汇

等级标准:
    A: 总分 >= 80
    B: 总分 >= 60
    C: 总分 < 60
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

STANDARD_TAGS = frozenset({
    "agent", "llm", "rag", "fine-tuning", "embedding", "vector-database",
    "langchain", "llamaindex", "crewai", "autogen", "dify", "coze",
    "prompt-engineering", "tool-calling", "function-calling", "multi-agent",
    "gpu", "inference", "ai-safety", "red-teaming", "rlhf", "guardrails",
    "release", "tutorial", "paper", "news", "benchmark", "dataset",
    "llm-framework", "inference-engine", "local-deployment", "mac",
})

HOLLOW_WORDS_CN = frozenset({
    "赋能", "抓手", "闭环", "打通", "全链路", "底层逻辑",
    "颗粒度", "对齐", "拉通", "沉淀", "强大的", "革命性的",
})

HOLLOW_WORDS_EN = frozenset({
    "groundbreaking", "revolutionary", "game-changing", "cutting-edge",
})

TECH_KEYWORDS = frozenset({
    "llm", "gpt", "claude", "gemini", "llama", "mistral", "langchain",
    "agent", "rag", "embedding", "fine-tuning", "inference", "gpu",
    "vector", "transformer", "multi-agent", "tool-calling",
    "function-calling", "rlhf", "prompt", "蒸馏", "量化", "推理",
})

URL_PATTERN = __import__("re").compile(r"^https?://.+")
VALID_STATUSES = frozenset({"pending_review", "approved", "rejected", "published"})


@dataclass
class DimensionScore:
    """单个维度评分结果。"""

    name: str
    score: int
    max_score: int
    details: list[str] = field(default_factory=list)

    @property
    def bar(self) -> str:
        filled = int(self.score / self.max_score * 10)
        return f"[{'=' * filled}{'-' * (10 - filled)}]"


@dataclass
class QualityReport:
    """完整质量评估报告。"""

    file_path: str
    summary_quality: DimensionScore = field(default_factory=lambda: DimensionScore("摘要质量", 0, 25))
    technical_depth: DimensionScore = field(default_factory=lambda: DimensionScore("技术深度", 0, 25))
    format_compliance: DimensionScore = field(default_factory=lambda: DimensionScore("格式规范", 0, 20))
    tag_accuracy: DimensionScore = field(default_factory=lambda: DimensionScore("标签精度", 0, 15))
    hollow_word_check: DimensionScore = field(default_factory=lambda: DimensionScore("空洞词检测", 0, 15))

    @property
    def total_score(self) -> int:
        return (
            self.summary_quality.score
            + self.technical_depth.score
            + self.format_compliance.score
            + self.tag_accuracy.score
            + self.hollow_word_check.score
        )

    @property
    def grade(self) -> str:
        if self.total_score >= 80:
            return "A"
        if self.total_score >= 60:
            return "B"
        return "C"

    def print_report(self) -> None:
        print(f"\n{'=' * 50}")
        print(f"文件: {self.file_path}")
        print(f"总分: {self.total_score} / 100  等级: {self.grade}")
        print("-" * 50)

        for dim in [
            self.summary_quality,
            self.technical_depth,
            self.format_compliance,
            self.tag_accuracy,
            self.hollow_word_check,
        ]:
            bar_str = f" {dim.score}/{dim.max_score}"
            print(f"  {dim.name:<10} {dim.bar}{bar_str}")
            for detail in dim.details:
                print(f"    - {detail}")


def score_summary_quality(summary: str, tech_keywords: set[str] = TECH_KEYWORDS) -> DimensionScore:
    reasons: list[str] = []
    length = len(summary)

    if length >= 50:
        score = 25
        reasons.append(f"摘要长度 {length} 字，满分")
    elif length >= 20:
        score = 15
        reasons.append(f"摘要长度 {length} 字，20-50字基本分 15")
    else:
        score = 0
        reasons.append(f"摘要长度 {length} 字，低于 20 字不得分")

    found_keywords = [kw for kw in tech_keywords if kw.lower() in summary.lower()]
    if found_keywords:
        score = min(score + 5, 25)
        reasons.append(f"含技术关键词: {', '.join(found_keywords[:5])} (+5)")

    return DimensionScore("摘要质量", score, 25, reasons)


def score_technical_depth(score_field: float) -> DimensionScore:
    mapped = score_field * 2.5
    score = int(mapped)
    return DimensionScore(
        "技术深度", score, 25, [f"score={score_field} → {mapped:.1f} (×2.5)"]
    )


def score_format_compliance(data: dict) -> DimensionScore:
    items = [
        ("id", "id" in data and isinstance(data.get("id"), str) and data["id"]),
        ("title", "title" in data and isinstance(data.get("title"), str) and data["title"]),
        ("source_url", "source_url" in data and isinstance(data.get("source_url"), str) and URL_PATTERN.match(str(data.get("source_url", "")))),
        ("status", "status" in data and data["status"] in VALID_STATUSES),
        ("timestamp", ("fetched_at" in data or "analyzed_at" in data) and isinstance(data.get("fetched_at") or data.get("analyzed_at"), str)),
    ]

    details: list[str] = []
    total = 0
    for name, passed in items:
        points = 4 if passed else 0
        total += points
        details.append(f"{name}: {points}/4 {'[OK]' if passed else '[--]'}")


    return DimensionScore("格式规范", total, 20, details)


def score_tag_accuracy(tags: list, standard: set[str] = STANDARD_TAGS) -> DimensionScore:
    reasons: list[str] = []
    count = len(tags)

    if count == 0:
        reasons.append("无标签，不得分")
        return DimensionScore("标签精度", 0, 15, reasons)
    elif 1 <= count <= 3:
        score = 15
        reasons.append(f"标签数量 {count}，1-3 个最佳满分")
    elif count <= 5:
        score = 10
        reasons.append(f"标签数量 {count}，4-5 个得 10 分")
    else:
        score = 5
        reasons.append(f"标签数量 {count}，超过 5 个得 5 分")

    valid_tags = [str(t) for t in tags if str(t) in standard]
    if valid_tags:
        reasons.append(f"标准标签: {', '.join(valid_tags)}")

    return DimensionScore("标签精度", score, 15, reasons)


def score_hollow_words(summary: str, title: str = "") -> DimensionScore:
    text = summary + title
    found_cn = [w for w in HOLLOW_WORDS_CN if w in text]
    found_en = [w for w in HOLLOW_WORDS_EN if w.lower() in text.lower()]

    if not found_cn and not found_en:
        return DimensionScore("空洞词检测", 15, 15, ["未检测到空洞词"])

    found = found_cn + found_en
    return DimensionScore(
        "空洞词检测", 0, 15, [f"检测到空洞词: {', '.join(found)}"]
    )


def assess_quality(file_path: Path) -> tuple[bool, QualityReport]:
    try:
        with file_path.open(encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        report = QualityReport(file_path=str(file_path))
        report.summary_quality.details.append("JSON 解析失败")
        return False, report

    if not isinstance(data, dict):
        report = QualityReport(file_path=str(file_path))
        report.summary_quality.details.append("根对象必须是 dict")
        return False, report

    report = QualityReport(file_path=str(file_path))

    summary = data.get("summary", "") if isinstance(data.get("summary"), str) else ""
    tags = data.get("tags", []) if isinstance(data.get("tags"), list) else []
    score_field = data.get("score")
    title = data.get("title", "") if isinstance(data.get("title"), str) else ""

    report.summary_quality = score_summary_quality(summary)

    if isinstance(score_field, (int, float)) and 1.0 <= score_field <= 10.0:
        report.technical_depth = score_technical_depth(score_field)
    else:
        report.technical_depth = DimensionScore(
            "技术深度", 0, 25, ["score 缺失或超出范围"]
        )

    report.format_compliance = score_format_compliance(data)
    report.tag_accuracy = score_tag_accuracy(tags)
    report.hollow_word_check = score_hollow_words(summary, title)

    return True, report


def collect_files(paths: list[str]) -> list[Path]:
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


def print_progress(current: int, total: int, filename: str, grade: str) -> None:
    bar_width = 30
    filled = int(current / total * bar_width)
    bar = ">" * filled + "." * (bar_width - filled)
    print(f"\r[{bar}] {current}/{total} {filename:<40} [{grade}]", end="", flush=True)


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python hooks/check_quality.py <json_file> [json_file2 ...]")
        sys.exit(1)

    files = collect_files(sys.argv[1:])
    if not files:
        print("未找到匹配的 JSON 文件")
        sys.exit(1)

    reports: list[QualityReport] = []
    grade_a = 0
    grade_b = 0
    grade_c = 0

    print(f"\n开始质量评分，共 {len(files)} 个文件...\n")

    for idx, file_path in enumerate(files, 1):
        _, report = assess_quality(file_path)
        reports.append(report)

        if report.grade == "A":
            grade_a += 1
        elif report.grade == "B":
            grade_b += 1
        else:
            grade_c += 1

        print_progress(idx, len(files), file_path.name, report.grade)

    print("\n")

    for report in reports:
        report.print_report()

    print(f"\n{'=' * 50}")
    print(f"评分完成: 总计 {len(files)} | A={grade_a} | B={grade_b} | C={grade_c}")

    return 1 if grade_c > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
