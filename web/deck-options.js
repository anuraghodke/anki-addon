// Deck options: add a "Custom Study" section at the top. Svelte may still be
// mounting when this runs, so wait for the first section to appear.
(function () {
  let tries = 0;
  function build() {
    if (document.querySelector(".m-custom-study") || document.querySelector(".m-presets")) return true;
    const first = document.querySelector(".deck-options-page .container-columns > div > .row");
    const sample = document.querySelector(".deck-options-page .container.dark, .deck-options-page .container.light");
    if (!first || !sample) return false;
    // Med School presets
    const prow = document.createElement("div");
    prow.className = first.className;
    const pcard = document.createElement("div");
    pcard.className = sample.className + " m-presets";
    pcard.innerHTML =
      '<div class="position-relative"><h1>Med School Preset</h1></div>' +
      '<div class="m-preset-grid">' +
      '<button type="button" class="m-preset" data-variant="preclinical">' +
        '<span class="m-preset-name">Preclinical</span>' +
        '<span class="m-preset-blurb">Following lectures. 60 new/day, 1-year max interval, lighter weekends.</span></button>' +
      '<button type="button" class="m-preset" data-variant="dedicated">' +
        '<span class="m-preset-name">Dedicated</span>' +
        '<span class="m-preset-blurb">Board study. 10 new/day, 60-day max interval, relearned cards first.</span></button>' +
      "</div>" +
      '<div class="m-preset-note">Both turn on FSRS at 90% retention with 10m 1h learning steps, sibling burying and leech tagging. ' +
      'For exam week use Advance (Browse → Cards → Set Due Date) rather than raising retention.</div>';
    prow.appendChild(pcard);
    first.parentNode.insertBefore(prow, first);
    pcard.querySelectorAll(".m-preset").forEach((b) => {
      if (window.mPresetActive && b.dataset.variant === window.mPresetActive) {
        b.classList.add("is-active");
        b.setAttribute("aria-pressed", "true");
      }
      b.addEventListener("click", () => pycmd("m_preset:" + b.dataset.variant));
    });

    const row = document.createElement("div");
    row.className = first.className;
    const card = document.createElement("div");
    card.className = sample.className + " m-custom-study";
    card.innerHTML =
      '<div class="position-relative"><h1>Custom Study</h1></div>' +
      '<div class="row m-custom-study-row">' +
      '<div class="setting-title">Study extra new cards, review ahead, or build a session from tags.</div>' +
      '<button type="button" class="label-button m-custom-study-btn">Custom study…</button>' +
      "</div>";
    row.appendChild(card);
    first.parentNode.insertBefore(row, first);
    card.querySelector("button").addEventListener("click", () => pycmd("m_custom_study"));
    return true;
  }
  function attempt() { if (build() || tries++ > 100) return; setTimeout(attempt, 50); }
  attempt();
})();
