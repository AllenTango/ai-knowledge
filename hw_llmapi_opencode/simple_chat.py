from config import deepseek_url, deepseek_api_key
from openai import OpenAI

# 初始化客户端
client = OpenAI(
    api_key=deepseek_api_key, 
    base_url=deepseek_url
)

print("🤖 AI 助手已就绪 (输入 'q' 结束对话)...")
while True:
    prompt = input("\n👤 你: ")
    if prompt.lower() == "q":
        print("👋 再见！")
        break
    if not prompt.strip():
        continue
    # 发起请求
    try:
        response = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[
                {"role": "system", "content": "你是一个资深的 Python 编程助手，回答要简洁且包含代码示例。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2  # 代码分析需要严谨，temperature 设低一点
        )

        # 5. 获取并打印结果
        result = response.choices[0].message.content
        print("🤖 AI 分析结果：")
        print("-" * 30)
        print(result)

    except Exception as e:
        print(f"请求发生错误: {e}")