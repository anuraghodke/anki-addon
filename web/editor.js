// Field text lives inside a shadow root with the note type's font size (often
// 20px). Cap it to match the surrounding UI so the pane reads as one piece.
(function () {
  const CSS = "anki-editable{font-size:15px !important;line-height:1.5 !important;}";
  function patch(host) {
    const sr = host.shadowRoot;
    if (!sr || sr.querySelector("style.m-size")) return;
    const st = document.createElement("style");
    st.className = "m-size";
    st.textContent = CSS;
    sr.appendChild(st);
  }
  function scan() {
    document.querySelectorAll(".rich-text-editable").forEach(patch);
  }
  new MutationObserver(scan).observe(document.documentElement, { childList: true, subtree: true });
  scan();
  // Shadow roots attach a tick after insertion; a short poll covers the gap.
  let n = 0;
  const t = setInterval(() => { scan(); if (++n > 40) clearInterval(t); }, 100);
})();
