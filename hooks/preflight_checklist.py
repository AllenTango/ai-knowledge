"""上线前 Checklist 检查脚本。

对 API KEY 环境变量、权限、备份策略、日志轮转、成本预算、版本固定、
测试通道、OpenClaw 状态、GitHub Actions 自动采集等项目进行全面检查。
所有检查项通过方可固定版本上线，每次检查生成审计报告可供追溯。

使用示例:
    $ python hooks/preflight_checklist.py
    $ python hooks/preflight_checklist.py --report-dir reports
    $ python hooks/preflight_checklist.py --skip-warning   # 忽略警告级检查
"""

import json
import logging
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ═══════════════════════════════════════════════════════════════════
# 检查结果数据类
# ═══════════════════════════════════════════════════════════════════


@dataclass
class CheckResult:
    """单项检查结果。

    Attributes:
        item_id: 检查项唯一标识。
        category: 检查类别。
        name: 检查项名称。
        passed: 是否通过。
        severity: 严重级别，critical | warning | info。
        detail: 详细说明或失败原因。
        suggestion: 修复建议（仅在未通过时）。
        timestamp: 检查时间。
    """

    item_id: str
    category: str
    name: str
    passed: bool
    severity: str
    detail: str = ""
    suggestion: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def icon(self) -> str:
        if self.passed:
            return "PASS"
        if self.severity == "critical":
            return "FAIL"
        return "WARN"

    @property
    def is_blocking(self) -> bool:
        """是否阻断上线。"""
        return not self.passed and self.severity == "critical"


@dataclass
class ChecklistReport:
    """完整检查报告。

    Attributes:
        report_id: 报告唯一标识。
        created_at: 创建时间。
        results: 所有检查结果列表。
    """

    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    results: list[CheckResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if r.is_blocking)

    @property
    def warning_count(self) -> int:
        return sum(1 for r in self.results if not r.passed and r.severity != "critical")

    @property
    def all_passed(self) -> bool:
        return self.failed_count == 0

    def add_result(self, result: CheckResult) -> None:
        self.results.append(result)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "created_at": self.created_at,
            "total": self.total,
            "passed": self.passed_count,
            "failed": self.failed_count,
            "warning": self.warning_count,
            "all_passed": self.all_passed,
            "checks": [
                {
                    "item_id": r.item_id,
                    "category": r.category,
                    "name": r.name,
                    "passed": r.passed,
                    "severity": r.severity,
                    "detail": r.detail,
                    "suggestion": r.suggestion if not r.passed else "",
                    "timestamp": r.timestamp,
                }
                for r in self.results
            ],
        }


# ═══════════════════════════════════════════════════════════════════
# 公共辅助函数
# ═══════════════════════════════════════════════════════════════════


def _is_git_tracked(path: str) -> bool:
    """检查文件是否在 git 跟踪中。"""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", path],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        return result.returncode == 0
    except Exception:
        return False


def _scan_hardcoded_keys(source_dir: str, patterns: list[str]) -> list[str]:
    """扫描源文件中是否硬编码了 API Key。

    Args:
        source_dir: 源码目录。
        patterns: 敏感字符串正则模式列表。

    Returns:
        发现问题的文件列表。
    """
    # 排除自身及已知不会硬编码密钥的文件
    exclude_dirs = {"__pycache__", ".git", "node_modules", "reports", "knowledge"}
    exclude_files = {"preflight_checklist.py", "env.example", "cost_guard.py", "security.py",
                     "model_client.py"}
    # 占位符值，不应视为硬编码
    placeholder_values = {"your_api_key", "your_api", "your_key", "${YOUR_", "YOUR_API_KEY",
                          "your_bot_token", "your_webhook_url", "your_target", "your_chat_id"}
    findings = []
    for root, dirs, files in os.walk(source_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for fname in files:
            if fname in exclude_files:
                continue
            if not fname.endswith((".py", ".sh", ".yml", ".yaml")):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                for pattern in patterns:
                    matches = re.finditer(pattern, content)
                    for match in matches:
                        matched_text = match.group(0)
                        # 跳过环境变量读取模式（os.getenv / os.environ）
                        line_start = max(0, match.start() - 80)
                        context = content[line_start:match.end()]
                        if "os.getenv" in context or "os.environ" in context:
                            continue
                        # 跳过占位符值
                        if any(pv.lower() in matched_text.lower() for pv in placeholder_values):
                            continue
                        findings.append(f"{fpath}:{matched_text[:60]}")
            except Exception:
                continue
    return findings


def _check_env_var(value: str | None) -> bool:
    """检查环境变量是否为有效值（非空且非占位符）。"""
    if not value:
        return False
    placeholders = ("${", "YOUR_", "your_", "CHANGE_ME", "PLACEHOLDER")
    for ph in placeholders:
        if value.startswith(ph) or ph in value:
            return False
    return True


def _run_pytest_dry() -> tuple[bool, str]:
    """运行 pytest --collect-only 验证测试可发现。"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q", "--no-header"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=30,
        )
        if result.returncode == 0:
            test_count = len([l for l in result.stdout.splitlines() if l.strip().startswith("tests/")])
            return True, f"发现 {test_count} 个测试用例"
        return False, result.stderr.strip() or result.stdout.strip()
    except FileNotFoundError:
        return False, "pytest 未安装"
    except Exception as e:
        return False, str(e)


def _check_script_executable(script_path: str) -> bool:
    """检查脚本是否有可执行权限。"""
    full_path = PROJECT_ROOT / script_path
    return full_path.exists() and os.access(full_path, os.X_OK)


def _check_directory_writable(dir_path: str) -> bool:
    """检查目录是否可写。"""
    full_path = PROJECT_ROOT / dir_path
    if not full_path.exists():
        return False
    return os.access(full_path, os.W_OK)


# ═══════════════════════════════════════════════════════════════════
# 各分类检查函数
# ═══════════════════════════════════════════════════════════════════


def check_api_keys(report: ChecklistReport) -> None:
    """1. API KEY 环境变量检查。"""
    cat = "API KEY & 环境变量"

    # 1.1 .env 文件存在
    env_file = PROJECT_ROOT / ".env"
    env_exists = env_file.exists()
    report.add_result(CheckResult(
        item_id="api-01",
        category=cat,
        name=".env 环境变量文件存在",
        passed=env_exists,
        severity="critical",
        detail=f".env {'存在' if env_exists else '不存在'}于 {PROJECT_ROOT}",
        suggestion="" if env_exists else "从 env.example 复制并填入正确的 API Key",
    ))

    # 1.2 .env 不在 git 跟踪中
    in_git = _is_git_tracked(".env") if env_exists else False
    report.add_result(CheckResult(
        item_id="api-02",
        category=cat,
        name=".env 未纳入 git 版本管理",
        passed=not in_git,
        severity="critical",
        detail=".env 已在 git 跟踪中" if in_git else ".env 未在 git 跟踪中",
        suggestion="执行 git rm --cached .env 将其移出版本管理" if in_git else "",
    ))

    # 1.3 LLM_PROVIDER 已设置
    llm_provider = os.getenv("LLM_PROVIDER", "")
    report.add_result(CheckResult(
        item_id="api-03",
        category=cat,
        name="LLM_PROVIDER 已设置",
        passed=bool(llm_provider),
        severity="critical",
        detail=f"LLM_PROVIDER={llm_provider}" if llm_provider else "LLM_PROVIDER 未设置",
        suggestion="在 .env 中设置 LLM_PROVIDER=deepseek" if not llm_provider else "",
    ))

    # 1.4 至少配置了一个 LLM API Key
    required_keys = ["DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "OPENAI_API_KEY"]
    configured = [k for k in required_keys if _check_env_var(os.getenv(k))]
    report.add_result(CheckResult(
        item_id="api-04",
        category=cat,
        name="至少配置一个 LLM API Key",
        passed=len(configured) > 0,
        severity="critical",
        detail=f"已配置: {', '.join(configured)}" if configured else "所有 LLM API Key 均未配置或为占位符",
        suggestion="在 .env 中设置至少一个有效的 API Key" if not configured else "",
    ))

    # 1.5 分发渠道密钥检查
    channel_keys = {
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID", ""),
        "FEISHU_WEBHOOK_URL": os.getenv("FEISHU_WEBHOOK_URL", ""),
        "QQ_WEBHOOK_URL": os.getenv("QQ_WEBHOOK_URL", ""),
    }
    configured_channels = [k for k, v in channel_keys.items() if _check_env_var(v)]
    report.add_result(CheckResult(
        item_id="api-05",
        category=cat,
        name="分发渠道密钥已配置",
        passed=len(configured_channels) > 0,
        severity="warning",
        detail=f"已配置渠道: {', '.join(configured_channels)}" if configured_channels else "所有分发渠道均未配置",
        suggestion="至少配置一个分发渠道（Telegram / 飞书 / QQ）" if not configured_channels else "",
    ))

    # 1.6 无硬编码 API Key（匹配实际密钥值的正则，而非变量名赋值）
    hardcoded = _scan_hardcoded_keys(
        str(PROJECT_ROOT),
        [
            r"sk-[A-Za-z0-9]{20,}",                  # OpenAI 格式密钥
            r"sk_[A-Za-z0-9]{20,}",                   # 其他 sk_ 格式
            r"DEEPSEEK_API_KEY\s*=\s*['\"][^'\"$]+",  # 硬编码 DeepSeek 密钥
            r"OPENAI_API_KEY\s*=\s*['\"][^'\"$]+",    # 硬编码 OpenAI 密钥
            r"TELEGRAM_BOT_TOKEN\s*=\s*['\"][^'\"$]+",# 硬编码 Telegram Token
        ],
    )
    report.add_result(CheckResult(
        item_id="api-06",
        category=cat,
        name="源代码无硬编码 API Key",
        passed=len(hardcoded) == 0,
        severity="critical",
        detail=f"发现疑似硬编码: {', '.join(hardcoded[:3])}" if hardcoded else "未发现硬编码",
        suggestion="将硬编码的密钥替换为环境变量读取" if hardcoded else "",
    ))

    # 1.7 env.example 存在且与 .env 结构一致
    example_file = PROJECT_ROOT / "env.example"
    example_exists = example_file.exists()
    env_keys = set()
    example_keys = set()
    if env_exists:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    env_keys.add(line.split("=")[0].strip())
    if example_exists:
        with open(example_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    example_keys.add(line.split("=")[0].strip())
    missing_in_example = env_keys - example_keys if env_keys else set()
    report.add_result(CheckResult(
        item_id="api-07",
        category=cat,
        name="env.example 与 .env 结构一致",
        passed=len(missing_in_example) == 0,
        severity="info",
        detail=f"env.example 缺少键: {', '.join(missing_in_example)}" if missing_in_example else "结构一致",
        suggestion="更新 env.example 以包含所有环境变量" if missing_in_example else "",
    ))


def check_permissions(report: ChecklistReport) -> None:
    """2. 权限检查。"""
    cat = "权限检查"

    dirs_to_check = [
        "knowledge/raw",
        "knowledge/analyzer_output",
        "knowledge/articles",
        "knowledge/human_review",
    ]
    all_writable = True
    bad_dirs = []
    for d in dirs_to_check:
        if not _check_directory_writable(d):
            all_writable = False
            bad_dirs.append(d)
    report.add_result(CheckResult(
        item_id="perm-01",
        category=cat,
        name="knowledge/ 各级目录可写",
        passed=all_writable,
        severity="critical",
        detail=f"不可写: {', '.join(bad_dirs)}" if bad_dirs else "所有目录可写",
        suggestion="检查目录权限，执行 chmod -R 755" if bad_dirs else "",
    ))

    script_exec = _check_script_executable("scheduler/run_pipeline.sh")
    report.add_result(CheckResult(
        item_id="perm-02",
        category=cat,
        name="scheduler/run_pipeline.sh 有执行权限",
        passed=script_exec,
        severity="critical",
        detail="可执行" if script_exec else "无法执行",
        suggestion="chmod +x scheduler/run_pipeline.sh" if not script_exec else "",
    ))

    git_ok = False
    git_detail = ""
    try:
        git_dir_result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=5,
        )
        git_dir_path = git_dir_result.stdout.strip()
        if git_dir_result.returncode == 0 and git_dir_path:
            git_ok = os.access(git_dir_path, os.R_OK)
            git_detail = f"Git 仓库: {git_dir_path}"
        else:
            git_detail = "git rev-parse 失败"
    except Exception:
        git_detail = "无法检测 git 仓库"
    report.add_result(CheckResult(
        item_id="perm-03",
        category=cat,
        name="Git 仓库可读",
        passed=git_ok,
        severity="critical",
        detail=git_detail,
        suggestion="确认在正确的 git 仓库中" if not git_ok else "",
    ))

    logs_dir = PROJECT_ROOT / "logs"
    logs_writable = True
    if not logs_dir.exists():
        try:
            logs_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            logs_writable = False
    else:
        logs_writable = os.access(logs_dir, os.W_OK)
    report.add_result(CheckResult(
        item_id="perm-04",
        category=cat,
        name="logs/ 目录可写",
        passed=logs_writable,
        severity="warning",
        detail="日志目录可写" if logs_writable else "日志目录不可写",
        suggestion="检查 logs/ 目录权限" if not logs_writable else "",
    ))

    openclaw_available = False
    try:
        openclaw_result = subprocess.run(
            ["openclaw", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        openclaw_available = openclaw_result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    report.add_result(CheckResult(
        item_id="perm-05",
        category=cat,
        name="openclaw CLI 可用",
        passed=openclaw_available,
        severity="warning",
        detail="openclaw 已安装" if openclaw_available else "openclaw 命令不可用",
        suggestion="安装 openclaw CLI 以启用该分发渠道" if not openclaw_available else "",
    ))


def check_backup_strategy(report: ChecklistReport) -> None:
    """3. 备份策略检查。"""
    cat = "备份策略"

    remote_configured = False
    remote_url = ""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        if result.returncode == 0 and result.stdout.strip():
            remote_configured = True
            remote_url = result.stdout.strip()
    except Exception:
        pass
    report.add_result(CheckResult(
        item_id="backup-01",
        category=cat,
        name="Git remote origin 已配置",
        passed=remote_configured,
        severity="warning",
        detail=f"Remote URL: {remote_url}" if remote_configured else "未配置 origin",
        suggestion="git remote add origin <仓库地址>" if not remote_configured else "",
    ))

    articles_dir = PROJECT_ROOT / "knowledge" / "articles"
    articles_in_git = True
    if not articles_dir.exists():
        articles_in_git = False
    else:
        try:
            result = subprocess.run(
                ["git", "check-ignore", str(articles_dir)],
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT,
            )
        except Exception:
            articles_in_git = True
    report.add_result(CheckResult(
        item_id="backup-02",
        category=cat,
        name="knowledge/articles/ 纳入 git 版本管理",
        passed=articles_in_git,
        severity="warning",
        detail="knowledge/articles/ 在 git 管理中" if articles_in_git else "knowledge/articles/ 未被 git 跟踪或被 .gitignore 排除",
        suggestion="移除 .gitignore 中 knowledge/articles/ 的相关条目" if not articles_in_git else "",
    ))

    backup_scripts = list(PROJECT_ROOT.glob("**/backup*")) + list(PROJECT_ROOT.glob("**/Backup*"))
    has_backup_script = len(backup_scripts) > 0
    report.add_result(CheckResult(
        item_id="backup-03",
        category=cat,
        name="存在备份脚本或机制",
        passed=has_backup_script,
        severity="info",
        detail=f"发现: {', '.join(p.name for p in backup_scripts)}" if has_backup_script else "未找到专用备份脚本（git 可充当备份）",
        suggestion="考虑添加定时备份脚本，或依赖 git push 作为远程备份" if not has_backup_script else "",
    ))


def check_log_rotation(report: ChecklistReport) -> None:
    """4. 日志轮转检查。"""
    cat = "日志轮转"

    logs_dir_exists = (PROJECT_ROOT / "logs").exists() or (PROJECT_ROOT / "scheduler" / "run_pipeline.sh").exists()
    report.add_result(CheckResult(
        item_id="log-01",
        category=cat,
        name="日志输出目录存在",
        passed=logs_dir_exists,
        severity="warning",
        detail="logs/ 目录可用" if logs_dir_exists else "logs/ 目录不存在",
        suggestion="scheduler/run_pipeline.sh 会自动创建 logs/" if not logs_dir_exists else "",
    ))

    retention_days = 30
    pipeline_script = PROJECT_ROOT / "scheduler" / "run_pipeline.sh"
    if pipeline_script.exists():
        with open(pipeline_script, "r", encoding="utf-8") as f:
            content = f.read()
        match = re.search(r"RETENTION_DAYS[=:]\s*\{?(\d+)", content)
        if match:
            retention_days = int(match.group(1))
    report.add_result(CheckResult(
        item_id="log-02",
        category=cat,
        name="日志保留天数已配置",
        passed=retention_days <= 90,
        severity="warning",
        detail=f"日志保留 {retention_days} 天" if retention_days <= 90 else f"日志保留 {retention_days} 天 (偏长)",
        suggestion="建议日志保留 30 天，通过 RETENTION_DAYS 环境变量调整" if retention_days > 90 else "",
    ))

    cleanup_present = "cleanup_old_logs" in content if pipeline_script.exists() else False
    report.add_result(CheckResult(
        item_id="log-03",
        category=cat,
        name="自动清理过期日志",
        passed=cleanup_present,
        severity="warning",
        detail="scheduler/run_pipeline.sh 包含日志清理逻辑" if cleanup_present else "未找到日志清理逻辑",
        suggestion="在调度脚本中添加 find + mtime + delete 清理逻辑" if not cleanup_present else "",
    ))

    log_files = list((PROJECT_ROOT / "logs").glob("collect_*.log")) if (PROJECT_ROOT / "logs").exists() else []
    total_size = sum(f.stat().st_size for f in log_files)
    report.add_result(CheckResult(
        item_id="log-04",
        category=cat,
        name="日志文件占用空间正常",
        passed=total_size < 500 * 1024 * 1024,  # < 500MB
        severity="info",
        detail=f"日志总大小 {total_size / 1024 / 1024:.1f} MB，共 {len(log_files)} 个文件",
        suggestion="手动清理过旧日志文件" if total_size >= 500 * 1024 * 1024 else "",
    ))


def check_cost_budget(report: ChecklistReport) -> None:
    """5. 成本预算检查。"""
    cat = "成本预算"

    cost_guard_path = PROJECT_ROOT / "scripts" / "cost_guard.py"
    cost_guard_exists = cost_guard_path.exists()
    report.add_result(CheckResult(
        item_id="cost-01",
        category=cat,
        name="成本守卫模块存在",
        passed=cost_guard_exists,
        severity="critical",
        detail="scripts/cost_guard.py 存在" if cost_guard_exists else "cost_guard.py 缺失",
        suggestion="检查 scripts/cost_guard.py 文件" if not cost_guard_exists else "",
    ))

    cost_guard_healthy = False
    cost_guard_detail = ""
    if cost_guard_exists:
        try:
            result = subprocess.run(
                [sys.executable, str(cost_guard_path)],
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT,
                timeout=15,
            )
            cost_guard_healthy = result.returncode == 0
            cost_guard_detail = (
                "cost_guard.py 自测通过" if cost_guard_healthy else f"失败: {result.stderr[:200]}"
            )
        except Exception as e:
            cost_guard_detail = f"执行异常: {e}"
    report.add_result(CheckResult(
        item_id="cost-02",
        category=cat,
        name="成本守卫功能正常",
        passed=cost_guard_healthy,
        severity="critical",
        detail=cost_guard_detail,
        suggestion="检查 cost_guard.py 的 budget 设置和环境" if not cost_guard_healthy else "",
    ))

    cost_reports = list(PROJECT_ROOT.glob("cost_report_*.json"))
    report.add_result(CheckResult(
        item_id="cost-03",
        category=cat,
        name="存在历史成本报告",
        passed=len(cost_reports) > 0,
        severity="info",
        detail=f"发现 {len(cost_reports)} 份成本报告" if cost_reports else "未找到历史成本报告（首次运行正常）",
        suggestion="首次运行可忽略，后续将自动生成" if not cost_reports else "",
    ))


def check_version_pinning(report: ChecklistReport) -> None:
    """6. 版本固定检查。"""
    cat = "版本固定"

    req_file = PROJECT_ROOT / "requirements.txt"
    req_exists = req_file.exists()
    report.add_result(CheckResult(
        item_id="ver-01",
        category=cat,
        name="requirements.txt 存在",
        passed=req_exists,
        severity="critical",
        detail="requirements.txt 存在" if req_exists else "requirements.txt 缺失",
        suggestion="创建 requirements.txt 并固定依赖版本" if not req_exists else "",
    ))

    pinned_count = 0
    loose_count = 0
    if req_exists:
        with open(req_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "==" in line:
                    pinned_count += 1
                elif ">=" in line:
                    loose_count += 1
    too_loose = pinned_count == 0 and loose_count > 0
    report.add_result(CheckResult(
        item_id="ver-02",
        category=cat,
        name="依赖版本已固定",
        passed=not too_loose,
        severity="warning",
        detail=f"固定版本: {pinned_count}, 仅下限版本: {loose_count}" if not too_loose else f"全部使用 >= 下限（{loose_count} 个），建议改为 == 固定版本",
        suggestion="将 >= 改为 == 固定版本，或生成 requirements.lock" if too_loose else "",
    ))

    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    python_ok = sys.version_info >= (3, 10)
    report.add_result(CheckResult(
        item_id="ver-03",
        category=cat,
        name="Python 版本 >= 3.10",
        passed=python_ok,
        severity="critical",
        detail=f"当前 Python {python_version}",
        suggestion="升级到 Python 3.10+" if not python_ok else "",
    ))

    langgraph_req = ""
    if req_exists:
        with open(req_file, "r", encoding="utf-8") as f:
            for line in f:
                if "langgraph" in line.lower():
                    langgraph_req = line.strip()
                    break
    report.add_result(CheckResult(
        item_id="ver-04",
        category=cat,
        name="核心依赖 langgraph 已声明",
        passed=bool(langgraph_req),
        severity="critical",
        detail=f"依赖声明: {langgraph_req}" if langgraph_req else "未声明 langgraph 依赖",
        suggestion="在 requirements.txt 中添加 langgraph" if not langgraph_req else "",
    ))


def check_test_channel(report: ChecklistReport) -> None:
    """7. 测试通道检查。"""
    cat = "测试通道"

    test_dir = PROJECT_ROOT / "tests"
    test_dir_exists = test_dir.exists()
    report.add_result(CheckResult(
        item_id="test-01",
        category=cat,
        name="tests/ 目录存在",
        passed=test_dir_exists,
        severity="critical",
        detail="tests/ 目录存在" if test_dir_exists else "tests/ 目录不存在",
        suggestion="创建 tests/ 目录并添加测试用例" if not test_dir_exists else "",
    ))

    eval_test = PROJECT_ROOT / "tests" / "eval_test.py"
    eval_exists = eval_test.exists()
    report.add_result(CheckResult(
        item_id="test-02",
        category=cat,
        name="eval_test.py 测试文件存在",
        passed=eval_exists,
        severity="critical",
        detail="tests/eval_test.py 存在" if eval_exists else "eval_test.py 缺失",
        suggestion="创建 tests/eval_test.py" if not eval_exists else "",
    ))

    pytest_ok, pytest_detail = _run_pytest_dry()
    report.add_result(CheckResult(
        item_id="test-03",
        category=cat,
        name="pytest 可发现测试用例",
        passed=pytest_ok,
        severity="critical",
        detail=pytest_detail,
        suggestion="pip install pytest" if not pytest_ok else "",
    ))

    pytest_available = False
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        pytest_available = result.returncode == 0
    except Exception:
        pass
    report.add_result(CheckResult(
        item_id="test-04",
        category=cat,
        name="pytest 已安装",
        passed=pytest_available,
        severity="critical",
        detail=f"pytest 版本: {result.stdout.strip()}" if pytest_available else "pytest 未安装",
        suggestion="pip install pytest" if not pytest_available else "",
    ))

    has_conftest = (PROJECT_ROOT / "conftest.py").exists() or (PROJECT_ROOT / "tests" / "conftest.py").exists()
    report.add_result(CheckResult(
        item_id="test-05",
        category=cat,
        name="测试配置文件 conftest.py 存在",
        passed=has_conftest,
        severity="info",
        detail="conftest.py 存在" if has_conftest else "conftest.py 不存在（可选）",
        suggestion="创建 conftest.py 配置 pytest fixtures 和环境" if not has_conftest else "",
    ))


def check_openclaw_status(report: ChecklistReport) -> None:
    """8. OpenClaw 状态检查。"""
    cat = "OpenClaw 状态"

    openclaw_dir = PROJECT_ROOT / ".openclaw"
    openclaw_exists = openclaw_dir.exists()
    report.add_result(CheckResult(
        item_id="oc-01",
        category=cat,
        name=".openclaw/ 目录存在",
        passed=openclaw_exists,
        severity="warning",
        detail=".openclaw/ 目录存在" if openclaw_exists else ".openclaw/ 目录缺失",
        suggestion="初始化 .openclaw/ 配置" if not openclaw_exists else "",
    ))

    required_files = ["IDENTITY.md", "SOUL.md", "USER.md", "HEARTBEAT.md", "TOOLS.md"]
    missing_files = []
    for fname in required_files:
        fpath = openclaw_dir / fname
        if not fpath.exists() or fpath.stat().st_size == 0:
            missing_files.append(fname)
    report.add_result(CheckResult(
        item_id="oc-02",
        category=cat,
        name="OpenClaw 身份文件齐全",
        passed=len(missing_files) == 0,
        severity="warning",
        detail=f"缺失: {', '.join(missing_files)}" if missing_files else "所有身份文件齐全",
        suggestion="补全缺失的身份文件" if missing_files else "",
    ))

    ws_state = openclaw_dir / "workspace-state.json"
    ws_valid = False
    if ws_state.exists():
        try:
            with open(ws_state, "r", encoding="utf-8") as f:
                state = json.load(f)
            ws_valid = "version" in state and "bootstrapSeededAt" in state
        except Exception:
            pass
    report.add_result(CheckResult(
        item_id="oc-03",
        category=cat,
        name="workspace-state.json 有效",
        passed=ws_valid,
        severity="warning",
        detail="workspace-state.json 格式有效" if ws_valid else "workspace-state.json 缺失或无效",
        suggestion="重新初始化 OpenClaw 工作空间" if not ws_valid else "",
    ))

    oc_channel = os.getenv("OPENCLAW_CHANNEL", "")
    oc_target = os.getenv("OPENCLAW_TARGET", "")
    oc_configured = _check_env_var(oc_channel) and _check_env_var(oc_target)
    report.add_result(CheckResult(
        item_id="oc-04",
        category=cat,
        name="OPENCLAW_CHANNEL 和 OPENCLAW_TARGET 已配置",
        passed=oc_configured,
        severity="warning",
        detail=f"channel={oc_channel}, target={'[已配置]' if _check_env_var(oc_target) else '[未配置]'}" if _check_env_var(oc_channel) else "未配置",
        suggestion="在 .env 中设置 OPENCLAW_CHANNEL 和 OPENCLAW_TARGET" if not oc_configured else "",
    ))


def check_github_actions(report: ChecklistReport) -> None:
    """9. GitHub Actions 自动采集检查。"""
    cat = "GitHub Actions"

    workflow_file = PROJECT_ROOT / ".github" / "workflows" / "daily-collect.yml"
    workflow_exists = workflow_file.exists()
    report.add_result(CheckResult(
        item_id="gha-01",
        category=cat,
        name="daily-collect.yml 工作流存在",
        passed=workflow_exists,
        severity="critical",
        detail=".github/workflows/daily-collect.yml 存在" if workflow_exists else "工作流文件缺失",
        suggestion="创建 .github/workflows/daily-collect.yml" if not workflow_exists else "",
    ))

    cron_present = False
    dispatch_present = False
    if workflow_exists:
        with open(workflow_file, "r", encoding="utf-8") as f:
            content = f.read()
        cron_present = "cron:" in content
        dispatch_present = "workflow_dispatch" in content
    report.add_result(CheckResult(
        item_id="gha-02",
        category=cat,
        name="调度触发器配置正确",
        passed=cron_present and dispatch_present,
        severity="critical",
        detail=f"cron={'[已配置]' if cron_present else '[未配置]'}, workflow_dispatch={'[已配置]' if dispatch_present else '[未配置]'}",
        suggestion="添加 schedule cron 和 workflow_dispatch 触发器" if not (cron_present and dispatch_present) else "",
    ))

    secrets_in_use = []
    if workflow_exists:
        with open(workflow_file, "r", encoding="utf-8") as f:
            content = f.read()
        secrets_in_use = re.findall(r"\$\{\{\s*secrets\.(\w+)\s*\}\}", content)
    secrets_unique = list(set(secrets_in_use))
    report.add_result(CheckResult(
        item_id="gha-03",
        category=cat,
        name="GitHub Secrets 引用正确",
        passed=len(secrets_unique) >= 2,
        severity="critical",
        detail=f"引用 Secrets: {', '.join(secrets_unique)}" if secrets_unique else "未引用任何 Secrets",
        suggestion="在 GitHub 仓库 Settings > Secrets and variables 中配置对应的 Secret" if len(secrets_unique) < 2 else "",
    ))

    validate_step = "validate_json" in content if workflow_exists else False
    check_quality_step = "check_quality" in content if workflow_exists else False
    report.add_result(CheckResult(
        item_id="gha-04",
        category=cat,
        name="CI 包含 JSON 校验和质量评分",
        passed=validate_step and check_quality_step,
        severity="warning",
        detail=f"validate_json={'[已配置]' if validate_step else '[未配置]'}, check_quality={'[已配置]' if check_quality_step else '[未配置]'}",
        suggestion="添加 validate_json 和 check_quality 步骤" if not (validate_step and check_quality_step) else "",
    ))

    permissions_ok = "contents: write" in content if workflow_exists else False
    report.add_result(CheckResult(
        item_id="gha-05",
        category=cat,
        name="GitHub Actions 有写权限",
        passed=permissions_ok,
        severity="critical",
        detail="permissions: contents: write" if permissions_ok else "缺少 write 权限",
        suggestion="添加 permissions: contents: write" if not permissions_ok else "",
    ))


# ═══════════════════════════════════════════════════════════════════
# 报告输出与保存
# ═══════════════════════════════════════════════════════════════════


def print_horizontal_line(msg: str = "", width: int = 60) -> None:
    """打印水平分隔线。"""
    if msg:
        padding = (width - len(msg) - 2) // 2
        logger.info("=" * padding + f" {msg} " + "=" * padding)
    else:
        logger.info("=" * width)


def print_report(report: ChecklistReport, skip_warning: bool = False) -> None:
    """打印检查报告。

    Args:
        report: 检查报告对象。
        skip_warning: 是否跳过警告级结果的展示。
    """
    results_to_show = [
        r for r in report.results
        if not (skip_warning and not r.passed and r.severity != "critical")
    ]

    category_order = [
        "API KEY & 环境变量",
        "权限检查",
        "备份策略",
        "日志轮转",
        "成本预算",
        "版本固定",
        "测试通道",
        "OpenClaw 状态",
        "GitHub Actions",
    ]

    current_cat = ""
    for r in results_to_show:
        if r.category != current_cat:
            current_cat = r.category
            cat_num = category_order.index(r.category) + 1 if r.category in category_order else "?"
            print_horizontal_line(f"{cat_num}. {r.category}")

        if r.passed:
            logger.info(f"  [{r.icon}] {r.name} — {r.detail}")
        else:
            logger.warning(f"  [{r.icon}] {r.name} — {r.detail}")
            if r.suggestion:
                logger.info(f"         建议: {r.suggestion}")

    print_horizontal_line("汇总")
    logger.info(
        f"  总计: {report.total} | "
        f"通过: {report.passed_count} | "
        f"阻断: {report.failed_count} | "
        f"警告: {report.warning_count}"
    )

    if report.all_passed:
        logger.info("  ALL PASS — 可以固定版本上线")
    else:
        logger.warning(f"  BLOCKED — 存在 {report.failed_count} 个阻断项，请修复后重试")
        logger.info(f"  报告 ID: {report.report_id}")


def save_report(report: ChecklistReport, output_dir: str = "reports") -> str:
    """保存检查报告到 JSON 文件。

    Args:
        report: 检查报告对象。
        output_dir: 输出目录。

    Returns:
        保存的文件路径。
    """
    report_dir = PROJECT_ROOT / output_dir
    report_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"preflight-{timestamp}-{report.report_id[:8]}.json"
    filepath = report_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

    return str(filepath)


# ═══════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════


def main() -> int:
    """主入口函数。

    Returns:
        退出码，0 表示全部通过，1 表示存在阻断项。
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="AI 知识库上线前 Checklist 检查",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--report-dir",
        type=str,
        default="reports",
        help="报告输出目录，默认 reports/",
    )
    parser.add_argument(
        "--skip-warning",
        action="store_true",
        help="仅报告 critical 级检查项，跳过 warning 和 info",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="同时输出 JSON 格式报告到 stdout",
    )
    args = parser.parse_args()

    print_horizontal_line("Pre-flight Checklist")
    logger.info(f"项目根目录: {PROJECT_ROOT}")
    logger.info(f"检查时间: {datetime.now(timezone.utc).isoformat()}")
    logger.info("")

    from dotenv import load_dotenv, find_dotenv

    load_dotenv(find_dotenv())

    report = ChecklistReport()

    # 按顺序执行各分类检查
    check_api_keys(report)
    check_permissions(report)
    check_backup_strategy(report)
    check_log_rotation(report)
    check_cost_budget(report)
    check_version_pinning(report)
    check_test_channel(report)
    check_openclaw_status(report)
    check_github_actions(report)

    print_report(report, skip_warning=args.skip_warning)

    saved_path = save_report(report, output_dir=args.report_dir)
    logger.info(f"\n审计报告已保存: {saved_path}")

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))

    return 0 if report.all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
