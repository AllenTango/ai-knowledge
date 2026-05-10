"""supervisor.py 综合测试脚本。"""
import sys
import inspect

sys.path.insert(0, "D:\\Xuexi\\MultiAgentDesign\\ai-zhishiku-v3")

results = {"pass": 0, "fail": 0, "skip": 0, "details": []}
_llm_ok = False


def check(name, ok, detail=""):
    if ok:
        results["pass"] += 1
        status = "PASS"
    else:
        results["fail"] += 1
        status = "FAIL"
    msg = f"  [{status}] {name}"
    if detail:
        msg += f" -> {detail}"
    results["details"].append(msg)
    print(msg)


def skip(name, reason=""):
    results["skip"] += 1
    msg = f"  [SKIP] {name}"
    if reason:
        msg += f" -> {reason}"
    results["details"].append(msg)
    print(msg)


def section(title):
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


# ── Test 0: LLM 可用性检查 ───────────────────────────────

section("Test 0: LLM 可用性检查")

from workflows.model_client import check_llm_available

_llm_ok = check_llm_available()
if _llm_ok:
    check("LLM 可用", True)
else:
    skip("LLM 不可用 - 将跳过调 LLM 的测试", "未配置 API Key")
    from patterns.supervisor import supervisor as _s
    r = _s("test")
    check("无 LLM 时返回友好提示", "LLM" in r["output"] or "API" in r["output"])
    check("attempts=0", r["attempts"] == 0)


# ── Test 1: 函数签名验证 ──────────────────────────────────

section("Test 1: supervisor() 函数签名")

from patterns.supervisor import supervisor

sig = inspect.signature(supervisor)
params = list(sig.parameters.keys())
check("参数包含 task", "task" in params)
check("参数包含 max_retries", "max_retries" in params)
check("task 为第一个参数", params[0] == "task")

defaults = {
    k: v.default
    for k, v in sig.parameters.items()
    if v.default is not inspect.Parameter.empty
}
check("max_retries 默认值为 3", defaults.get("max_retries") == 3)
check("supervisor 参数数量为 2", len(params) == 2)
check("返回值标注为 dict[str, Any]",
      "dict" in str(sig.return_annotation))


# ── Test 2: 返回值结构（无 LLM）───────────────────────────

section("Test 2: 返回值结构")

r = supervisor("test")
expected_keys = {"output", "attempts", "final_score"}
check("包含 output 字段", "output" in r)
check("包含 attempts 字段", "attempts" in r)
check("包含 final_score 字段", "final_score" in r)
check("output 为字符串", isinstance(r["output"], str))
check("attempts 为整数", isinstance(r["attempts"], int))
check("final_score 为整数", isinstance(r["final_score"], int))


# ── Test 3: 边界情况 ──────────────────────────────────────

section("Test 3: 边界情况")

r_empty = supervisor("")
check("空字符串 -> attempts=0", r_empty["attempts"] == 0)
check("空字符串 -> output 非空", len(r_empty["output"]) > 0)

r_spaces = supervisor("   ")
check("纯空格 -> attempts=0", r_spaces["attempts"] == 0)

r_custom = supervisor("test", max_retries=5)
check("自定义 max_retries=5 不报错",
      isinstance(r_custom, dict))


# ── Test 4: 内部函数签名 ──────────────────────────────────

section("Test 4: 内部函数签名")

from patterns import supervisor as sv_mod

for fn_name in ("_call_worker", "_call_supervisor"):
    fn = getattr(sv_mod, fn_name, None)
    check(f"{fn_name} 存在且可调用",
          fn is not None and callable(fn))


# ── Test 5: 提示词完整性 ──────────────────────────────────

section("Test 5: 提示词完整性")

from patterns.supervisor import WORKER_SYSTEM_PROMPT, SUPERVISOR_SYSTEM_PROMPT

check("Worker 提示词非空", len(WORKER_SYSTEM_PROMPT) > 100)
check("Supervisor 提示词非空", len(SUPERVISOR_SYSTEM_PROMPT) > 100)
check("Worker 提示词含 JSON 输出要求", "JSON" in WORKER_SYSTEM_PROMPT)
check("Supervisor 提示词含准确性维度", "准确" in SUPERVISOR_SYSTEM_PROMPT)
check("Supervisor 提示词含深度维度", "深度" in SUPERVISOR_SYSTEM_PROMPT)
check("Supervisor 提示词含格式维度", "格式" in SUPERVISOR_SYSTEM_PROMPT)
check("Worker 提示词含 title/summary/analysis/conclusion",
      all(kw in WORKER_SYSTEM_PROMPT for kw in ["title", "summary", "analysis", "conclusion"]))


# ── Test 6: PASS_THRESHOLD ──────────────────────────────

section("Test 6: 通过阈值")

from patterns.supervisor import PASS_THRESHOLD

check("PASS_THRESHOLD = 21", PASS_THRESHOLD == 21)
check("PASS_THRESHOLD 在 18~27 之间（合理范围）",
      18 <= PASS_THRESHOLD <= 27)


# ── Test 7: CLI 入口 ──────────────────────────────────────

section("Test 7: CLI 入口")

import subprocess
result = subprocess.run(
    [sys.executable, "-m", "patterns.supervisor", "--help"],
    capture_output=True, text=True,
    cwd="D:\\Xuexi\\MultiAgentDesign\\ai-zhishiku-v3",
)
check("--help 返回代码 0", result.returncode == 0)
check("--help 包含用法说明",
      "usage:" in result.stdout.lower() or "usage:" in result.stderr.lower())

result2 = subprocess.run(
    [sys.executable, "-m", "patterns.supervisor", "测试任务", "--max-retries", "2"],
    capture_output=True, text=True,
    cwd="D:\\Xuexi\\MultiAgentDesign\\ai-zhishiku-v3",
)
check("CLI 调用 supervisor 不崩溃", result2.returncode == 0)
check("CLI 输出包含 supervisor 结果",
      "SUPERVISOR" in result2.stdout.upper())


# ── 汇总 ─────────────────────────────────────────────────

section(
    f"RESULTS: {results['pass']} passed, "
    f"{results['fail']} failed, "
    f"{results['skip']} skipped"
)
for d in results["details"]:
    print(d)

sys.exit(results["fail"])
