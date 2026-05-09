import requests
from typing import Dict, Optional

def get_repo_info(owner: str, repo: str, token: Optional[str] = None) -> Dict[str, Optional[str]]:
    """
    从 GitHub API 获取指定仓库的基本信息。

    Args:
        owner: 仓库所有者 (用户名或组织名)。
        repo: 仓库名称。
        token: 可选的 GitHub 个人访问令牌，用于提高 API 速率限制。

    Returns:
        包含 'stars', 'forks', 'description' 的字典。
        若请求失败，则返回包含错误信息的字典。
    """
    url = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # 对于 4xx/5xx 状态码抛出异常
        data = response.json()
        info = {
            "stars": data.get("stargazers_count"),
            "forks": data.get("forks_count"),
            "description": data.get("description"),
        }
        print(info)
        return info
    except requests.exceptions.HTTPError as e:
        # 处理 HTTP 错误（如 404 仓库不存在、403 速率限制等）
        return {"error": f"HTTP error: {e.response.status_code} - {e.response.reason}"}
    except requests.exceptions.RequestException as e:
        # 处理其他请求异常（如网络问题、超时等）
        return {"error": f"Request failed: {str(e)}"}
    except ValueError:
        # 处理 JSON 解析失败
        return {"error": "Failed to parse JSON response."}