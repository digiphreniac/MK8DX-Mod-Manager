// ===== UI components: Progress (one bar for each phase of a long job) =====
//   const p = ui.progress({ id, title, startText, note, units })  ->  { el, update(state) }
//     title      the line at the top left ("Putting your mods together..."); the time it has been going is at the right
//     startText  what the line under the bars says before the first answer arrives
//     note       a small line at the bottom
//     units      { phaseId: "files" }: the phases that say "x of y files" (the others say what they are doing, or just the phase)
//   p.update(state) takes what the backend says: { active, phases: [{ id, label }], phase, done, total, detail, elapsed }.
// The bars: done ones are full, the one it is in fills as it goes (or slides while it can't say how many there will be), the rest are empty.
// The page asks for the state and calls update(); this draws it and knows nothing about what the job is.
ui.progress = function (spec) {
  const elapsedEl = ui.el("span", { class: "ui-progress-elapsed", text: "0:00" });
  const phasesEl = ui.el("div", "ui-progress-phases");
  const detailEl = ui.el("div", { class: "ui-progress-detail", text: spec.startText || "Starting..." });
  const el = ui.el("div", { class: "ui-progress", id: spec.id },
    ui.el("div", "ui-progress-head", ui.el("span", { class: "ui-progress-title", text: spec.title }), elapsedEl),
    phasesEl, detailEl, spec.note ? ui.el("div", { class: "ui-progress-note", text: spec.note }) : null);

  function update(p) {
    if (!p || !p.active) return;
    const signature = p.phases.map(x => x.id).join(",");
    if (phasesEl.dataset.signature !== signature) {
      phasesEl.dataset.signature = signature;
      phasesEl.replaceChildren(...p.phases.map(x => ui.el("div", { class: "ui-progress-phase", attrs: { "data-phase": x.id } },
        ui.el("div", "ui-progress-bar", ui.el("div", "ui-progress-fill")), ui.el("div", { class: "ui-progress-name", text: x.label }))));
    }
    const at = p.phases.findIndex(x => x.id === p.phase);
    p.phases.forEach((x, i) => {
      const phase = phasesEl.children[i];
      const state = i < at ? "done" : i === at ? "now" : "todo";
      const known = state === "now" && p.total;
      phase.className = "ui-progress-phase ui-progress-phase--" + state + (state === "now" && !known ? " ui-progress-phase--unknown" : "");
      // (the one it is in always shows a little, so a phase that has only just begun doesn't look like it hasn't)
      phase.querySelector(".ui-progress-fill").style.width = state === "done" ? "100%" : known ? `${Math.max(4, Math.min(100, Math.round(100 * p.done / p.total)))}%` : "";
      phase.querySelector(".ui-progress-name").textContent = (state === "done" ? "✓ " : "") + x.label;
    });
    const label = p.phases[at].label;
    const unit = (spec.units || {})[p.phase];
    detailEl.textContent = unit && p.total ? `${label}: ${p.done.toLocaleString()} of ${p.total.toLocaleString()} ${unit}`
      : p.detail ? `${label}: ${p.detail}` : `${label}...`;
    elapsedEl.textContent = ui.progress.formatElapsed(p.elapsed);
  }
  return { el, update };
};

// 75 -> "1:15"
ui.progress.formatElapsed = function (seconds) {
  const s = Math.floor(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};
