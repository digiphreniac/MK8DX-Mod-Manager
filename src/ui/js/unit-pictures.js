// ---- The menu pictures a mod brings (Select screen, Mini map, Results): the tag on a character mod row and its window.
const PIC_LABELS = { Chara: "Select screen", MapChara: "Mini map", edChara: "Results" };
const PIC_ORDER = ["Chara", "MapChara", "edChara"];
const unitPics = {};       // unit key -> what Api.get_unit_pictures() said about it
function pictureSvg() {
  return ui.icon("photo", { size: null });
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
  const modal = ui.modal({ variant: "card", class: "pics-card", title: "Menu pictures", footer: true, destroyOnClose: true });
  const card = modal.body;
  card.appendChild(ui.el("div", "pics-sub", modLabel));
  const body = ui.el("div", "pics-body");
  body.appendChild(ui.el("div", "voice-empty", "Looking at the pictures\u2026"));
  card.appendChild(body);
  const closeBtn = button("Close", "primary", () => modal.close());
  modal.footer.appendChild(closeBtn);
  modal.open();
  closeBtn.focus();
  let r;
  try { r = await pywebview.api.get_unit_picture_sets(unitKey, siblings); } catch (e) { r = null; }
  if (!modal.isOpen) return;
  body.replaceChildren();
  const sets = (r && r.sets) || [];
  if (!sets.length) { body.appendChild(ui.el("div", "voice-empty", "No menu pictures could be read from this mod.")); return; }
  for (const st of sets) {
    const box = ui.el("div", "pics-set");
    const title = ui.el("div", "pics-title", st.label);
    if (st.colours > 1) title.appendChild(ui.el("span", "pics-note", `${st.colours} colours - the first is shown`));
    box.appendChild(title);
    if (st.for) box.appendChild(ui.el("div", "pics-warn", `These pictures are named for ${st.for}, not for this character. You can still use them from its Icons row.`));
    const row = ui.el("div", "pics-row");
    for (const kind of PIC_ORDER) {
      const tile = ui.el("div", "pics-tile");
      const have = st.kinds[kind];
      const frame = ui.el("div", "pics-img" + (have ? "" : " none"));
      if (have) {
        const img = document.createElement("img");
        img.src = have.preview;
        img.alt = PIC_LABELS[kind];
        frame.appendChild(img);
      } else {
        frame.textContent = kind !== "Chara" && st.kinds.Chara ? "Not included - can be made from the Select screen" : "Not included";
      }
      tile.appendChild(frame);
      const cap = ui.el("div", "pics-cap", PIC_LABELS[kind]);
      if (have) cap.appendChild(ui.el("span", "pics-size", have.size));
      tile.appendChild(cap);
      row.appendChild(tile);
    }
    box.appendChild(row);
    body.appendChild(box);
  }
  body.appendChild(ui.hint("You choose which pictures to use in its Icons row.", { class: "pics-hint", size: "md" }));
}

