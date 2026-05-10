"""router.py 综合测试脚本。"""
import sys
import inspect

sys.path.insert(0, "D:\\Xuexi\\MultiAgentDesign\\ai-zhishiku-v3")
from patterns.router import (
    classify_by_keywords, classify_by_llm,
    handle_github_search, handle_knowledge_query,
    route, KEYWORD_MAP, HANDLER_MAP,
)

results = {"pass": 0, "fail": 0, "details": []}


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


def section(title):
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


# ── Test 1: 第一层关键词匹配 ────────────────────────────────────

section("Test 1: classify_by_keywords (第一层关键词匹配)")

check("github项目 -> github_search",
      classify_by_keywords("github项目") == "github_search")
check("开源仓库 -> github_search",
      classify_by_keywords("开源仓库") == "github_search")
check("RAG repo -> github_search",
      classify_by_keywords("RAG repo") == "github_search")
check("repository -> github_search",
      classify_by_keywords("repository") == "github_search")
check("trending项目 -> github_search",
      classify_by_keywords("trending项目") == "github_search")
check("git仓库 -> github_search",
      classify_by_keywords("git仓库") == "github_search")

check("搜索文章 -> knowledge_query",
      classify_by_keywords("搜索文章") == "knowledge_query")
check("查找知识库 -> knowledge_query",
      classify_by_keywords("查找知识库") == "knowledge_query")
check("AI相关文章 -> knowledge_query",
      classify_by_keywords("AI相关文章") == "knowledge_query")
check("检索RAG -> knowledge_query",
      classify_by_keywords("检索RAG") == "knowledge_query")
check("查一下LangChain -> knowledge_query",
      classify_by_keywords("查一下LangChain") == "knowledge_query")
check("find article -> knowledge_query",
      classify_by_keywords("find article") == "knowledge_query")
check("query数据 -> knowledge_query",
      classify_by_keywords("query数据") == "knowledge_query")

check("今天天气 -> None (fallthrough)",
      classify_by_keywords("今天天气") is None)
check("你好 -> None (fallthrough)",
      classify_by_keywords("你好") is None)
check("什么是Agent -> None (fallthrough)",
      classify_by_keywords("什么是Agent") is None)
check("空字符串 -> None",
      classify_by_keywords("") is None)

check("大小写不敏感: GITHUB项目 -> github_search",
      classify_by_keywords("GITHUB项目") == "github_search")
check("大小写不敏感: Search知识 -> knowledge_query",
      classify_by_keywords("Search知识") == "knowledge_query")


# ── Test 2: KEYWORD_MAP 结构 ─────────────────────────────────

section("Test 2: KEYWORD_MAP 数据结构验证")

check("KEYWORD_MAP 有 2 种意图", len(KEYWORD_MAP) == 2)
check("github_search 有 8 个关键词",
      len(KEYWORD_MAP["github_search"]) == 8,
      str(KEYWORD_MAP["github_search"]))
check("knowledge_query 有 10 个关键词",
      len(KEYWORD_MAP["knowledge_query"]) == 10,
      str(KEYWORD_MAP["knowledge_query"]))

all_lower = all(
    kw.islower() or not kw.isascii()
    for kw_list in KEYWORD_MAP.values()
    for kw in kw_list
)
check("纯英文关键词均为小写", all_lower)

all_no_dupes = all(
    len(set(kw_list)) == len(kw_list)
    for kw_list in KEYWORD_MAP.values()
)
check("无重复关键词", all_no_dupes)


# ── Test 3: HANDLER_MAP 结构 ─────────────────────────────────

section("Test 3: HANDLER_MAP 处理器映射验证")

check("HANDLER_MAP 有 3 种意图", len(HANDLER_MAP) == 3)
check("github_search 处理器可调用",
      callable(HANDLER_MAP["github_search"]))
check("knowledge_query 处理器可调用",
      callable(HANDLER_MAP["knowledge_query"]))
check("general_chat 处理器可调用",
      callable(HANDLER_MAP["general_chat"]))

check("github_search -> handle_github_search",
      HANDLER_MAP["github_search"].__name__ == "handle_github_search")
check("knowledge_query -> handle_knowledge_query",
      HANDLER_MAP["knowledge_query"].__name__ == "handle_knowledge_query")
check("general_chat -> handle_general_chat",
      HANDLER_MAP["general_chat"].__name__ == "handle_general_chat")

for name, handler in HANDLER_MAP.items():
    hsig = inspect.signature(handler)
    check(f"{name} 签名 {hsig} 为单参数",
          len(hsig.parameters) == 1)


# ── Test 4: handle_github_search (真实API) ──────────────────

section("Test 4: handle_github_search (GitHub Search API)")

try:
    r = handle_github_search("langchain")
    check("API 请求成功 -> 返回搜索结果",
          r.startswith("找到"), f"返回 {len(r)} 字符")
    # 输出前 300 字符
    print(f"  结果预览 ({len(r)} chars):")
    for line in r.splitlines()[:8]:
        print(f"    {line}")
except Exception as e:
    check("API 请求", False, str(e)[:80])


try:
    r2 = handle_github_search("machine learning agent framework")
    check("多词英文搜索",
          r2.startswith("找到"), f"返回 {len(r2)} 字符")
except Exception as e:
    check("多词英文搜索", False, str(e)[:80])


# ── Test 5: handle_knowledge_query ───────────────────────────

section("Test 5: handle_knowledge_query (本地知识库检索)")

r1 = handle_knowledge_query("langchain")
check("index.json 为空时返回友好提示",
      "空" in r1 or "不存在" in r1)
print(f"  输出: {r1[:80]}")


# ── Test 6: classify_by_llm 兜底 ────────────────────────────

section("Test 6: classify_by_llm (LLM 分类兜底)")

r = classify_by_llm("今天有什么新闻")
check("LLM 不可用时默认 general_chat", r == "general_chat")

r2 = classify_by_llm("帮我查一下Python项目")
check("LLM 不可用时 general_chat (含关键词也LLM走)", r2 == "general_chat")


# ── Test 7: 统一入口 route() ────────────────────────────────

section("Test 7: route() 统一入口")

r1 = route("github项目")
check("github项目 -> 返回字符串", isinstance(r1, str) and len(r1) > 0)

r2 = route("知识检索")
check("知识检索 -> 返回字符串", isinstance(r2, str) and len(r2) > 0)

r3 = route("")
check("空字符串 -> 友好提示", "有效" in r3 or len(r3) > 0,
      repr(r3))

r4 = route("   ")
check("纯空格 -> 友好提示", "有效" in r4 or len(r4) > 0,
      repr(r4))

sig = inspect.signature(route)
check("route(query) 单参数签名", len(sig.parameters) == 1, str(sig))


# ── 汇总 ─────────────────────────────────────────────────────

section(f"RESULTS: {results['pass']} passed, {results['fail']} failed")

for d in results["details"]:
    print(d)

sys.exit(results["fail"])
