"""成本对比测试脚本"""
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "pipeline"))

env_file = project_root / "pipeline" / ".env"
from dotenv import load_dotenv

load_dotenv(env_file)

print("API Keys loaded:")
print(f"  DEEPSEEK: {'Yes' if os.getenv('DEEPSEEK_API_KEY') else 'No'}")
print(f"  MINIMAX: {'Yes' if os.getenv('MINIMAX_API_KEY') else 'No'}")

from model_client import chat_with_retry, tracker

test_cases = [
    {
        "name": "代码生成",
        "system": "你是一个专业的 Python 开发者。",
        "prompt": "请写一个 Python 函数，实现计算斐波那契数列的第 n 项，要求包含迭代和递归两种实现方式。"
    },
    {
        "name": "任务规划",
        "system": "你是一个 AI 项目规划专家。",
        "prompt": "请为一个 AI 知识库系统规划完整的搭建流程，包含数据采集、分析、存储、审核、分发等步骤。"
    },
    {
        "name": "文本摘要",
        "system": "你是一个专业的 AI 技术资讯分析师。",
        "prompt": "请为以下内容生成 50 字以内的中文摘要：LangChain 发布 v0.3 版本，重点改进了 Agent 编排能力，增加了多模态支持，性能提升 30%。"
    },
]

results = []

for test in test_cases:
    print(f"测试: {test['name']}")
    
    messages = [
        {"role": "system", "content": test["system"]},
        {"role": "user", "content": test["prompt"]},
    ]
    
    # DeepSeek
    tracker._records = {}
    try:
        r1 = chat_with_retry(messages, provider_name="deepseek")
        cost1 = tracker.estimated_cost("deepseek")
        print(f"  DeepSeek: {r1.usage.total_tokens} tokens (输入:{r1.usage.prompt_tokens}, 输出:{r1.usage.completion_tokens}) 成本: ¥{cost1:.6f}")
    except Exception as e:
        print(f"  DeepSeek 错误: {e}")
        cost1 = 0
        r1 = None
    
    # MiniMax
    tracker._records = {}
    try:
        r2 = chat_with_retry(messages, provider_name="minimax")
        cost2 = tracker.estimated_cost("minimax")
        print(f"  MiniMax: {r2.usage.total_tokens} tokens (输入:{r2.usage.prompt_tokens}, 输出:{r2.usage.completion_tokens}) 成本: ¥{cost2:.6f}")
    except Exception as e:
        print(f"  MiniMax 错误: {e}")
        cost2 = 0
        r2 = None
    
    results.append({
        "name": test["name"],
        "deepseek_tokens": r1.usage.total_tokens if r1 else 0,
        "deepseek_cost": cost1,
        "minimax_tokens": r2.usage.total_tokens if r2 else 0,
        "minimax_cost": cost2,
    })
    print()

print("=" * 50)
print("汇总:")
for r in results:
    print(f"{r['name']}: DeepSeek {r['deepseek_cost']:.6f} yuan vs MiniMax {r['minimax_cost']:.6f} yuan")