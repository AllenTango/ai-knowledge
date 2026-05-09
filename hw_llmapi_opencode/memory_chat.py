from config import deepseek_url, deepseek_api_key
from openai import OpenAI

# 初始化客户端
client = OpenAI(
    api_key=deepseek_api_key, 
    base_url=deepseek_url
)

# 初始化对话历史列表
conversation_history = [
    {"role": "system", "content": "你是一个资深的 Python 编程助手，回答要简洁且包含代码示例。"}
]
# 简单的上下文截断示例（保留最近 20 条消息）
MAX_HISTORY = 20

print("🤖 AI 助手已就绪 (输入 'q' 结束对话)...")

while True:
    # 3. 获取用户输入
    user_input = input("\n👤 你: ")
    
    # 检查退出指令
    if user_input.lower() == 'q':
        print("👋 再见！")
        break
    
    if not user_input.strip():
        continue

    # 将用户的新输入加入历史记录
    conversation_history.append({"role": "user", "content": user_input})

    try:
        # 发送请求（带上完整的历史记录）
        stream = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=conversation_history,
            temperature=0.7,
            stream=True  # 开启流式响应，避免完整响应过长时会话长时间空白
        )

        print("🤖 AI 分析结果：")
        result = ""
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                content = chunk.choices[0].delta.content
                print(content, end="", flush=True) # 逐字打印
                result += content
        print()

        # 【关键步骤】将 AI 的回复也加入历史记录
        # 如果不加这一步，AI 下一轮就会忘记自己刚才说了什么
        if len(conversation_history) > MAX_HISTORY:
            # 保留第0条（System提示词）和最后 MAX_HISTORY-1 条
            conversation_history = [conversation_history[0]] + conversation_history[-(MAX_HISTORY-1):]
        else:
            conversation_history.append({"role": "assistant", "content": result})

    except Exception as e:
        print(f"❌ 发生错误: {e}")
        # 出错时，建议把刚才用户发的消息移除，避免污染历史
        conversation_history.pop() 