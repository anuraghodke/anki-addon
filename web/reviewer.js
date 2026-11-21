// Flip animation + click-to-reveal for the reviewer card. Wraps the globals
// that Python calls (_showQuestion / _showAnswer) so templates stay untouched.
(function () {
  const qa = () => document.getElementById("qa");
  const FLIP_OUT = 170;
  let onAnswer = false;

  const origQ = window._showQuestion;
  const origA = window._showAnswer;
  if (typeof origQ !== "function" || typeof origA !== "function") return;

  function restyle(el, cls, ms) {
    el.classList.remove("m-flip-out", "m-flip-in", "m-enter");
    void el.offsetWidth; // restart animation
    el.classList.add(cls);
    setTimeout(() => el.classList.remove(cls), ms + 40);
  }

  // Group everything before <hr id=answer> so the question half can be demoted.
  function demoteFront() {
    const el = qa();
    const hr = el && el.querySelector("hr#answer");
    if (!hr || el.querySelector(".m-front")) return;
    const wrap = document.createElement("div");
    wrap.className = "m-front";
    while (el.firstChild && el.firstChild !== hr) wrap.appendChild(el.firstChild);
    if (wrap.childNodes.length) el.insertBefore(wrap, hr);
  }

  window._showQuestion = function (q, a, bodyclass) {
    onAnswer = false;
    const el = qa();
    if (el) {
      el.classList.remove("m-answer");
      restyle(el, "m-enter", 220);
    }
    return origQ(q, a, bodyclass);
  };

  window._showAnswer = function (a, bodyclass) {
    const el = qa();
    if (!el || document.body.classList.contains("reduce-motion")) {
      onAnswer = true;
      el && el.classList.add("m-answer");
      const r = origA(a, bodyclass);
      setTimeout(demoteFront, 0);
      return r;
    }
    restyle(el, "m-flip-out", FLIP_OUT);
    setTimeout(() => {
      onAnswer = true;
      el.classList.add("m-answer");
      origA(a, bodyclass);
      restyle(el, "m-flip-in", 190);
      // content is set asynchronously; demote once it lands
      let tries = 0;
      const tick = () => {
        if (el.querySelector("hr#answer") || tries++ > 20) return demoteFront();
        setTimeout(tick, 50);
      };
      tick();
    }, FLIP_OUT);
  };

  // Click the card to flip it (ignore interactive elements and text selection).
  document.addEventListener("click", (ev) => {
    if (onAnswer) return;
    const el = qa();
    if (!el || !el.contains(ev.target)) return;
    if (ev.target.closest("a, button, input, textarea, select, audio, video, [contenteditable]")) return;
    const sel = window.getSelection();
    if (sel && sel.toString()) return;
    if (typeof pycmd === "function") pycmd("ans");
  });
})();
