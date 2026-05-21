/**
 * Kanban Core — AI 知识库看板
 * 共享看板组件：卡片渲染、列渲染、模态框、搜索、Toast。
 */

const STATUS_CONFIG = {
  pending_review: { label: "待审核", icon: "⏳", cls: "pending" },
  approved: { label: "已批准", icon: "✅", cls: "approved" },
  rejected: { label: "已驳回", icon: "❌", cls: "rejected" },
};

const STATUS_ORDER = ["pending_review", "approved", "rejected"];

// --------------------------------------------------------------------------
// Utilities
// --------------------------------------------------------------------------

function scoreClass(score) {
  if (score === null || score === undefined) return "mid";
  if (score >= 8.0) return "high";
  if (score >= 5.0) return "mid";
  return "low";
}

function formatDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
  } catch {
    return iso.slice(5, 10);
  }
}

function sourceIcon(source) {
  if (source === "github") return "🐙";
  if (source === "rss") return "📡";
  return "📄";
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// --------------------------------------------------------------------------
// Toast
// --------------------------------------------------------------------------

function showToast(message, type = "info", duration = 3000) {
  let container = document.querySelector(".toast-container");
  if (!container) {
    container = document.createElement("div");
    container.className = "toast-container";
    document.body.appendChild(container);
  }

  const icons = { success: "✅", error: "❌", info: "ℹ️" };
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span class="toast-icon">${icons[type] || "ℹ️"}</span><span>${escapeHtml(message)}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add("removing");
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// --------------------------------------------------------------------------
// Stats Bar
// --------------------------------------------------------------------------

function renderStatsBar(stats, container) {
  const dist = stats.status_distribution || {};
  const total = stats.total_articles || 0;
  const pending = dist.pending_review || 0;
  const approved = dist.approved || 0;
  const rejected = dist.rejected || 0;
  const humanReview = dist.human_review || 0;

  const articles = window._allArticles || [];
  const avgScore = articles.length
    ? (articles.reduce((s, a) => s + (a.score || 0), 0) / articles.length).toFixed(1)
    : "—";

  container.innerHTML = `
    <div class="stat-item total">
      <span class="stat-icon">📚</span>
      <span class="stat-value">${total}</span>
      <span class="stat-label">总条目</span>
    </div>
    <div class="stat-divider"></div>
    <div class="stat-item pending">
      <span class="stat-icon">⏳</span>
      <span class="stat-value">${pending}</span>
      <span class="stat-label">待审核</span>
    </div>
    <div class="stat-item approved">
      <span class="stat-icon">✅</span>
      <span class="stat-value">${approved}</span>
      <span class="stat-label">已批准</span>
    </div>
    <div class="stat-item rejected">
      <span class="stat-icon">❌</span>
      <span class="stat-value">${rejected}</span>
      <span class="stat-label">已驳回</span>
    </div>
    <div class="stat-divider"></div>
    <div class="stat-item total">
      <span class="stat-icon">⭐</span>
      <span class="stat-value">${avgScore}</span>
      <span class="stat-label">均分</span>
    </div>
  `;
}

// --------------------------------------------------------------------------
// Card Rendering
// --------------------------------------------------------------------------

function renderCard(article, options = {}) {
  const {
    showCheckbox = false,
    onStatusChange = null,
  } = options;

  const score = article.score ?? "—";
  const scoreCls = scoreClass(score);
  const tags = (article.tags || []).slice(0, 5);
  const tagsHtml = tags.map(t => `<span class="tag">${escapeHtml(t)}</span>`).join("");
  const source = article.source || "unknown";
  const icon = sourceIcon(source);

  return `
    <div class="article-card" data-id="${escapeHtml(article.id)}"
         ${onStatusChange ? `data-status="${escapeHtml(article.status)}"` : ""}>
      <div class="card-header">
        ${showCheckbox ? `<input type="checkbox" class="card-checkbox" data-id="${escapeHtml(article.id)}">` : ""}
        <span class="card-score ${scoreCls}">${score} ★</span>
      </div>
      <div class="card-title">${escapeHtml(article.title || "—")}</div>
      <div class="card-summary">${escapeHtml(article.summary || "")}</div>
      ${tagsHtml ? `<div class="card-tags">${tagsHtml}</div>` : ""}
      <div class="card-footer">
        <span class="card-source">
          <span class="card-source-icon">${icon}</span>
          ${escapeHtml(source)}
        </span>
        <span class="card-date">${formatDate(article.analyzed_at || article.fetched_at)}</span>
      </div>
    </div>
  `;
}

// --------------------------------------------------------------------------
// Column Rendering
// --------------------------------------------------------------------------

function renderColumn(status, articles, options = {}) {
  const config = STATUS_CONFIG[status] || { label: status, icon: "📋", cls: "" };
  const count = articles.length;
  const showCheckbox = (status === "pending_review") && options.showCheckbox;
  const subHeader = options.subHeader || "";

  const cardsHtml = articles.length
    ? articles.map(a => renderCard(a, { ...options, showCheckbox })).join("")
    : `<div class="column-empty">
        <span class="column-empty-icon">${config.icon}</span>
        <span>暂无条目</span>
       </div>`;

  return `
    <div class="kanban-column" data-status="${escapeHtml(status)}">
      <div class="column-header ${config.cls}">
        <span class="column-title">
          <span class="column-icon">${config.icon}</span>
          ${config.label}
        </span>
        <span class="column-count">${count}</span>
      </div>
      ${subHeader}
      <div class="column-cards" data-status="${escapeHtml(status)}">
        ${cardsHtml}
      </div>
    </div>
  `;
}

// --------------------------------------------------------------------------
// Kanban Board
// --------------------------------------------------------------------------

function groupByStatus(articles) {
  const groups = {};
  for (const s of STATUS_ORDER) groups[s] = [];
  for (const a of articles) {
    let s = a.status || "pending_review";
    if (s === "human_review") s = "pending_review";
    if (groups[s]) groups[s].push(a);
    else groups.pending_review.push(a);
  }
  return groups;
}

function renderKanban(articles, container, options = {}) {
  const groups = groupByStatus(articles);
  const colOpts = options.columnOptions || {};
  container.innerHTML = STATUS_ORDER.map(s => renderColumn(s, groups[s], { ...options, ...(colOpts[s] || {}) })).join("");
}

// --------------------------------------------------------------------------
// Modal — Detail / Edit
// --------------------------------------------------------------------------

let _modalOptions = {};

function openModal(article, options = {}) {
  _modalOptions = options;
  const { editable = false } = options;
  const tags = article.tags || [];

  const tagsEditorHtml = editable
    ? `<div class="tags-editor" id="modal-tags-editor">
        ${tags.map(t => `<span class="tag"><span class="tag-remove" data-tag="${escapeHtml(t)}">×</span>${escapeHtml(t)}</span>`).join("")}
        <input type="text" class="tag-input" id="modal-tag-input" placeholder="输入标签后回车添加…">
       </div>`
    : `<div class="tags-editor">${tags.map(t => `<span class="tag">${escapeHtml(t)}</span>`).join("")}</div>`;

  const overlay = document.getElementById("modal-overlay");
  overlay.innerHTML = `
    <div class="modal">
      <div class="modal-header">
        <span class="modal-title">
          <span>${editable ? "✏️" : "📄"}</span>
          ${escapeHtml(article.title || "文章详情")}
        </span>
        <button class="modal-close" id="modal-close-btn" aria-label="关闭">×</button>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label class="form-label">标题</label>
          <input type="text" class="form-input" id="modal-title"
                 value="${escapeHtml(article.title || "")}"
                 ${editable ? "" : "readonly"}>
        </div>
        <div class="form-group">
          <label class="form-label">摘要</label>
          <textarea class="form-textarea" id="modal-summary"
                    rows="5" ${editable ? "" : "readonly"}>${escapeHtml(article.summary || "")}</textarea>
        </div>
        <div class="form-group">
          <label class="form-label">标签</label>
          ${tagsEditorHtml}
        </div>
        <div class="form-group">
          <label class="form-label">评分</label>
          <input type="number" class="form-input form-input-score" id="modal-score"
                 value="${article.score ?? ""}" min="0" max="10" step="0.1"
                 ${editable ? "" : "readonly"}>
        </div>
        <div class="meta-info">
          <div class="meta-row"><span>ID</span><span class="font-mono">${escapeHtml(article.id || "")}</span></div>
          <div class="meta-row"><span>来源</span><span>${sourceIcon(article.source || "")} ${escapeHtml(article.source || "—")}</span></div>
          <div class="meta-row"><span>链接</span><span><a href="${escapeHtml(article.source_url || "#")}" target="_blank" rel="noopener">${escapeHtml(article.source_url || "—")}</a></span></div>
          <div class="meta-row"><span>抓取时间</span><span>${formatDate(article.fetched_at)}</span></div>
          <div class="meta-row"><span>分析时间</span><span>${formatDate(article.analyzed_at)}</span></div>
          <div class="meta-row"><span>状态</span><span>${STATUS_CONFIG[article.status]?.icon || "📋"} ${STATUS_CONFIG[article.status]?.label || article.status}</span></div>
          <div class="meta-row"><span>审核人</span><span>${escapeHtml(article.reviewer || "—")}</span></div>
          <div class="meta-row"><span>审核时间</span><span>${formatDate(article.reviewed_at)}</span></div>
        </div>
      </div>
      <div class="modal-footer">
        ${editable ? `
          ${article.status === "approved" || article.status === "pending_review" || article.status === "human_review" ? `
            <button class="btn btn-ghost btn-sm" id="modal-save">💾 保存</button>
            <button class="btn btn-ghost btn-sm" id="modal-reject">❌ 驳回</button>
            ${article.status !== "approved" ? `<button class="btn btn-primary btn-sm" id="modal-approve">✅ 批准</button>` : ""}
          ` : ""}
          ${article.status === "rejected" ? `
            <button class="btn btn-ghost btn-sm" id="modal-save">💾 保存</button>
            <button class="btn btn-primary btn-sm" id="modal-approve">✅ 批准</button>
          ` : ""}
        ` : `
          <button class="btn btn-ghost btn-sm" id="modal-close-btn2">关闭</button>
        `}
      </div>
    </div>
  `;

  overlay.classList.add("open");

  // Close handlers
  overlay.querySelectorAll("#modal-close-btn, #modal-close-btn2").forEach(btn => {
    btn.addEventListener("click", closeModal);
  });

  overlay.addEventListener("click", e => {
    if (e.target === overlay) closeModal();
  });

  // Tag editing
  const tagInput = document.getElementById("modal-tag-input");
  if (tagInput) {
    const editor = document.getElementById("modal-tags-editor");

    tagInput.addEventListener("keydown", e => {
      if (e.key === "Enter") {
        e.preventDefault();
        const val = tagInput.value.trim().toLowerCase().replace(/\s+/g, "-");
        if (val) {
          const existingTags = Array.from(editor.querySelectorAll(".tag")).map(t => t.textContent.replace("×", "").trim());
          if (!existingTags.includes(val)) {
            const tagEl = document.createElement("span");
            tagEl.className = "tag";
            tagEl.innerHTML = `<span class="tag-remove" data-tag="${escapeHtml(val)}">×</span>${escapeHtml(val)}`;
            editor.insertBefore(tagEl, tagInput);
          }
        }
        tagInput.value = "";
      }
    });

    editor.addEventListener("click", e => {
      const removeBtn = e.target.closest(".tag-remove");
      if (removeBtn) {
        removeBtn.closest(".tag").remove();
      }
    });
  }

  // Action handlers (only in editable mode)
  if (editable) {
    document.getElementById("modal-save")?.addEventListener("click", async () => {
      const tags = Array.from(document.querySelectorAll("#modal-tags-editor .tag"))
        .map(t => t.textContent.replace("×", "").trim())
        .filter(Boolean);
      const updates = {
        title: document.getElementById("modal-title").value.trim(),
        summary: document.getElementById("modal-summary").value.trim(),
        tags,
        score: parseFloat(document.getElementById("modal-score").value) || 0,
      };
      try {
        const result = await API.updateArticle(article.id, updates);
        if (result.error) throw new Error(result.error);
        showToast("修改已保存", "success");
        closeModal();
        if (options.onUpdate) options.onUpdate(article.id, updates);
      } catch (err) {
        showToast(`保存失败: ${err.message}`, "error");
      }
    });

    document.getElementById("modal-approve")?.addEventListener("click", async () => {
      try {
        const result = await API.updateStatus(article.id, "approved");
        if (result.error) throw new Error(result.error);
        showToast("已批准", "success");
        closeModal();
        if (options.onStatusChange) options.onStatusChange(article.id, "approved");
      } catch (err) {
        showToast(`批准失败: ${err.message}`, "error");
      }
    });

    document.getElementById("modal-reject")?.addEventListener("click", async () => {
      try {
        const result = await API.updateStatus(article.id, "rejected");
        if (result.error) throw new Error(result.error);
        showToast("已驳回", "success");
        closeModal();
        if (options.onStatusChange) options.onStatusChange(article.id, "rejected");
      } catch (err) {
        showToast(`驳回失败: ${err.message}`, "error");
      }
    });
  }
}

function closeModal() {
  const overlay = document.getElementById("modal-overlay");
  if (overlay) {
    overlay.classList.remove("open");
    overlay.innerHTML = "";
  }
}

// --------------------------------------------------------------------------
// Filter & Search
// --------------------------------------------------------------------------

function applyFilters(articles, filters) {
  let result = [...articles];

  if (filters.keyword) {
    const kw = filters.keyword.toLowerCase();
    result = result.filter(a =>
      (a.title || "").toLowerCase().includes(kw) ||
      (a.summary || "").toLowerCase().includes(kw) ||
      (a.tags || []).some(t => t.toLowerCase().includes(kw))
    );
  }

  if (filters.source) {
    result = result.filter(a => a.source === filters.source);
  }

  if (filters.scoreMin != null) {
    result = result.filter(a => (a.score || 0) >= filters.scoreMin);
  }

  if (filters.tag) {
    result = result.filter(a => (a.tags || []).includes(filters.tag));
  }

  return result;
}

// --------------------------------------------------------------------------
// Export globals
// --------------------------------------------------------------------------

window.Kanban = {
  STATUS_CONFIG,
  STATUS_ORDER,
  renderStatsBar,
  renderCard,
  renderColumn,
  renderKanban,
  groupByStatus,
  openModal,
  closeModal,
  showToast,
  applyFilters,
  escapeHtml,
  scoreClass,
  formatDate,
};
