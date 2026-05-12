/**
 * API Client — AI 知识库看板
 * 封装所有与 MCP HTTP API 的通信。
 */

const API = {
  base: window.location.origin,

  async _get(path) {
    const res = await fetch(`${this.base}${path}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },

  async _post(path, body) {
    const res = await fetch(`${this.base}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },

  async _tool(tool, args = {}) {
    const data = await this._post("/mcp/tools", { tool, arguments: args });
    return data.result;
  },

  getStats() {
    return this._get("/mcp/stats");
  },

  search(keyword, limit = 50) {
    return this._get(`/mcp/search?keyword=${encodeURIComponent(keyword)}&limit=${limit}`);
  },

  getArticle(id) {
    return this._get(`/mcp/articles/${encodeURIComponent(id)}`);
  },

  getAllArticles({ status, source, tag, score_min, keyword } = {}) {
    return this._tool("get_all_articles", { status, source, tag, score_min, keyword });
  },

  updateStatus(id, new_status) {
    return this._tool("update_article_status", { article_id: id, new_status });
  },

  updateArticle(id, updates) {
    return this._tool("update_article_fields", { article_id: id, updates });
  },

  batchUpdate(ids, new_status) {
    return this._tool("batch_update_status", { article_ids: ids, new_status });
  },

  getHumanReviewItems() {
    return this._tool("get_human_review_items", {});
  },

  resolveHumanReview(filename, action = "approve") {
    return this._tool("resolve_human_review", { filename, action });
  },

  processHumanReviewArticle(filename, articleId, action = "approve") {
    return this._tool("process_human_review_article", {
      filename,
      article_id: articleId,
      action,
    });
  },
};
