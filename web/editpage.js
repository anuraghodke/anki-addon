// Edit page: renders the card list and talks to Python via pycmd("m_edit:...").
(function () {
  const $ = (id) => document.getElementById(id);
  let data = { decks: [], deck: 0, rows: [] };
  let filter = "";

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function text(html) {
    const d = document.createElement("div");
    d.innerHTML = html;
    return d.textContent || "";
  }

  function renderDecks() {
    const sel = $("m-deck");
    sel.innerHTML = data.decks.map((d) => `<option value="${d.id}" ${d.id === data.deck ? "selected" : ""}>${esc(d.name)}</option>`).join("");
  }

  function fieldHtml(cls, html, label) {
    return `<div class="m-field-wrap"><div class="m-field ${cls}" contenteditable="true" spellcheck="false">${html}</div><div class="m-label">${label}</div></div>`;
  }

  // Incremental list: render a chunk at a time, more as the sentinel scrolls into view.
  const CHUNK = 60;
  let visibleRows = [];
  let rendered = 0;
  let sentinel = null;
  let observer = null;

  function cardHtml(r, i) {
    return `
      <li class="m-card ${r.suspended ? "is-suspended" : ""}" data-nid="${r.id}">
        <div class="m-idx">${i + 1}</div>
        <div class="m-fields">
          ${fieldHtml("front", r.front, "Front")}
          <div class="m-divider"></div>
          ${fieldHtml("back", r.back, "Back")}
        </div>
        <div class="m-actions">
          <button class="m-icon m-suspend" title="${r.suspended ? "Unsuspend" : "Suspend"}" data-act="suspend">${r.suspended ? "&#9654;" : "&#10074;&#10074;"}</button>
          <button class="m-icon m-delete" title="Delete" data-act="delete">&#128465;</button>
        </div>
      </li>`;
  }

  function renderMore() {
    if (rendered >= visibleRows.length) return;
    const end = Math.min(rendered + CHUNK, visibleRows.length);
    const html = visibleRows.slice(rendered, end).map((r, k) => cardHtml(r, rendered + k)).join("");
    sentinel.insertAdjacentHTML("beforebegin", html);
    rendered = end;
    if (rendered >= visibleRows.length) sentinel.hidden = true;
  }

  function renderCards() {
    const list = $("m-cards");
    const q = filter.trim().toLowerCase();
    visibleRows = data.rows.filter((r) => !q || text(r.front).toLowerCase().includes(q) || text(r.back).toLowerCase().includes(q));
    $("m-count").textContent = `${data.rows.length} card${data.rows.length === 1 ? "" : "s"}` + (q ? ` · ${visibleRows.length} shown` : "");
    $("m-empty").hidden = data.rows.length > 0;
    list.innerHTML = '<li class="m-sentinel" aria-hidden="true"></li>';
    sentinel = list.querySelector(".m-sentinel");
    sentinel.hidden = false;
    rendered = 0;
    renderMore();
    if (observer) observer.disconnect();
    observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) renderMore();
    }, { rootMargin: "600px 0px" });
    observer.observe(sentinel);
  }

  function render(d) {
    data = d;
    renderDecks();
    renderCards();
  }

  // --- editing -----------------------------------------------------------
  function cardOf(el) { return el.closest(".m-card"); }

  function saveCard(card) {
    const nid = card.dataset.nid;
    const front = card.querySelector(".m-field.front").innerHTML;
    const back = card.querySelector(".m-field.back").innerHTML;
    const row = data.rows.find((r) => String(r.id) === nid);
    if (!row || (row.front === front && row.back === back)) return;
    row.front = front; row.back = back;
    pycmd("m_edit:save:" + JSON.stringify({ id: Number(nid), front, back }));
    card.classList.add("is-saved");
    setTimeout(() => card.classList.remove("is-saved"), 600);
  }

  document.addEventListener("focusout", (e) => {
    const f = e.target.closest && e.target.closest(".m-card .m-field");
    if (f) saveCard(cardOf(f));
  });

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-act]");
    if (!btn) return;
    const card = cardOf(btn);
    if (!card) return;
    if (btn.dataset.act === "delete") {
      if (confirm("Delete this card?")) pycmd("m_edit:delete:" + card.dataset.nid);
    } else if (btn.dataset.act === "suspend") {
      pycmd("m_edit:suspend:" + card.dataset.nid);
    }
  });

  // Tab from Front to Back, Enter (without Shift) commits and moves on.
  document.addEventListener("keydown", (e) => {
    const f = e.target.closest && e.target.closest(".m-field");
    if (!f) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (f.id === "m-add-back" || f.id === "m-add-front") { if (f.id === "m-add-front") $("m-add-back").focus(); else addCard(); return; }
      const card = cardOf(f);
      if (f.classList.contains("front")) card.querySelector(".m-field.back").focus();
      else { f.blur(); const next = card.nextElementSibling; if (next) next.querySelector(".m-field.front").focus(); }
    }
  });

  // --- add ----------------------------------------------------------------
  function addState() {
    const has = text($("m-add-front").innerHTML).trim() || text($("m-add-back").innerHTML).trim();
    $("m-add-btn").disabled = !has;
  }
  function addCard() {
    const front = $("m-add-front").innerHTML, back = $("m-add-back").innerHTML;
    if (!text(front).trim() && !text(back).trim()) return;
    pycmd("m_edit:add:" + JSON.stringify({ front, back }));
  }
  function addedOk() {
    $("m-add-front").innerHTML = ""; $("m-add-back").innerHTML = "";
    addState();
    $("m-add-front").focus();
  }
  let pending = null;
  function bind() {
    if (!$("m-edit")) return; // not the edit page (e.g. the bottom bar)
    $("m-add-front").addEventListener("input", addState);
    $("m-add-back").addEventListener("input", addState);
    $("m-add-btn").addEventListener("click", addCard);
    $("m-deck").addEventListener("change", (e) => pycmd("m_edit:deck:" + e.target.value));
    $("m-search").addEventListener("input", (e) => { filter = e.target.value; renderCards(); });
    if (pending) { render(pending); pending = null; }
  }
  const ready = () => document.readyState !== "loading" && $("m-cards");
  if (ready()) bind(); else document.addEventListener("DOMContentLoaded", bind);

  // Python may push data before the DOM is bound; hold it until then.
  window.mEdit = {
    render: (d) => (ready() && $("m-deck") ? render(d) : (pending = d)),
    addedOk,
  };
})();
