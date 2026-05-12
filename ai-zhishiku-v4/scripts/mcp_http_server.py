"""MCP 知识库 HTTP API 服务器。

将原 stdio 协议的 MCP 知识库工具封装为 RESTful HTTP API，
支持 Docker 容器化部署，通过标准 HTTP 端口对外提供服务。
同时托管看板静态文件。

API 端点:
    GET  /                    - 重定向到公开看板
    GET  /static/*            - 静态文件（看板 HTML/CSS/JS）
    GET  /health              - 健康检查
    GET  /mcp/stats           - 知识库统计
    GET  /mcp/search          - 关键词搜索文章（query: keyword, limit: int）
    GET  /mcp/articles/{id}   - 按 ID 获取文章详情
    POST /mcp/tools           - MCP JSON-RPC 风格工具调用

Usage:
    python3 scripts/mcp_http_server.py                  # 默认 0.0.0.0:8080
    MCP_HOST=0.0.0.0 MCP_PORT=9000 python3 scripts/mcp_http_server.py
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mcp_knowledge_server import (
    search_articles,
    get_article,
    knowledge_stats,
    load_articles,
    get_all_articles,
    update_article_status,
    update_article_fields,
    batch_update_status,
    get_human_review_items,
    resolve_human_review,
    process_human_review_article,
)

from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI 知识库 MCP API",
    description="知识库搜索、审核与看板 HTTP API",
    version="1.1.0",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时预加载文章缓存。"""
    count = len(load_articles())
    logger.info(f"MCP HTTP API 启动，已加载 {count} 篇文章")
    yield
    logger.info("MCP HTTP API 关闭")


app = FastAPI(
    title="AI 知识库 MCP API",
    description="知识库搜索、审核与看板 HTTP API",
    version="1.1.0",
    lifespan=lifespan,
)

STATIC_DIR = PROJECT_ROOT / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    logger.info(f"静态文件目录已挂载: {STATIC_DIR}")
else:
    logger.warning(f"静态文件目录不存在: {STATIC_DIR}，看板页面将不可用")


@app.get("/")
async def root():
    """根路径重定向到公开看板。"""
    return RedirectResponse(url="/static/index.html", status_code=302)


@app.get("/health")
async def health():
    """健康检查端点。"""
    return JSONResponse({"status": "ok"})


@app.get("/mcp/stats")
async def stats():
    """知识库统计信息。"""
    result = knowledge_stats()
    return JSONResponse(result)


@app.get("/mcp/search")
async def search(
    keyword: str = Query(..., description="搜索关键词"),
    limit: int = Query(5, ge=1, le=200, description="返回结果数量（1-200）"),
):
    """按关键词搜索文章标题和摘要。"""
    result = search_articles(keyword=keyword, limit=limit)
    return JSONResponse(result)


@app.get("/mcp/articles/{article_id}")
async def article(article_id: str):
    """按 ID 获取文章完整内容。"""
    result = get_article(article_id=article_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"文章未找到: {article_id}")
    return JSONResponse(result)


@app.post("/mcp/tools")
async def tools(request: dict):
    """MCP JSON-RPC 风格工具调用。

    Request body:
        {"tool": "tool_name", "arguments": {...}}
    """
    tool_name = request.get("tool", "")
    arguments = request.get("arguments", {})

    if tool_name == "search_articles":
        result = search_articles(
            keyword=arguments.get("keyword", ""),
            limit=arguments.get("limit", 5),
        )
    elif tool_name == "get_article":
        result = get_article(article_id=arguments.get("article_id", ""))
        if result is None:
            raise HTTPException(status_code=404, detail=f"文章未找到")
    elif tool_name == "knowledge_stats":
        result = knowledge_stats()
    elif tool_name == "get_all_articles":
        result = get_all_articles(
            status=arguments.get("status"),
            source=arguments.get("source"),
            tag=arguments.get("tag"),
            score_min=arguments.get("score_min"),
            keyword=arguments.get("keyword"),
        )
    elif tool_name == "update_article_status":
        result = update_article_status(
            article_id=arguments.get("article_id", ""),
            new_status=arguments.get("new_status", ""),
        )
    elif tool_name == "update_article_fields":
        result = update_article_fields(
            article_id=arguments.get("article_id", ""),
            updates=arguments.get("updates", {}),
        )
    elif tool_name == "batch_update_status":
        result = batch_update_status(
            article_ids=arguments.get("article_ids", []),
            new_status=arguments.get("new_status", ""),
        )
    elif tool_name == "get_human_review_items":
        result = get_human_review_items()
    elif tool_name == "resolve_human_review":
        result = resolve_human_review(
            filename=arguments.get("filename", ""),
            action=arguments.get("action", "approve"),
        )
    elif tool_name == "process_human_review_article":
        result = process_human_review_article(
            filename=arguments.get("filename", ""),
            article_id=arguments.get("article_id", ""),
            action=arguments.get("action", "approve"),
        )
    else:
        raise HTTPException(status_code=400, detail=f"未知工具: {tool_name}")

    return JSONResponse({"result": result})


def main():
    """启动 HTTP API 服务器。"""
    import uvicorn

    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "5001"))

    logger.info(f"MCP HTTP API 监听: http://{host}:{port}")
    logger.info(f"公开看板: http://{host}:{port}/")
    logger.info(f"审核看板: http://{host}:{port}/static/review.html")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
