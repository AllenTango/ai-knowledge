"""多 Agent 预算守卫 — CostGuard。

实现 LLM 调用的成本追踪与预算保护，防止 Token 费用超出预期。

Usage:
    python tests/cost_guard.py
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class BudgetExceededError(Exception):
    """预算超限异常。

    当累计成本超出 budget_yuan 时，check() 抛出此异常。
    """

    def __init__(self, total_cost: float, budget: float):
        self.total_cost = total_cost
        self.budget = budget
        super().__init__(
            f"预算超限: 已消费 ¥{total_cost:.4f}，预算 ¥{budget:.4f}，"
            f"超出 ¥{total_cost - budget:.4f}"
        )


@dataclass
class CostRecord:
    """单次 LLM 调用成本记录。

    Attributes:
        timestamp: 调用时间（ISO 8601）。
        node_name: 调用发生的节点名称（如 "analyze", "review"）。
        prompt_tokens: 输入 Token 数量。
        completion_tokens: 输出 Token 数量。
        cost_yuan: 本次调用成本（元）。
        model: 模型名称。
    """

    timestamp: str
    node_name: str
    prompt_tokens: int
    completion_tokens: int
    cost_yuan: float
    model: str


class CostGuard:
    """LLM 调用预算守卫。

    三重保护：
    1. record() — 记录每次 LLM 调用
    2. check() — 检查预算，超限时抛出 BudgetExceededError
    3. get_report() — 按节点分组生成成本报告

    成本计算公式：
        cost = (prompt_tokens / 1_000_000) * input_price
             + (completion_tokens / 1_000_000) * output_price

    Args:
        budget_yuan: 预算上限（元），默认 1.0。
        alert_threshold: 预警阈值（0.0-1.0），默认 0.8，
            达到此比例时 check() 返回 status="warning" 而不抛异常。
        input_price_per_million: 输入价格（元/百万 Token），默认 1.0。
        output_price_per_million: 输出价格（元/百万 Token），默认 2.0。
    """

    def __init__(
        self,
        budget_yuan: float = 1.0,
        alert_threshold: float = 0.8,
        input_price_per_million: float = 1.0,
        output_price_per_million: float = 2.0,
    ):
        self.budget_yuan = budget_yuan
        self.alert_threshold = alert_threshold
        self.input_price = input_price_per_million
        self.output_price = output_price_per_million

        self._records: list[CostRecord] = []

    def _calc_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """计算单次调用成本。

        Args:
            prompt_tokens: 输入 Token 数。
            completion_tokens: 输出 Token 数。

        Returns:
            成本（元）。
        """
        cost = (
            (prompt_tokens / 1_000_000) * self.input_price
            + (completion_tokens / 1_000_000) * self.output_price
        )
        return cost

    def record(
        self,
        node_name: str,
        usage: dict[str, int],
        model: str = "",
    ) -> CostRecord:
        """记录一次 LLM 调用。

        Args:
            node_name: 节点名称（如 "analyze", "review"）。
            usage: 用量字典，格式 {"prompt_tokens": int, "completion_tokens": int}。
            model: 模型名称。

        Returns:
            新创建的 CostRecord。
        """
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        cost_yuan = self._calc_cost(prompt_tokens, completion_tokens)

        record = CostRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            node_name=node_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_yuan=cost_yuan,
            model=model,
        )
        self._records.append(record)
        return record

    def _total_cost(self) -> float:
        """累计成本。

        Returns:
            所有记录的成本之和（元）。
        """
        return sum(r.cost_yuan for r in self._records)

    def check(self) -> dict[str, Any]:
        """检查预算状态。

        Returns:
            状态字典：
            {
                "status": "ok" | "warning" | "exceeded",
                "total_cost": float,
                "budget": float,
                "usage_ratio": float,
                "message": str
            }

        Raises:
            BudgetExceededError: 当 total_cost > budget_yuan 时。
        """
        total_cost = self._total_cost()
        usage_ratio = total_cost / self.budget_yuan if self.budget_yuan > 0 else 0.0

        if total_cost > self.budget_yuan:
            raise BudgetExceededError(total_cost, self.budget_yuan)

        if usage_ratio >= self.alert_threshold:
            status = "warning"
            message = (
                f"预算预警: 已使用 {usage_ratio * 100:.1f}%，"
                f"消费 ¥{total_cost:.4f} / ¥{self.budget_yuan:.4f}"
            )
        else:
            status = "ok"
            message = (
                f"预算正常: 已使用 {usage_ratio * 100:.1f}%，"
                f"消费 ¥{total_cost:.4f} / ¥{self.budget_yuan:.4f}"
            )

        return {
            "status": status,
            "total_cost": round(total_cost, 6),
            "budget": self.budget_yuan,
            "usage_ratio": round(usage_ratio, 4),
            "message": message,
        }

    def get_report(self) -> dict[str, Any]:
        """生成成本报告（按节点分组统计）。

        Returns:
            报告字典：
            {
                "total_cost_yuan": float,
                "total_prompt_tokens": int,
                "total_completion_tokens": int,
                "total_tokens": int,
                "usage_ratio": float,
                "budget_yuan": float,
                "by_node": {
                    "<node_name>": {
                        "calls": int,
                        "prompt_tokens": int,
                        "completion_tokens": int,
                        "cost_yuan": float,
                        "models": list[str]
                    },
                    ...
                },
                "records": [list of CostRecord dicts]
            }
        """
        by_node: dict[str, dict[str, Any]] = {}
        for record in self._records:
            node = record.node_name
            if node not in by_node:
                by_node[node] = {
                    "calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cost_yuan": 0.0,
                    "models": [],
                }
            by_node[node]["calls"] += 1
            by_node[node]["prompt_tokens"] += record.prompt_tokens
            by_node[node]["completion_tokens"] += record.completion_tokens
            by_node[node]["cost_yuan"] += record.cost_yuan
            if record.model and record.model not in by_node[node]["models"]:
                by_node[node]["models"].append(record.model)

        for node_data in by_node.values():
            node_data["cost_yuan"] = round(node_data["cost_yuan"], 6)

        total_prompt = sum(r.prompt_tokens for r in self._records)
        total_completion = sum(r.completion_tokens for r in self._records)
        total_cost = self._total_cost()

        return {
            "total_cost_yuan": round(total_cost, 6),
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "usage_ratio": round(total_cost / self.budget_yuan, 4) if self.budget_yuan > 0 else 0.0,
            "budget_yuan": self.budget_yuan,
            "by_node": by_node,
            "records": [
                {
                    "timestamp": r.timestamp,
                    "node_name": r.node_name,
                    "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens,
                    "cost_yuan": round(r.cost_yuan, 6),
                    "model": r.model,
                }
                for r in self._records
            ],
        }

    def save_report(self, path: str | Path | None = None) -> str:
        """保存成本报告到 JSON 文件。

        Args:
            path: 输出路径，默认 "cost_report_{timestamp}.json"。

        Returns:
            保存的文件路径。
        """
        if path is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            path = Path(f"cost_report_{timestamp}.json")
        else:
            path = Path(path)

        report = self.get_report()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return str(path)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    sys.stdout.write("=== CostGuard 测试 ===\n\n")

    # 测试 1: 成本追踪正确性
    sys.stdout.write("【测试1】成本追踪正确性\n")
    guard = CostGuard(budget_yuan=1.0, alert_threshold=0.8)

    usage1 = {"prompt_tokens": 500, "completion_tokens": 200}
    guard.record("analyze", usage1, model="deepseek-chat")
    cost1 = guard._calc_cost(500, 200)
    expected_cost1 = (500 / 1_000_000) * 1.0 + (200 / 1_000_000) * 2.0
    assert abs(cost1 - expected_cost1) < 1e-9, f"成本计算错误: {cost1} vs {expected_cost1}"
    assert guard._records[0].node_name == "analyze"
    assert guard._records[0].prompt_tokens == 500
    assert guard._records[0].completion_tokens == 200
    sys.stdout.write(f"  PASS: 单次调用成本=¥{cost1:.6f}（预期 ¥{expected_cost1:.6f}）\n")

    usage2 = {"prompt_tokens": 1000, "completion_tokens": 500}
    guard.record("review", usage2, model="deepseek-chat")
    total_cost = guard._total_cost()
    expected_total = (1500 / 1_000_000) * 1.0 + (700 / 1_000_000) * 2.0
    assert abs(total_cost - expected_total) < 1e-9, f"累计成本错误: {total_cost} vs {expected_total}"
    sys.stdout.write(f"  PASS: 累计成本=¥{total_cost:.6f}（预期 ¥{expected_total:.6f}）\n")

    report = guard.get_report()
    assert report["total_prompt_tokens"] == 1500
    assert report["total_completion_tokens"] == 700
    assert report["total_tokens"] == 2200
    assert report["by_node"]["analyze"]["calls"] == 1
    assert report["by_node"]["analyze"]["prompt_tokens"] == 500
    assert report["by_node"]["review"]["calls"] == 1
    assert report["by_node"]["review"]["prompt_tokens"] == 1000
    sys.stdout.write(f"  PASS: 报告生成正确，by_node 分组准确\n\n")

    # 测试 2: 预算超限检测（check() 抛出 BudgetExceededError）
    sys.stdout.write("【测试2】预算超限检测\n")
    guard2 = CostGuard(budget_yuan=0.0005, alert_threshold=0.8)
    try:
        guard2.record("analyze", {"prompt_tokens": 300, "completion_tokens": 200})
        guard2.check()
        sys.stdout.write("  FAIL: 未抛出 BudgetExceededError\n")
        sys.exit(1)
    except BudgetExceededError as e:
        assert e.total_cost > e.budget
        sys.stdout.write(f"  PASS: 抛出 BudgetExceededError — {e}\n\n")

    # 测试 3: 预警阈值触发（check() 返回 status="warning"）
    sys.stdout.write("【测试3】预警阈值触发（80% 预警）\n")
    guard3 = CostGuard(budget_yuan=1.0, alert_threshold=0.8)
    cost_per_call = guard3._calc_cost(400, 400)
    for _ in range(1):
        guard3.record("analyze", {"prompt_tokens": 400, "completion_tokens": 400})

    ratio = guard3._total_cost() / guard3.budget_yuan
    if ratio >= 0.8:
        status = guard3.check()
        assert status["status"] == "warning", f"预期 warning，实际 {status['status']}"
        assert "warning" in status["message"].lower()
        sys.stdout.write(f"  PASS: status=warning，ratio={ratio:.4f} >= 0.8，message={status['message']}\n")
    else:
        needed = int((0.8 * guard3.budget_yuan - guard3._total_cost()) / cost_per_call) + 1
        for _ in range(needed):
            guard3.record("analyze", {"prompt_tokens": 400, "completion_tokens": 400})
        status = guard3.check()
        assert status["status"] == "warning"
        sys.stdout.write(f"  PASS: 多次 record 后达到预警阈值，status=warning\n\n")

    # 测试 4: check() 返回 status="ok" 场景
    sys.stdout.write("【测试4】预算正常状态\n")
    guard4 = CostGuard(budget_yuan=10.0, alert_threshold=0.8)
    guard4.record("analyze", {"prompt_tokens": 100, "completion_tokens": 50})
    status4 = guard4.check()
    assert status4["status"] == "ok"
    assert status4["total_cost"] < guard4.budget_yuan * guard4.alert_threshold
    sys.stdout.write(f"  PASS: status=ok，total_cost=¥{status4['total_cost']:.6f}\n\n")

    # 测试 5: get_report() 按节点分组
    sys.stdout.write("【测试5】按节点分组报告\n")
    guard5 = CostGuard(budget_yuan=1.0)
    guard5.record("analyze", {"prompt_tokens": 100, "completion_tokens": 50})
    guard5.record("analyze", {"prompt_tokens": 200, "completion_tokens": 100})
    guard5.record("review", {"prompt_tokens": 300, "completion_tokens": 150})
    report5 = guard5.get_report()
    assert "analyze" in report5["by_node"]
    assert "review" in report5["by_node"]
    assert report5["by_node"]["analyze"]["calls"] == 2
    assert report5["by_node"]["analyze"]["prompt_tokens"] == 300
    assert report5["by_node"]["review"]["calls"] == 1
    sys.stdout.write(f"  PASS: analyze(2次), review(1次)，分组正确\n\n")

    # 测试 6: save_report() 文件输出
    sys.stdout.write("【测试6】save_report() 文件输出\n")
    test_path = Path(__file__).resolve().parent / "test_cost_report.json"
    saved_path = guard5.save_report(path=test_path)
    assert Path(saved_path).exists()
    with open(test_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert "total_cost_yuan" in loaded
    assert "by_node" in loaded
    assert "records" in loaded
    sys.stdout.write(f"  PASS: 报告已保存到 {saved_path}\n\n")

    sys.stdout.write("=== 全部测试通过 ===\n")