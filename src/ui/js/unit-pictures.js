// ---- The menu pictures a mod brings (Select screen, Mini map, Results): the tag on a character mod row and its window.
const PIC_LABELS = { Chara: "Select screen", MapChara: "Mini map", edChara: "Results" };
const PIC_ORDER = ["Chara", "MapChara", "edChara"];
const unitPics = {};       // unit key -> what Api.get_unit_pictures() said about it
function pictureSvg() {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("aria-hidden", "true");
  const frame = document.createElementNS(NS, "path");
  frame.setAttribute("class", "pic-line");
  frame.setAttribute("d", "M3 2.5h10a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1zM2.2 12 6 8.2l2.6 2.6 1.9-1.9 3.3 3.1");
  const dot = document.createElementNS(NS, "circle");
  dot.setAttribute("class", "pic-dot");
  dot.setAttribute("cx", "10.8");
  dot.setAttribute("cy", "5.6");
  dot.setAttribute("r", "1.2");
  svg.append(frame, dot);
  return svg;
}
function pictureSummary(p) {
  const have = PIC_ORDER.filter(k => p.kinds.includes(k)).map(k => PIC_LABELS[k]);
  const lack = PIC_ORDER.filter(k => !p.kinds.includes(k)).map(k => PIC_LABELS[k]);
  let t = p.for ? `Menu pictures named for ${p.for}, not this character: ${have.join(", ")}` : `Menu pictures: ${have.join(", ")}`;
  if (lack.length && !p.for) t += ` (no ${lack.join(" or ")})`;
  if (p.versions > 1) t += ` \u00b7 ${p.versions} versions`;
  if (p.colours > 1) t += ` \u00b7 ${p.colours} colours`;
  return t;
}
async function openUnitPictures(unitKey, siblings, modLabel) {
  ui.menu.closeAll();
  const back = cgEl("div", "gate-backdrop");
  const card = cgEl("div", "gate-card pics-card");
  card.setAttribute("role", "dialog");
  card.setAttribute("aria-modal", "true");
  card.appendChild(cgEl("h3", null, "Menu pictures"));
  card.appendChild(cgEl("div", "pics-sub", modLabel));
  const body = cgEl("div", "pics-body");
  body.appendChild(cgEl("div", "voice-empty", "Looking at the pictures\u2026"));
  card.appendChild(body);
  const acts = cgEl("div", "gate-actions");
  const close = () => { back.remove(); document.removeEventListener("keydown", onKey, true); };
  const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
  document.addEventListener("keydown", onKey, true);
  const closeBtn = button("Close", "primary", close);
  acts.appendChild(closeBtn);
  card.appendChild(acts);
  back.appendChild(card);
  back.addEventListener("click", (e) => { if (e.target === back) close(); });
  document.body.appendChild(back);
  closeBtn.focus();
  let r;
  try { r = await pywebview.api.get_unit_picture_sets(unitKey, siblings); } catch (e) { r = null; }
  if (!back.isConnected) return;
  body.replaceChildren();
  const sets = (r && r.sets) || [];
  if (!sets.length) { body.appendChild(cgEl("div", "voice-empty", "No menu pictures could be read from this mod.")); return; }
  for (const st of sets) {
    const box = cgEl("div", "pics-set");
    const title = cgEl("div", "pics-title", st.label);
    if (st.colours > 1) title.appendChild(cgEl("span", "pics-note", `${st.colours} colours - the first is shown`));
    box.appendChild(title);
    if (st.for) box.appendChild(cgEl("div", "pics-warn", `These pictures are named for ${st.for}, not for this character. You can still use them from its Icons row.`));
    const row = cgEl("div", "pics-row");
    for (const kind of PIC_ORDER) {
      const tile = cgEl("div", "pics-tile");
      const have = st.kinds[kind];
      const frame = cgEl("div", "pics-img" + (have ? "" : " none"));
      if (have) {
        const img = document.createElement("img");
        img.src = have.preview;
        img.alt = PIC_LABELS[kind];
        frame.appendChild(img);
      } else {
        frame.textContent = kind !== "Chara" && st.kinds.Chara ? "Not included - can be made from the Select screen" : "Not included";
      }
      tile.appendChild(frame);
      const cap = cgEl("div", "pics-cap", PIC_LABELS[kind]);
      if (have) cap.appendChild(cgEl("span", "pics-size", have.size));
      tile.appendChild(cap);
      row.appendChild(tile);
    }
    box.appendChild(row);
    body.appendChild(box);
  }
  body.appendChild(cgEl("div", "pics-hint", "You choose which pictures to use in its Icons row."));
}

