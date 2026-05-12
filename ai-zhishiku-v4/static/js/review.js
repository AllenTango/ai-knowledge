/**
 * Review Board — 内部审核看板专用逻辑
 */

let allArticles = [];
let selectedIds = new Set();
let sortableInstances = [];
let tagOptions = new Set();
let currentFilters = {};

// --------------------------------------------------------------------------
// Init
// --------------------------------------------------------------------------

async function initReview() {
  try {
    const [stats, articles] = await Promise.all([
      API.getStats(),
      API.getAllArticles(),
    ]);

    allArticles = articles.filter(a => a.status !== "pending_review");
    collectTags(articles);
    renderTagFilter();
    renderStatsBar(stats);
    renderBoard();
    bindToolbar();
  } catch (err) {
    Kanban.showToast("初始化失败: " + err.message, "error");
    document.getElementById("kanban-board").innerHTML = `
      <div class="board-loading" style="color:var(--dracula-red)">⚠️ 加载失败: ${Kanban.escapeHtml(err.message)}</div>
    `;
  }
}

function collectTags(articles) {
  tagOptions.clear();
  for (const a of articles) {
    for (const t of (a.tags || [])) {
      tagOptions.add(t);
    }
  }
}

function renderTagFilter() {
  const select = document.getElementById("filter-tag");
  select.innerHTML = `<option value="">全部标签</option>`;
  for (const t of [...tagOptions].sort()) {
    select.innerHTML += `<option value="${Kanban.escapeHtml(t)}">${Kanban.escapeHtml(t)}</option>`;
  }
}

function renderStatsBar(stats) {
  const dist = stats.status_distribution || {};
  const total = stats.total_articles || 0;
  const pending = dist.pending_review || 0;
  const approved = dist.approved || 0;
  const rejected = dist.rejected || 0;

  const avgScore = allArticles.length
    ? (allArticles.reduce((s, a) => s + (a.score || 0), 0) / allArticles.length).toFixed(1)
    : "—";

  document.getElementById("stat-total").textContent = total;
  document.getElementById("stat-pending").textContent = pending;
  document.getElementById("stat-approved").textContent = approved;
  document.getElementById("stat-rejected").textContent = rejected;
  document.getElementById("stat-avgscore").textContent = avgScore;
}

// --------------------------------------------------------------------------
// Board
// --------------------------------------------------------------------------

function getFilters() {
  return {
    keyword: document.getElementById("search-input")?.value?.trim() || "",
    source: document.getElementById("filter-source")?.value || "",
    scoreMin: parseFloat(document.getElementById("filter-score")?.value) || null,
    tag: document.getElementById("filter-tag")?.value || "",
  };
}

function getPendingArticles() {
  const filters = currentFilters;
  return allArticles.filter(a => {
    const isPending = a.status === "pending_review" || a.status === "human_review";
    if (!isPending) return false;
    if (filters.keyword) {
      const kw = filters.keyword.toLowerCase();
      if (!(a.title || "").toLowerCase().includes(kw) &&
          !(a.summary || "").toLowerCase().includes(kw) &&
          !(a.tags || []).some(t => t.toLowerCase().includes(kw))) return false;
    }
    if (filters.source && a.source !== filters.source) return false;
    if (filters.scoreMin != null && (a.score || 0) < filters.scoreMin) return false;
    if (filters.tag && !(a.tags || []).includes(filters.tag)) return false;
    return true;
  });
}

function renderBoard() {
  const container = document.getElementById("kanban-board");
  currentFilters = getFilters();
  const filtered = Kanban.applyFilters(allArticles, currentFilters);

  for (const s of sortableInstances) { if (s) s.destroy(); }
  sortableInstances = [];

  window._allArticles = allArticles;

  const pendingCount = filtered.filter(a => a.status === "pending_review" || a.status === "human_review").length;
  const selectedCount = [...selectedIds].filter(id => {
    const a = allArticles.find(x => x.id === id);
    return a && (a.status === "pending_review" || a.status === "human_review");
  }).length;

  const pendingSubHeader = `
    <div class="col-actions" id="pending-actions">
      <label class="col-select-label">
        <input type="checkbox" class="col-select-all" id="pending-select-all"
               ${selectedCount === pendingCount && pendingCount > 0 ? "checked" : ""}
               ${pendingCount === 0 ? "disabled" : ""}>
        全选
      </label>
      <span class="col-selected-count" id="pending-selected-count">${selectedCount > 0 ? `已选 ${selectedCount} 项` : ""}</span>
      <div class="col-batch-btns">
        <button class="btn btn-success btn-xs" id="pending-batch-approve"
                ${selectedCount === 0 ? "disabled" : ""}>✅ 批准</button>
        <button class="btn btn-danger btn-xs" id="pending-batch-reject"
                ${selectedCount === 0 ? "disabled" : ""}>❌ 驳回</button>
      </div>
    </div>
  `;

  Kanban.renderKanban(filtered, container, {
    showCheckbox: true,
    onStatusChange: handleStatusChange,
    onUpdate: handleArticleUpdate,
    columnOptions: {
      pending_review: { subHeader: pendingSubHeader },
    },
  });

  bindCardEvents();
  bindPendingBatchActions();

  selectedIds = new Set([...selectedIds].filter(id => {
    const a = allArticles.find(x => x.id === id);
    return a && (a.status === "pending_review" || a.status === "human_review");
  }));
  updateCheckboxes();

  for (const status of Kanban.STATUS_ORDER) {
    const col = container.querySelector(`.column-cards[data-status="${status}"]`);
    if (!col) continue;

    const s = new Sortable(col, {
      group: "kanban",
      animation: 200,
      ghostClass: "sortable-ghost",
      chosenClass: "sortable-chosen",
      dragClass: "dragging",
      onEnd: async (evt) => {
        const cardId = evt.item.dataset.id;
        const newStatus = evt.to.dataset.status;
        const oldStatus = evt.from.dataset.status;
        if (newStatus === oldStatus) return;

        if ((oldStatus === "approved" || oldStatus === "rejected") && newStatus === "pending_review") {
          Kanban.showToast("已批准/已驳回的条目不能移回待审核", "error");
          renderBoard();
          return;
        }

        try {
          const result = await API.updateStatus(cardId, newStatus);
          if (result.error) throw new Error(result.error);

          const article = allArticles.find(a => a.id === cardId);
          if (article) article.status = newStatus;

          Kanban.showToast(`已移动到「${Kanban.STATUS_CONFIG[newStatus]?.label || newStatus}」`, "success");

          const stats = await API.getStats();
          renderStatsBar(stats);
          renderBoard();
        } catch (err) {
          Kanban.showToast(`移动失败: ${err.message}`, "error");
          renderBoard();
        }
      },
    });
    sortableInstances.push(s);
  }

  for (const status of Kanban.STATUS_ORDER) {
    const count = filtered.filter(a => {
      if (status === "pending_review") {
        return a.status === "pending_review" || a.status === "human_review";
      }
      return a.status === status;
    }).length;
    const el = container.querySelector(`.kanban-column[data-status="${status}"] .column-count`);
    if (el) el.textContent = count;
  }
}

function bindCardEvents() {
  document.querySelectorAll(".article-card").forEach(card => {
    card.addEventListener("click", (e) => {
      if (
        e.target.classList.contains("card-checkbox") ||
        e.target.closest(".card-checkbox") ||
        e.target.classList.contains("tag-remove")
      ) return;

      const article = allArticles.find(a => a.id === card.dataset.id);
      if (article) {
        Kanban.openModal(article, {
          editable: true,
          onStatusChange: handleStatusChange,
          onUpdate: handleArticleUpdate,
        });
      }
    });
  });
}

async function handleStatusChange(articleId, newStatus) {
  const article = allArticles.find(a => a.id === articleId);
  if (article) article.status = newStatus;
  const isPending = (newStatus === "pending_review" || newStatus === "human_review");
  if (!isPending) selectedIds.delete(articleId);
  const stats = await API.getStats().catch(() => null);
  if (stats) renderStatsBar(stats);
  renderBoard();
  refreshPendingActions();
}

async function handleArticleUpdate(articleId, updates) {
  const article = allArticles.find(a => a.id === articleId);
  if (article) Object.assign(article, updates);
  const stats = await API.getStats().catch(() => null);
  if (stats) renderStatsBar(stats);
  renderBoard();
}

// --------------------------------------------------------------------------
// Toolbar & Batch
// --------------------------------------------------------------------------

function bindToolbar() {
  document.getElementById("search-input")?.addEventListener("input", debounce(renderBoard, 300));
  document.getElementById("filter-source")?.addEventListener("change", renderBoard);
  document.getElementById("filter-score")?.addEventListener("change", renderBoard);
  document.getElementById("filter-tag")?.addEventListener("change", renderBoard);
}

function updateCheckboxes() {
  document.querySelectorAll(".card-checkbox").forEach(cb => {
    cb.checked = selectedIds.has(cb.dataset.id);
  });
}

function refreshPendingActions() {
  const filtered = Kanban.applyFilters(allArticles, currentFilters);
  const pending = filtered.filter(a => a.status === "pending_review" || a.status === "human_review");
  const pendingSelected = [...selectedIds].filter(id => {
    const a = allArticles.find(x => x.id === id);
    return a && (a.status === "pending_review" || a.status === "human_review");
  });

  const countEl = document.getElementById("pending-selected-count");
  const selectAllEl = document.getElementById("pending-select-all");
  const approveBtn = document.getElementById("pending-batch-approve");
  const rejectBtn = document.getElementById("pending-batch-reject");

  if (countEl) countEl.textContent = pendingSelected.length > 0 ? `已选 ${pendingSelected.length} 项` : "";
  if (selectAllEl) selectAllEl.checked = pendingSelected.length === pending.length && pending.length > 0;
  if (approveBtn) approveBtn.disabled = pendingSelected.length === 0;
  if (rejectBtn) rejectBtn.disabled = pendingSelected.length === 0;
}

function bindPendingBatchActions() {
  const selectAll = document.getElementById("pending-select-all");
  if (selectAll) {
    selectAll.addEventListener("change", e => {
      const pendingIds = getPendingArticles().map(a => a.id);
      if (e.target.checked) {
        pendingIds.forEach(id => selectedIds.add(id));
      } else {
        pendingIds.forEach(id => selectedIds.delete(id));
      }
      updateCheckboxes();
      refreshPendingActions();
    });
  }

  const approveBtn = document.getElementById("pending-batch-approve");
  if (approveBtn) {
    approveBtn.addEventListener("click", () => pendingBatchAction("approved"));
  }

  const rejectBtn = document.getElementById("pending-batch-reject");
  if (rejectBtn) {
    rejectBtn.addEventListener("click", () => pendingBatchAction("rejected"));
  }
}

async function pendingBatchAction(newStatus) {
  const pendingSelected = [...selectedIds].filter(id => {
    const a = allArticles.find(x => x.id === id);
    return a && (a.status === "pending_review" || a.status === "human_review");
  });
  if (!pendingSelected.length) return;
  const label = Kanban.STATUS_CONFIG[newStatus]?.label || newStatus;
  if (!confirm(`确定要将 ${pendingSelected.length} 条设为「${label}」吗？`)) return;

  try {
    const result = await API.batchUpdate(pendingSelected, newStatus);
    Kanban.showToast(
      `成功 ${result.success_count} 条${result.failed.length ? `，失败 ${result.failed.length} 条` : ""}`,
      result.failed.length ? "error" : "success"
    );
    const [stats, articles] = await Promise.all([API.getStats(), API.getAllArticles()]);
    allArticles = articles.filter(a => a.status !== "pending_review");
    renderStatsBar(stats);
    selectedIds.clear();
    renderBoard();
  } catch (err) {
    Kanban.showToast(`批量操作失败: ${err.message}`, "error");
  }
}

// --------------------------------------------------------------------------
// Checkbox delegation
// --------------------------------------------------------------------------

document.addEventListener("change", e => {
  if (e.target.classList.contains("card-checkbox")) {
    const id = e.target.dataset.id;
    if (e.target.checked) selectedIds.add(id);
    else selectedIds.delete(id);
    updateCheckboxes();
    refreshPendingActions();
  }
});

// --------------------------------------------------------------------------
// Utility
// --------------------------------------------------------------------------

function debounce(fn, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

// --------------------------------------------------------------------------
// ESC key — close modal
// --------------------------------------------------------------------------

document.addEventListener("keydown", e => {
  if (e.key === "Escape") {
    Kanban.closeModal();
  }
});

// --------------------------------------------------------------------------
// Export
// --------------------------------------------------------------------------

window.ReviewBoard = {
  init: initReview,
  renderBoard,
  renderStatsBar,
};
