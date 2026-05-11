"""知识库交互模块。

整合搜索引擎、订阅管理和权限控制，提供统一的消息处理入口。

Usage:
    from bot.knowledge_bot import KnowledgeBot

    bot = KnowledgeBot()
    response = bot.handle_message(user_id="user123", text="/search langgraph")
"""

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_ARTICLES = PROJECT_ROOT / "knowledge" / "articles"
BOT_DATA_DIR = PROJECT_ROOT / "bot" / "bot_data"


class Intent(Enum):
    """意图枚举。"""

    SEARCH = "search"
    TODAY = "today"
    TOP = "top"
    SUBSCRIBE = "subscribe"
    HELP = "help"
    UNKNOWN = "unknown"


class Permission(IntEnum):
    """权限等级枚举。"""

    READ = 1
    WRITE = 2
    DELETE = 3


@dataclass
class BotResponse:
    """Bot 回复结构体。

    Attributes:
        success: 请求是否处理成功。
        reply: 格式化回复文本。
        data: 附加数据（如文章列表）。
    """

    success: bool
    reply: str
    data: list[dict[str, Any]] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════
# KnowledgeSearchEngine
# ══════════════════════════════════════════════════════════════════════


class KnowledgeSearchEngine:
    """知识库搜索引擎。

    支持按关键词、标签、日期范围过滤文章，按评分或日期排序，支持分页。

    Attributes:
        data_dir: 文章存储目录。
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        """初始化搜索引擎。

        Args:
            data_dir: 文章 JSON 存储目录，默认 knowledge/articles/。
        """
        self.data_dir = data_dir or KNOWLEDGE_ARTICLES
        self._articles_cache: list[dict[str, Any]] = []
        self._cache_loaded = False

    def _load_articles(self) -> list[dict[str, Any]]:
        """加载所有文章到内存缓存。"""
        if self._cache_loaded:
            return self._articles_cache

        self._articles_cache = []
        if not self.data_dir.exists():
            logger.warning(f"文章目录不存在: {self.data_dir}")
            return self._articles_cache

        for json_file in sorted(self.data_dir.glob("*.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    article = json.load(f)
                    self._articles_cache.append(article)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"无法读取文章文件 {json_file.name}: {e}")
                continue

        self._cache_loaded = True
        logger.info(f"加载了 {len(self._articles_cache)} 篇文章")
        return self._articles_cache

    def refresh_cache(self) -> None:
        """刷新文章缓存。"""
        self._cache_loaded = False
        self._articles_cache = []
        self._load_articles()

    @staticmethod
    def _parse_datetime(date_str: str | None) -> datetime | None:
        """解析 ISO 8601 时间字符串，统一返回 UTC-aware datetime。

        Args:
            date_str: ISO 8601 格式字符串或日期简写 "YYYY-MM-DD"。

        Returns:
            解析后的 UTC-aware datetime 对象，解析失败返回 None。
        """
        if not date_str:
            return None
        try:
            dt = datetime.fromisoformat(date_str)
        except (ValueError, TypeError):
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                logger.warning(f"无法解析日期: {date_str}")
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def _get_article_date(self, article: dict[str, Any]) -> datetime | None:
        """从文章中提取可用的日期字段。

        Args:
            article: 文章字典。

        Returns:
            解析后的 datetime 或 None。
        """
        for date_field in ("fetched_at", "analyzed_at"):
            value = article.get(date_field)
            if value:
                parsed = self._parse_datetime(value)
                if parsed:
                    return parsed
        return None

    def search(
        self,
        keyword: str | None = None,
        tags: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sort_by: str = "score",
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """搜索知识库文章。

        Args:
            keyword: 搜索关键词（匹配标题、摘要、标签）。
            tags: 标签过滤列表（文章需包含全部标签）。
            date_from: 起始日期（ISO 8601 或 YYYY-MM-DD）。
            date_to: 结束日期（ISO 8601 或 YYYY-MM-DD）。
            sort_by: 排序方式，可选 "score" | "date"，默认 "score"。
            limit: 返回数量上限，默认 10。
            offset: 分页偏移，默认 0。

        Returns:
            匹配的文章列表，每项包含 id, title, source, summary, score, tags, fetched_at。
        """
        articles = self._load_articles()

        keyword_lower = keyword.lower().strip() if keyword else ""
        tags_set = set(t.strip().lower() for t in tags) if tags else set()
        dt_from = self._parse_datetime(date_from) if date_from else None
        dt_to = self._parse_datetime(date_to) if date_to else None

        matches = []
        for article in articles:
            if keyword_lower:
                title = article.get("title", "").lower()
                summary = article.get("summary", "").lower()
                article_tags = " ".join(article.get("tags", [])).lower()
                if (
                    keyword_lower not in title
                    and keyword_lower not in summary
                    and keyword_lower not in article_tags
                ):
                    continue

            if tags_set:
                article_tags_lower = {t.lower() for t in article.get("tags", [])}
                if not tags_set.issubset(article_tags_lower):
                    continue

            if dt_from or dt_to:
                article_date = self._get_article_date(article)
                if article_date is None:
                    continue
                if dt_from and article_date < dt_from:
                    continue
                if dt_to and article_date > dt_to:
                    continue

            matches.append({
                "id": article.get("id", ""),
                "title": article.get("title", ""),
                "source": article.get("source", ""),
                "source_url": article.get("source_url", ""),
                "summary": article.get("summary", "")[:300],
                "score": article.get("score", 0),
                "tags": article.get("tags", []),
                "fetched_at": article.get("fetched_at", ""),
                "status": article.get("status", ""),
            })

        if sort_by == "date":
            matches.sort(
                key=lambda a: a.get("fetched_at", ""),
                reverse=True,
            )
        else:
            matches.sort(key=lambda a: a.get("score", 0), reverse=True)

        total = len(matches)
        paginated = matches[offset : offset + limit]
        logger.info(
            f"搜索完成: keyword={keyword or '<无>'}, tags={tags or '<无>'}, "
            f"匹配={total}, 返回={len(paginated)}"
        )
        return paginated

    def get_today(self, limit: int = 20) -> list[dict[str, Any]]:
        """获取今日入库的文章。

        Args:
            limit: 返回数量上限，默认 20。

        Returns:
            今日入库的文章列表。
        """
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.search(date_from=today_str, sort_by="score", limit=limit)

    def get_top(self, top_n: int = 10, date_from: str | None = None) -> list[dict[str, Any]]:
        """获取评分最高的文章。

        Args:
            top_n: 返回数量上限，默认 10。
            date_from: 可选，只返回该日期之后的文章。

        Returns:
            评分最高的文章列表。
        """
        return self.search(sort_by="score", limit=top_n, date_from=date_from)

    def get_stats(self) -> dict[str, Any]:
        """获取知识库统计信息。

        Returns:
            文章总数、来源分布、热门标签、评分分布。
        """
        articles = self._load_articles()

        source_counts = Counter(a.get("source", "unknown") for a in articles)
        all_tags = []
        all_scores = []
        for a in articles:
            all_tags.extend(a.get("tags", []))
            score = a.get("score")
            if score is not None:
                all_scores.append(score)
        tag_counts = Counter(all_tags)

        return {
            "total_articles": len(articles),
            "source_distribution": dict(source_counts),
            "top_tags": [{"tag": tag, "count": count} for tag, count in tag_counts.most_common(10)],
            "avg_score": round(sum(all_scores) / len(all_scores), 2) if all_scores else 0,
            "max_score": max(all_scores) if all_scores else 0,
        }


# ══════════════════════════════════════════════════════════════════════
# SubscriptionManager
# ══════════════════════════════════════════════════════════════════════


class SubscriptionManager:
    """用户订阅管理器。

    支持用户按关键词/标签订阅知识更新，数据持久化到 JSON 文件。

    Attributes:
        storage_file: 订阅数据文件路径。
    """

    def __init__(self, storage_file: Path | None = None) -> None:
        """初始化订阅管理器。

        Args:
            storage_file: 订阅数据存储文件路径，默认 bot/bot_data/subscriptions.json。
        """
        self.storage_file = storage_file or BOT_DATA_DIR / "subscriptions.json"
        self._subscriptions: dict[str, set[str]] = {}
        self._load()

    def _ensure_storage_dir(self) -> None:
        """确保存储目录存在。"""
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        """从文件加载订阅数据。"""
        if not self.storage_file.exists():
            self._subscriptions = {}
            return
        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
                self._subscriptions = {
                    user_id: set(keywords) for user_id, keywords in raw.items()
                }
            logger.info(f"加载了 {len(self._subscriptions)} 位用户的订阅数据")
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"加载订阅数据失败: {e}")
            self._subscriptions = {}

    def _save(self) -> None:
        """保存订阅数据到文件。"""
        self._ensure_storage_dir()
        serializable = {
            user_id: sorted(keywords) for user_id, keywords in self._subscriptions.items()
        }
        try:
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(serializable, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"保存订阅数据失败: {e}")

    def subscribe(self, user_id: str, keyword: str) -> bool:
        """为用户添加订阅关键词。

        Args:
            user_id: 用户标识。
            keyword: 订阅关键词。

        Returns:
            True 表示新增，False 表示已存在。
        """
        keyword = keyword.strip().lower()
        if not keyword:
            return False
        if user_id not in self._subscriptions:
            self._subscriptions[user_id] = set()
        if keyword in self._subscriptions[user_id]:
            return False
        self._subscriptions[user_id].add(keyword)
        self._save()
        logger.info(f"用户 {user_id} 订阅了: {keyword}")
        return True

    def unsubscribe(self, user_id: str, keyword: str) -> bool:
        """取消用户的订阅关键词。

        Args:
            user_id: 用户标识。
            keyword: 要取消的关键词。

        Returns:
            True 表示成功取消，False 表示未找到。
        """
        keyword = keyword.strip().lower()
        if user_id not in self._subscriptions:
            return False
        if keyword not in self._subscriptions[user_id]:
            return False
        self._subscriptions[user_id].discard(keyword)
        if not self._subscriptions[user_id]:
            del self._subscriptions[user_id]
        self._save()
        logger.info(f"用户 {user_id} 取消订阅: {keyword}")
        return True

    def get_subscriptions(self, user_id: str) -> list[str]:
        """获取用户所有订阅关键词。

        Args:
            user_id: 用户标识。

        Returns:
            已排序的订阅关键词列表。
        """
        return sorted(self._subscriptions.get(user_id, set()))

    def get_all_subscribers(self) -> list[str]:
        """获取所有已订阅的用户 ID 列表。

        Returns:
            用户 ID 列表。
        """
        return list(self._subscriptions.keys())


# ══════════════════════════════════════════════════════════════════════
# PermissionManager
# ══════════════════════════════════════════════════════════════════════


class PermissionManager:
    """权限管理器。

    三级权限：READ（1，默认）、WRITE（2）、DELETE（3）。高权限自动继承低权限。

    Attributes:
        storage_file: 权限数据文件路径。
    """

    def __init__(self, storage_file: Path | None = None) -> None:
        """初始化权限管理器。

        Args:
            storage_file: 权限数据存储文件路径，默认 bot/bot_data/permissions.json。
        """
        self.storage_file = storage_file or BOT_DATA_DIR / "permissions.json"
        self._permissions: dict[str, int] = {}
        self._load()

    def _ensure_storage_dir(self) -> None:
        """确保存储目录存在。"""
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        """从文件加载权限数据。"""
        if not self.storage_file.exists():
            self._permissions = {}
            return
        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                self._permissions = json.load(f)
            logger.info(f"加载了 {len(self._permissions)} 位用户的权限数据")
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"加载权限数据失败: {e}")
            self._permissions = {}

    def _save(self) -> None:
        """保存权限数据到文件。"""
        self._ensure_storage_dir()
        try:
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(self._permissions, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"保存权限数据失败: {e}")

    def check(self, user_id: str, required: Permission) -> bool:
        """检查用户是否具备所需权限等级。

        Args:
            user_id: 用户标识。
            required: 所需的最小权限等级。

        Returns:
            True 表示权限足够。
        """
        if required == Permission.READ:
            return True
        user_level = self._permissions.get(user_id, Permission.READ.value)
        return user_level >= required.value

    def grant(self, user_id: str, permission: Permission) -> None:
        """授予用户指定权限等级。

        Args:
            user_id: 用户标识。
            permission: 要授予的权限等级。
        """
        self._permissions[user_id] = permission.value
        self._save()
        logger.info(f"授予用户 {user_id} 权限: {permission.name} (level={permission.value})")

    def revoke(self, user_id: str) -> None:
        """回收用户所有自定义权限，恢复默认 READ。

        Args:
            user_id: 用户标识。
        """
        if user_id in self._permissions:
            del self._permissions[user_id]
            self._save()
            logger.info(f"回收用户 {user_id} 权限，已恢复默认 READ")

    def get_level(self, user_id: str) -> Permission:
        """获取用户当前权限等级。

        Args:
            user_id: 用户标识。

        Returns:
            用户当前权限等级，默认为 READ。
        """
        level = self._permissions.get(user_id, Permission.READ.value)
        return Permission(level)


# ══════════════════════════════════════════════════════════════════════
# 意图识别
# ══════════════════════════════════════════════════════════════════════

COMMAND_PATTERNS: list[tuple[str, Intent]] = [
    ("/search", Intent.SEARCH),
    ("/s", Intent.SEARCH),
    ("/today", Intent.TODAY),
    ("/td", Intent.TODAY),
    ("/日报", Intent.TODAY),
    ("/top", Intent.TOP),
    ("/tp", Intent.TOP),
    ("/subscribe", Intent.SUBSCRIBE),
    ("/sub", Intent.SUBSCRIBE),
    ("/help", Intent.HELP),
    ("/h", Intent.HELP),
    ("/?", Intent.HELP),
]
# 按前缀长度降序排列，确保长前缀优先匹配（如 /subscribe 优先于 /sub）
COMMAND_PATTERNS.sort(key=lambda x: len(x[0]), reverse=True)

NATURAL_KEYWORDS: list[tuple[list[str], Intent]] = [
    (["搜索", "查询", "查一下", "找一下", "搜"], Intent.SEARCH),
    (["今天", "今日", "简报", "日报", "今日简报", "今日动态", "digest"], Intent.TODAY),
    (["热门", "排行", "高分", "top", "最高分"], Intent.TOP),
    (["订阅", "subscribe", "关注", "追踪"], Intent.SUBSCRIBE),
    (["帮助", "help", "怎么用", "功能"], Intent.HELP),
]


def recognize_intent(text: str) -> tuple[Intent, str]:
    """识别用户消息的意图。

    优先匹配命令前缀（如 /search），再匹配自然语言关键词。

    Args:
        text: 用户输入文本。

    Returns:
        (Intent 枚举, 参数字符串) 元组。UNKNOWN 时参数为原始文本。
    """
    text_stripped = text.strip()
    if not text_stripped:
        return Intent.UNKNOWN, ""

    # 1) 命令前缀匹配（长前缀优先，且要求边界为空格或结尾）
    for prefix, intent in COMMAND_PATTERNS:
        if text_stripped.startswith(prefix):
            rest = text_stripped[len(prefix):]
            if rest == "" or rest.startswith((" ", "\n", "\t")):
                return intent, rest.strip()

    # 2) 自然语言关键词匹配
    text_lower = text_stripped.lower()

    best_match: tuple[int, Intent, str] = (0, Intent.UNKNOWN, text_stripped)

    for keywords, intent in NATURAL_KEYWORDS:
        for kw in keywords:
            if kw in text_lower:
                kw_len = len(kw)
                if kw_len > best_match[0]:
                    idx = text_lower.find(kw)
                    param = text_stripped[:idx].strip() + " " + text_stripped[idx + kw_len:].strip()
                    param = param.strip()
                    if param == text_stripped:
                        param = ""
                    best_match = (kw_len, intent, param)

    _, final_intent, final_param = best_match
    return final_intent, final_param


# ══════════════════════════════════════════════════════════════════════
# KnowledgeBot
# ══════════════════════════════════════════════════════════════════════


class KnowledgeBot:
    """知识库 Bot 主入口。

    整合搜索引擎、订阅管理和权限控制，提供统一消息处理接口。

    Usage:
        bot = KnowledgeBot()
        response = bot.handle_message(user_id="user123", text="/search langgraph")
        print(response.reply)

    Attributes:
        engine: 搜索引擎实例。
        subscriptions: 订阅管理器实例。
        permissions: 权限管理器实例。
        max_search_results: 搜索最大返回条数。
    """

    def __init__(
        self,
        engine: KnowledgeSearchEngine | None = None,
        subscriptions: SubscriptionManager | None = None,
        permissions: PermissionManager | None = None,
        max_search_results: int = 10,
    ) -> None:
        """初始化 KnowledgeBot。

        Args:
            engine: 搜索引擎实例，默认新建。
            subscriptions: 订阅管理器实例，默认新建。
            permissions: 权限管理器实例，默认新建。
            max_search_results: 搜索最大返回条数，默认 10。
        """
        self.engine = engine or KnowledgeSearchEngine()
        self.subscriptions = subscriptions or SubscriptionManager()
        self.permissions = permissions or PermissionManager()
        self.max_search_results = max_search_results

    def handle_message(self, user_id: str, text: str) -> BotResponse:
        """处理用户消息的统一入口。

        Args:
            user_id: 用户标识。
            text: 用户消息文本。

        Returns:
            BotResponse 回复体。
        """
        intent, param = recognize_intent(text)

        logger.info(
            f"收到消息: user={user_id}, intent={intent.value}, param={param!r}"
        )

        handlers = {
            Intent.SEARCH: self._handle_search,
            Intent.TODAY: self._handle_today,
            Intent.TOP: self._handle_top,
            Intent.SUBSCRIBE: self._handle_subscribe,
            Intent.HELP: self._handle_help,
        }

        handler = handlers.get(intent)
        if handler:
            try:
                return handler(param, user_id)
            except Exception as e:
                logger.error(f"处理消息异常: {e}", exc_info=True)
                return BotResponse(
                    success=False,
                    reply=f"[错误] 处理请求时发生异常，请稍后重试。\n\n详情: {e}",
                )

        return BotResponse(
            success=False,
            reply=(
                "抱歉，无法识别您的意图。\n\n"
                "试试这些命令：\n"
                "/search <关键词> — 搜索知识库\n"
                "/today — 今日入库文章\n"
                "/top — 高分文章排行\n"
                "/subscribe <关键词> — 订阅关键词\n"
                "/help — 查看帮助"
            ),
        )

    def _handle_search(self, query: str, user_id: str) -> BotResponse:
        """处理搜索请求。

        Args:
            query: 搜索关键词。
            user_id: 用户标识。

        Returns:
            BotResponse 回复体。
        """
        if not query:
            return BotResponse(
                success=False,
                reply="请提供搜索关键词。用法：/search <关键词>",
            )

        if not self.permissions.check(user_id, Permission.READ):
            return BotResponse(
                success=False,
                reply="[权限不足] 您没有读取知识库的权限。",
            )

        results = self.engine.search(
            keyword=query,
            limit=self.max_search_results,
            sort_by="score",
        )

        if not results:
            return BotResponse(
                success=True,
                reply=f"未找到与「{query}」相关的文章。",
            )

        reply_lines = [f"搜索「{query}」的结果 (共 {len(results)} 条)：\n"]
        for i, article in enumerate(results, 1):
            title = article.get("title", "无标题")
            score = article.get("score", 0)
            source = article.get("source", "")
            summary = article.get("summary", "")[:150]
            reply_lines.append(
                f"{i}. [{score:.1f}] {title} (来源: {source})\n"
                f"   {summary}\n"
            )

        return BotResponse(success=True, reply="\n".join(reply_lines), data=results)

    def _handle_today(self, _param: str, user_id: str) -> BotResponse:
        """处理今日简报请求。

        Args:
            _param: 未使用。
            user_id: 用户标识。

        Returns:
            BotResponse 回复体。
        """
        if not self.permissions.check(user_id, Permission.READ):
            return BotResponse(
                success=False,
                reply="[权限不足] 您没有读取知识库的权限。",
            )

        results = self.engine.get_today(limit=self.max_search_results)

        if not results:
            return BotResponse(
                success=True,
                reply="今日暂无新入库文章。",
            )

        today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        reply_lines = [f"今日知识简报 ({today_date})，共 {len(results)} 条：\n"]

        for i, article in enumerate(results, 1):
            title = article.get("title", "无标题")
            score = article.get("score", 0)
            source = article.get("source", "")
            tags = " / ".join(article.get("tags", [])[:5])
            summary = article.get("summary", "")[:120]
            reply_lines.append(
                f"{i}. [{score:.1f}] {title}\n"
                f"   标签: {tags}\n"
                f"   来源: {source} | {summary}\n"
            )

        stats = self.engine.get_stats()
        reply_lines.append(
            f"──\n"
            f"知识库总量: {stats['total_articles']} 篇 | "
            f"平均分: {stats['avg_score']}"
        )

        return BotResponse(success=True, reply="\n".join(reply_lines), data=results)

    def _handle_top(self, param: str, user_id: str) -> BotResponse:
        """处理高分排行请求。

        Args:
            param: 可选的数量参数，如 "/top 5"。
            user_id: 用户标识。

        Returns:
            BotResponse 回复体。
        """
        if not self.permissions.check(user_id, Permission.READ):
            return BotResponse(
                success=False,
                reply="[权限不足] 您没有读取知识库的权限。",
            )

        try:
            top_n = int(param) if param.strip() else 10
        except ValueError:
            top_n = 10
        top_n = min(max(top_n, 1), 20)

        results = self.engine.get_top(top_n=top_n)

        if not results:
            return BotResponse(success=True, reply="知识库暂无内容。")

        reply_lines = [f"高分文章 Top {top_n}：\n"]
        for i, article in enumerate(results, 1):
            title = article.get("title", "无标题")
            score = article.get("score", 0)
            summary = article.get("summary", "")[:120]
            reply_lines.append(
                f"{i}. [{score:.1f}] {title}\n"
                f"   {summary}\n"
            )

        return BotResponse(success=True, reply="\n".join(reply_lines), data=results)

    def _handle_subscribe(self, param: str, user_id: str) -> BotResponse:
        """处理订阅管理请求。

        支持四种操作：
          - /subscribe <关键词> → 新增订阅
          - /subscribe list → 列出当前订阅
          - /subscribe del <关键词> → 取消订阅
          - /subscribe → 显示用法

        Args:
            param: 订阅操作参数。
            user_id: 用户标识。

        Returns:
            BotResponse 回复体。
        """
        if not self.permissions.check(user_id, Permission.WRITE):
            return BotResponse(
                success=False,
                reply="[权限不足] 订阅管理需要 WRITE 权限，您当前仅拥有 READ 权限。",
            )

        param = param.strip()

        if not param:
            current = self.subscriptions.get_subscriptions(user_id)
            if current:
                tags = "\n".join(f"  - {kw}" for kw in current)
                reply = f"您的订阅列表：\n{tags}\n\n用法：\n  /subscribe <关键词> — 新增订阅\n  /subscribe list — 查看列表\n  /subscribe del <关键词> — 取消订阅"
            else:
                reply = "您当前没有订阅。\n\n用法：\n  /subscribe <关键词> — 新增订阅\n  /subscribe list — 查看列表\n  /subscribe del <关键词> — 取消订阅"
            return BotResponse(success=True, reply=reply)

        if param.lower() == "list":
            current = self.subscriptions.get_subscriptions(user_id)
            if current:
                reply = "您的订阅列表：\n" + "\n".join(f"  {i}. {kw}" for i, kw in enumerate(current, 1))
            else:
                reply = "您当前没有订阅。"
            return BotResponse(success=True, reply=reply)

        if param.lower().startswith("del ") or param.lower().startswith("rm "):
            keyword = param.split(maxsplit=1)[1].strip()
            if not keyword:
                return BotResponse(success=False, reply="请指定要取消的关键词。用法：/subscribe del <关键词>")
            ok = self.subscriptions.unsubscribe(user_id, keyword)
            if ok:
                return BotResponse(success=True, reply=f"已取消订阅「{keyword}」。")
            else:
                return BotResponse(success=False, reply=f"未找到订阅「{keyword}」。")

        ok = self.subscriptions.subscribe(user_id, param)
        if ok:
            return BotResponse(success=True, reply=f"已订阅「{param}」。当有新内容匹配时将通知您。")
        else:
            return BotResponse(success=True, reply=f"您已订阅过「{param}」，无需重复订阅。")

    def _handle_help(self, _param: str, user_id: str) -> BotResponse:
        """处理帮助请求。

        Args:
            _param: 未使用。
            user_id: 用户标识（用于显示当前权限等级）。

        Returns:
            BotResponse 回复体。
        """
        perm_level = self.permissions.get_level(user_id).name
        reply = (
            "AI 知识库助手 使用帮助\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "搜索知识库：\n"
            "  /search <关键词> — 搜索相关文章\n\n"
            "浏览内容：\n"
            "  /today — 今日入库文章\n"
            "  /top [数量] — 高分排行，如 /top 5\n\n"
            "订阅管理（需 WRITE 权限）：\n"
            "  /subscribe <关键词> — 订阅关键词\n"
            "  /subscribe list — 查看订阅\n"
            "  /subscribe del <关键词> — 取消订阅\n\n"
            "其他：\n"
            "  /help — 查看帮助\n\n"
            f"您的权限等级：{perm_level}"
        )
        return BotResponse(success=True, reply=reply)
