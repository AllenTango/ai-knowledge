"""GitHub API 工具模块。

提供从 GitHub API 获取仓库基本信息的函数。
"""

import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_GITHUB_API_BASE = "https://api.github.com"


def get_repo_info(
    repo_full_name: str,
    token: Optional[str] = None,
) -> dict[str, str | int]:
    """从 GitHub API 获取指定仓库的基本信息。

    Args:
        repo_full_name: 仓库全名，格式为 "owner/repo"，例如 "langchain-ai/langchain"。
        token: GitHub 个人访问令牌。若未提供，则尝试从环境变量 GITHUB_TOKEN 读取。
            未认证请求有更低的频率限制（60 次/小时）。

    Returns:
        包含仓库基本信息的字典：
        - full_name: 仓库全名
        - description: 仓库描述
        - stars: Star 数量
        - forks: Fork 数量
        - url: 仓库 HTML 地址

    Raises:
        ValueError: repo_full_name 格式无效或仓库不存在。
        requests.RequestException: 网络请求失败。
    """
    token = token or os.getenv("GITHUB_TOKEN")

    if not isinstance(repo_full_name, str) or "/" not in repo_full_name:
        raise ValueError(f"无效的仓库全名格式：{repo_full_name}，期望格式为 owner/repo")

    url = f"{_GITHUB_API_BASE}/repos/{repo_full_name}"

    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    logger.info("正在获取仓库信息：%s", repo_full_name)

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.HTTPError as e:
        if response.status_code == 404:
            raise ValueError(f"仓库不存在：{repo_full_name}") from e
        if response.status_code == 403:
            raise ValueError(
                f"频率限制或权限不足（403），请提供有效的 GitHub Token"
            ) from e
        raise
    except requests.RequestException:
        logger.exception("获取仓库信息失败：%s", repo_full_name)
        raise

    data = response.json()

    result = {
        "full_name": data.get("full_name", repo_full_name),
        "description": data.get("description") or "",
        "stars": data.get("stargazers_count", 0),
        "forks": data.get("forks_count", 0),
        "url": data.get("html_url", f"https://github.com/{repo_full_name}"),
    }

    logger.info(
        "仓库信息获取成功：%s (Stars: %s, Forks: %s)",
        result["full_name"],
        result["stars"],
        result["forks"],
    )

    return result
