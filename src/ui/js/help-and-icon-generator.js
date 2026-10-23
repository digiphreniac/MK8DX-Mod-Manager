function openHelpModal() {
  document.getElementById("help-modal-backdrop").hidden = false;
}
function closeHelpModal() {
  document.getElementById("help-modal-backdrop").hidden = true;
}
document.getElementById("help-link").addEventListener("click", openHelpModal);
document.getElementById("support-link").addEventListener("click", () => { pywebview.api.open_external_url("https://buymeacoffee.com/digiphreniac"); });
document.getElementById("btn-help-modal-close").addEventListener("click", closeHelpModal);
document.getElementById("help-modal-backdrop").addEventListener("click", (e) => {
  if (e.target.id === "help-modal-backdrop") closeHelpModal();
});
document.getElementById("help-modal-body").addEventListener("click", (e) => {
  const link = e.target.closest(".help-ext-link");
  if (link) pywebview.api.open_help_link(link.dataset.url);
});

// --- Course icon generator: pick one of a mod's own GameBanana screenshots,
// position a fixed-304x256-aspect crop box over it, and hand the crop off
// to Api.generate_course_icon() (see that method + bntx_encode.py). ---
// Matches the visible-content window Api.generate_course_icon() actually
// composites into (288x162, exactly 16:9) - not the full 304x256 texture,
// which real CoursePict files leave bordered (see the Help page and
// docs/course-select.md ("Course-select icon preview & generation") for how that
// was measured). Cropping to this ratio means a typical 16:9 screenshot
// needs no letterboxing at all - the app adds the matching border after.
const ICON_GEN_COURSE_ASPECT = 288 / 162;
// A vehicle part's picture in the parts menu is 200x128 in the game.
const ICON_GEN_PART_ASPECT = 200 / 128;
let iconGenAspect = ICON_GEN_COURSE_ASPECT;
let iconGenMode = "course";       // "course" (select-screen picture) | "character" (menu icons) | "part" (a vehicle part's picture)
let iconGenOnDone = null;
let iconGenKinds = null;          // character mode: only these icons ("Chara" / "MapChara" / "edChara"), else all three
let iconGenColour = null;         // ...and only this colour (0-based) of a colour-variant character, else all of them
let iconGenCourseName = null;
let iconGenSelectedShot = null;
let iconGenNaturalWidth = 0;
let iconGenBoxState = null; // {left, top, width, height, dispW, dispH} - all in displayed (CSS) pixels

let iconGenIconsToken = 0;
// "Icons from the mod": the pictures the mods provide for this character, shown ahead of the screenshots. Picking
// one uses it as it is (it is an icon already - no cropping).
async function loadIconGenModIcons(name) {
  const box = document.getElementById("icon-gen-mod-icons-box");
  const list = document.getElementById("icon-gen-mod-icons");
  const otherList = document.getElementById("icon-gen-mod-icons-other");
  const err = document.getElementById("icon-gen-mod-error");
  box.hidden = true;
  err.hidden = true;
  list.replaceChildren();
  otherList.replaceChildren();
  document.getElementById("icon-gen-other-title").hidden = true;
  document.getElementById("icon-gen-shots-title").hidden = true;
  if (iconGenMode !== "character") return;
  const token = ++iconGenIconsToken;
  let pics = [];
  try { pics = await pywebview.api.get_mod_icon_pictures(name, iconGenColour); } catch (e) { pics = []; }
  if (token !== iconGenIconsToken || !pics.length) return;
  for (const p of pics) {
    const label = (ML_KINDS.find(k => k[0] === p.kind) || [0, p.kind])[1];
    const tile = cgEl("button", "icon-gen-icon");
    tile.type = "button";
    tile.title = p.for ? `Use this ${label} picture from ${p.from} (it is named for ${p.for})` : `Use this ${label} picture from ${p.from}`;
    const imgBox = cgEl("div", "icon-gen-icon-img");
    const im = document.createElement("img");
    im.src = p.preview;
    im.alt = "";
    imgBox.appendChild(im);
    tile.appendChild(imgBox);
    const cap = cgEl("span", "icon-gen-icon-cap");
    cap.appendChild(cgEl("b", null, label + (p.colour != null ? ` \u00b7 colour ${p.colour + 1}` : "")));
    cap.appendChild(document.createTextNode(p.for ? `${p.from} \u00b7 for ${p.for}` : p.from));
    tile.appendChild(cap);
    tile.addEventListener("click", async () => {
      tile.disabled = true;
      err.hidden = true;
      const r = await pywebview.api.use_mod_icon_picture(name, p.key, iconGenKinds, iconGenColour);
      if (!r.success) { tile.disabled = false; err.textContent = r.error; err.hidden = false; return; }
      closeIconGenModal();
      refreshBehindModal();
      if (iconGenOnDone) iconGenOnDone();
    });
    (p.for ? otherList : list).appendChild(tile);
  }
  document.getElementById("icon-gen-other-title").hidden = !otherList.childNodes.length;
  box.hidden = false;
  document.getElementById("icon-gen-shots-title").hidden = false;
}

function openIconGenModal(courseName, screenshots, mode, onDone, opts) {
  iconGenMode = mode || "course";
  iconGenOnDone = onDone || null;
  iconGenKinds = (opts && opts.kinds) || null;
  iconGenColour = opts && opts.colour != null ? opts.colour : null;
  const one = iconGenMode === "character" && opts && opts.label;   // a picture for one icon only
  iconGenAspect = iconGenMode === "character" ? 1 : iconGenMode === "part" ? ICON_GEN_PART_ASPECT : ICON_GEN_COURSE_ASPECT;
  document.getElementById("icon-gen-title").textContent = iconGenMode === "character"
    ? (one ? `Change the ${opts.label} icon for ${courseName}` : "Icons for " + courseName)
    : iconGenMode === "part" ? "Picture for " + courseName : "Generate Course Icon";
  document.getElementById("icon-gen-pick-hint").textContent = iconGenMode === "character"
    ? (one ? `Pick a picture for ${courseName}'s ${opts.label} icon: one of the mod's own icons (used as they are), or a GameBanana screenshot or a file from your computer (you'll choose which part of it shows next).`
           : "Pick a picture for this character's menu icons: one of the mod's own icons (used as they are), or a GameBanana screenshot or a file from your computer (you'll choose which part of it shows next).")
    : iconGenMode === "part" ? `Pick a picture for ${courseName} in the parts menu: a GameBanana screenshot or a file from your computer (you'll choose which part of it shows next). It is shown in the game 200 pixels wide - a picture of the part on a plain or see-through background works best.`
    : "Pick one of this mod's own GameBanana screenshots to use as the course-select picture. Nothing this mod doesn't already show off gets used.";
  document.getElementById("icon-gen-crop-hint").textContent = iconGenMode === "character"
    ? (one ? `Drag the square to choose what shows - it becomes the ${opts.label} icon only.`
           : "Drag the square to choose what shows - it becomes the character-select, map and results icons.")
    : iconGenMode === "part" ? "Drag the box to choose what shows - it becomes the part's picture in the parts menu."
    : "Drag the box to choose what shows - this exact area becomes the in-game picture.";
  iconGenCourseName = courseName;
  iconGenSelectedShot = null;
  iconGenBoxState = null;
  document.getElementById("icon-gen-step-pick").hidden = false;
  document.getElementById("icon-gen-step-crop").hidden = true;
  document.getElementById("icon-gen-error").hidden = true;
  const grid = document.getElementById("icon-gen-screenshot-grid");
  grid.innerHTML = "";
  for (const shot of screenshots) {
    const img = document.createElement("img");
    img.src = shot.thumb_url;
    img.alt = "";
    img.addEventListener("click", () => selectIconGenScreenshot(shot));
    grid.appendChild(img);
  }
  if (iconGenMode === "character" || iconGenMode === "part") {
    const up = cgEl("label", "ml-upload", "Choose a picture from your computer...");
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.hidden = true;
    input.addEventListener("change", () => {
      const f = input.files && input.files[0];
      if (!f) return;
      const reader = new FileReader();
      reader.onload = () => selectIconGenScreenshot({ thumb_url: reader.result, full_url: reader.result, local: true });
      reader.readAsDataURL(f);
    });
    up.appendChild(input);
    grid.appendChild(up);
  }
  document.getElementById("icon-gen-modal-backdrop").hidden = false;
  loadIconGenModIcons(courseName);
}

function closeIconGenModal() {
  document.getElementById("icon-gen-modal-backdrop").hidden = true;
}

function selectIconGenScreenshot(shot) {
  iconGenSelectedShot = shot;
  document.getElementById("icon-gen-step-pick").hidden = true;
  document.getElementById("icon-gen-step-crop").hidden = false;
  const img = document.getElementById("icon-gen-crop-image");
  img.onload = () => {
    iconGenNaturalWidth = img.naturalWidth;
    requestAnimationFrame(initIconGenCropBox);
  };
  img.src = shot.full_url;
}

function initIconGenCropBox() {
  const img = document.getElementById("icon-gen-crop-image");
  const dispW = img.clientWidth;
  const dispH = img.clientHeight;
  if (!dispW || !dispH) return;
  const imgAspect = dispW / dispH;
  let boxW, boxH;
  if (imgAspect > iconGenAspect) {
    boxH = dispH;
    boxW = boxH * iconGenAspect;
  } else {
    boxW = dispW;
    boxH = boxW / iconGenAspect;
  }
  iconGenBoxState = {
    left: (dispW - boxW) / 2,
    top: (dispH - boxH) / 2,
    width: boxW,
    height: boxH,
    dispW, dispH,
  };
  renderIconGenCropBox();
}

function renderIconGenCropBox() {
  const box = document.getElementById("icon-gen-crop-box");
  const s = iconGenBoxState;
  box.style.left = s.left + "px";
  box.style.top = s.top + "px";
  box.style.width = s.width + "px";
  box.style.height = s.height + "px";
}

(function setupIconGenCropDrag() {
  const box = document.getElementById("icon-gen-crop-box");
  let dragging = false;
  let startX = 0, startY = 0, startLeft = 0, startTop = 0;
  box.addEventListener("mousedown", (e) => {
    if (!iconGenBoxState) return;
    dragging = true;
    box.classList.add("dragging");
    startX = e.clientX;
    startY = e.clientY;
    startLeft = iconGenBoxState.left;
    startTop = iconGenBoxState.top;
    e.preventDefault();
  });
  document.addEventListener("mousemove", (e) => {
    if (!dragging || !iconGenBoxState) return;
    const s = iconGenBoxState;
    let newLeft = startLeft + (e.clientX - startX);
    let newTop = startTop + (e.clientY - startY);
    newLeft = Math.max(0, Math.min(s.dispW - s.width, newLeft));
    newTop = Math.max(0, Math.min(s.dispH - s.height, newTop));
    s.left = newLeft;
    s.top = newTop;
    renderIconGenCropBox();
  });
  document.addEventListener("mouseup", () => {
    dragging = false;
    box.classList.remove("dragging");
  });
})();

document.getElementById("btn-icon-gen-back").addEventListener("click", () => {
  document.getElementById("icon-gen-step-crop").hidden = true;
  document.getElementById("icon-gen-step-pick").hidden = false;
});

document.getElementById("btn-icon-gen-confirm").addEventListener("click", async () => {
  if (!iconGenBoxState || !iconGenSelectedShot) return;
  const s = iconGenBoxState;
  const scale = iconGenNaturalWidth / s.dispW; // image is never stretched (width:100%, height:auto), so this scale applies to both axes
  const cropX = Math.round(s.left * scale);
  const cropY = Math.round(s.top * scale);
  const cropW = Math.round(s.width * scale);
  const cropH = Math.round(s.height * scale);

  const confirmBtn = document.getElementById("btn-icon-gen-confirm");
  const errEl = document.getElementById("icon-gen-error");
  errEl.hidden = true;
  confirmBtn.disabled = true;
  confirmBtn.textContent = "Generating…";
  let result;
  if (iconGenMode === "part") {
    if (iconGenSelectedShot.local) {
      const img = document.getElementById("icon-gen-crop-image");
      const canvas = document.createElement("canvas");
      canvas.width = 400;
      canvas.height = 256;
      canvas.getContext("2d").drawImage(img, cropX, cropY, cropW, cropH, 0, 0, 400, 256);
      result = await pywebview.api.set_part_icon_from_data(iconGenCourseName, canvas.toDataURL("image/png"));
    } else {
      result = await pywebview.api.set_part_icon_from_url(iconGenCourseName, iconGenSelectedShot.full_url, cropX, cropY, cropW, cropH);
    }
  } else if (iconGenMode === "character") {
    if (iconGenSelectedShot.local) {
      // a picture from the user's own computer: crop it here and send the result
      const img = document.getElementById("icon-gen-crop-image");
      const canvas = document.createElement("canvas");
      canvas.width = 256;
      canvas.height = 256;
      canvas.getContext("2d").drawImage(img, cropX, cropY, cropW, cropH, 0, 0, 256, 256);
      result = await pywebview.api.set_character_icons_from_data(iconGenCourseName, canvas.toDataURL("image/png"), iconGenKinds, iconGenColour);
    } else {
      result = await pywebview.api.set_character_icons_from_url(iconGenCourseName, iconGenSelectedShot.full_url, cropX, cropY, cropW, cropH, iconGenKinds, iconGenColour);
    }
  } else {
    result = await pywebview.api.generate_course_icon(
      iconGenCourseName, iconGenSelectedShot.full_url, cropX, cropY, cropW, cropH,
    );
  }
  confirmBtn.disabled = false;
  confirmBtn.textContent = "Use this crop";
  if (!result.success) {
    errEl.textContent = result.error;
    errEl.hidden = false;
    return;
  }
  closeIconGenModal();
  refreshBehindModal();
  if (iconGenOnDone) iconGenOnDone();
});

document.getElementById("btn-icon-gen-modal-close").addEventListener("click", closeIconGenModal);
document.getElementById("icon-gen-modal-backdrop").addEventListener("click", (e) => {
  if (e.target.id === "icon-gen-modal-backdrop") closeIconGenModal();
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (!document.getElementById("icon-gen-modal-backdrop").hidden) {
    closeIconGenModal();
    return;
  }
  if (!document.getElementById("help-modal-backdrop").hidden) {
    closeHelpModal();
    return;
  }
  const shared = document.getElementById("modal-backdrop");
  if (!shared.hidden && shared.classList.contains("above-settings")) {
    closeModal();  // Clear All / Change directory, drawn above Settings
    return;
  }
  if (!document.getElementById("settings-modal-backdrop").hidden) {
    closeSettingsModal();
    return;
  }
  if (!document.getElementById("add-mod-modal-backdrop").hidden) {
    closeAddModModal();
    return;
  }
  if (!document.getElementById("gb-detail-modal-backdrop").hidden) {
    closeGbDetailModal();
    return;
  }
  if (!document.getElementById("gb-browse-modal-backdrop").hidden) {
    closeGbBrowseModal();
    return;
  }
  if (openCharacter !== null) closeModal();
});

