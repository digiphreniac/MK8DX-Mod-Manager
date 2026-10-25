// ---- Vehicles ----
// The three kinds of part - bodies (Karts / Bikes / ATVs), wheels and gliders - each on its own board, each part shown
// as the game's own picture of it, with a name plate along the bottom like Character Select: the part being viewed (its
// card is, or was, open), or whatever tile the mouse is over. The whole screen is sized to fit the window with no
// scrolling (fitVehicleScreen). A part's card is the pop-up openCharacterModal() builds.

// The game's own pictures, {part name: PNG data URI}, from the app's copy of the game files (Api.get_vehicle_icons).
// {} when that copy isn't there yet: the tiles then show the part's name until it is.
let vehicleIcons = {};
let vehicleIconsPending = null;
function loadVehicleIcons() {
  if (Object.keys(vehicleIcons).length) return Promise.resolve();
  if (!vehicleIconsPending) {
    vehicleIconsPending = pywebview.api.get_vehicle_icons()
      .then(r => { vehicleIcons = r || {}; }, () => { vehicleIcons = {}; })
      .finally(() => { vehicleIconsPending = null; });
  }
  return vehicleIconsPending;
}

const VEHICLE_BODY_GROUPS = [
  { type: "kart", label: "Karts", kind: "Kart" },
  { type: "bike", label: "Bikes", kind: "Bike" },
  { type: "atv", label: "ATVs", kind: "ATV" },
];
const VEHICLE_KIND = { wheels: "Wheels", gliders: "Glider" };   // what the plate says a wheel / glider is (bodies: their type)

// What the tiles of the Vehicles screen share (ui.tileGrid); the layout itself is fitVehicleScreen.
const vehicleGrid = ui.tileGrid({
  roots: [document.getElementById("vehicle-sections")], tileSelector: ".char-tile",
  frameHost: document.getElementById("view-vehicles"), plate: document.getElementById("vehicle-name-plate"),
  resolve: resolveVehiclePlate,
  fit: fitVehicleScreen, observe: [document.getElementById("vehicle-layout")],
});

function paintVehicleTile(tile) {
  // the picture the menus will show: the one you chose or a mod brings, else the game's own
  const src = (partReview[tile.dataset.char] && partReview[tile.dataset.char].icon) || vehicleIcons[tile.dataset.char];
  tile.classList.toggle("has-art", !!src);
  const art = tile.querySelector(".vehicle-icon");
  if (!src) { if (art) art.remove(); return; }
  if (art) { if (art.src !== src) art.src = src; return; }
  const img = document.createElement("img");
  img.className = "vehicle-icon";
  img.src = src;
  img.alt = "";
  img.draggable = false;
  tile.prepend(img);
}

// The groups of tiles a section is drawn as: bodies are split into Karts / Bikes / ATVs the way the game's own parts
// menu does; wheels and gliders are one group.
function vehicleGroups(section) {
  if (section.key !== "vehicles") return [{ label: null, kind: VEHICLE_KIND[section.key], items: section.items }];
  return VEHICLE_BODY_GROUPS
    .map(g => ({ label: g.label, kind: g.kind, items: section.items.filter(i => i.type === g.type) }))
    .filter(g => g.items.length > 0);
}

function renderVehiclesView() {
  const container = document.getElementById("vehicle-sections");
  vehicleGrid.reset();   // the tile under the mouse is about to be replaced
  container.replaceChildren();
  const icons = loadVehicleIcons();
  for (const section of state.vehicles) {
    const box = document.createElement("div");
    box.className = "vehicle-section";
    box.dataset.section = section.key;
    const withMods = section.items.filter(i => i.units.length > 0).length;
    const heading = document.createElement("div");
    heading.className = "vehicle-section-heading";
    heading.appendChild(document.createTextNode(section.label));
    const summary = document.createElement("span");
    summary.className = "vehicle-section-summary";
    summary.textContent = `${withMods}/${section.items.length} with mods`;
    heading.appendChild(summary);
    box.appendChild(heading);

    const buildItemTile = (item, kind) => {
      const { tile, checkedUnits } = buildTile(
        item.name, item.units, () => { selectedVehicle = item.name; markActiveVehicle(); openCharacterModal(item.name); }, item.gb_attempted,
        { overlayCount: true, hideBadge: true }
      );
      tile.dataset.kind = kind;
      const conflictPool = checkedUnits;
      if (conflictPool.length >= 2) {
        conflictCount(conflictPool).then(n => {
          if (n > 0) ui.tile.markConflict(tile, `${n} conflicting file(s) among selected mods`);
        });
      }
      paintVehicleTile(tile);
      return tile;
    };

    for (const group of vehicleGroups(section)) {
      const wrap = document.createElement("div");
      wrap.className = "vehicle-group";
      wrap.dataset.count = group.items.length;
      wrap.dataset.labelled = group.label ? "1" : "";
      if (group.label) {
        const sub = document.createElement("div");
        sub.className = "vehicle-subheading";
        sub.textContent = group.label;
        wrap.appendChild(sub);
      }
      const grid = document.createElement("div");
      grid.className = "vehicle-grid";
      for (const item of group.items) grid.appendChild(buildItemTile(item, group.kind));
      wrap.appendChild(grid);
      box.appendChild(wrap);
    }
    container.appendChild(box);
  }
  fitVehicleScreen();
  markActiveVehicle();
  icons.then(() => { for (const t of document.querySelectorAll("#vehicle-sections .char-tile")) paintVehicleTile(t); });
  applyPartMarkers();   // (from what was last known; the fresh answer follows)
  refreshPartReview();
}

// What each part with ticked mods still needs (Api.get_part_tile_view -> partReview): the small marker on its tile (amber =
// its name and/or picture still needs a look, green tick = done; nothing for a part with nothing to check), the picture and
// name the menus will show, the "N to finish" on the step bar, and what the "aren't finished" prompt lists. `now` skips the
// short wait that lets the tick which caused a re-render reach the disk.
let partReviewTimer = null, partReviewToken = 0;
function refreshPartReview(now) {
  const token = ++partReviewToken;
  clearTimeout(partReviewTimer);
  const run = async () => {
    const names = state.vehicles.flatMap(sec => sec.items).filter(i => i.units.some(u => state.checked[u])).map(i => i.name);
    let view = {};
    if (names.length) {
      try { view = await pywebview.api.get_part_tile_view(names) || {}; } catch (e) { return; }
    }
    if (token !== partReviewToken) return;   // (a newer render is waiting for its own answer)
    partReview = view;
    applyPartMarkers();
    try { if (flow.status) { renderStepBar(); renderNextButton(); } } catch (e) { /* (the flow bar isn't up yet) */ }
  };
  if (now) return run();
  partReviewTimer = setTimeout(run, 400);
}
function markPartTiles() { refreshPartReview(true); }   // (after a step of a part's card was settled)
function applyPartMarkers() {
  for (const tile of document.querySelectorAll("#vehicle-sections .char-tile")) {
    tile.querySelectorAll(".tile-review-mark").forEach(e => e.remove());
    paintVehicleTile(tile);
    const r = partReview[tile.dataset.char];
    if (!r || !r.applicable) continue;
    const mark = document.createElement("div");
    mark.className = "tile-review-mark " + (r.finished ? "done" : "todo");
    mark.title = r.finished ? "Completed" : "Mod selected - open it to finish its name and picture";
    if (r.finished) mark.textContent = "\u2713";
    tile.appendChild(mark);
  }
  updateVehicleNameBar();
}

// Opens a part's card on the Vehicles screen: the part selected, its card up.
async function openPartCard(partName) {
  if (!findVehicleItem(partName)) return;
  switchView("vehicles");
  selectedVehicle = partName;
  renderVehiclesView();
  openCharacterModal(partName);
}

// ---- the viewed part ----
// A part's card being open (from any tile, link or list) makes that part the viewed one; it stays viewed after the card
// closes, until another is opened - the yellow corner brackets and the plate follow it.
function markActiveVehicle() {
  if (openCharacter !== null && findVehicleItem(openCharacter)) selectedVehicle = openCharacter;
  vehicleGrid.markActive(selectedVehicle);
  updateVehicleNameBar();
}

// ---- the name plate ----
// While the mouse is over a tile the plate shows THAT part (as the game's select screens do as the cursor moves);
// otherwise the viewed one. The kind of part follows, small and dim.
function resolveVehiclePlate(hover) {
  const el = hover || vehicleGrid.active();
  if (!el) return null;
  const shown = partReview[el.dataset.char] && partReview[el.dataset.char].shown;   // a modded name: the game's own follows, small and dim
  return { main: shown || el.dataset.char, dim: shown ? el.dataset.char : el.dataset.kind };
}
function updateVehicleNameBar() { vehicleGrid.refresh(); }

// ---- fitting the screen ----
// Everything on the Vehicles screen is sized from the room there is, so nothing scrolls: one tile size --vt (a 200:128
// picture), and for each board the number of tiles per row (--vc). The boards can be arranged three ways -
//   a: [bodies | wheels over gliders]     b: [bodies over (wheels | gliders)]     c: [bodies | wheels | gliders]
// - and it takes the biggest tile size at which one of them fits, then, of the ways to fill the boards at that size, the
// arrangement using the least room. The numbers below are the CSS's own (vehicle-screen.css): a board's padding + border,
// its heading, a sub-heading, the gap between a body group and the next, and between boards.
const VEHICLE_FIT = {
  BOARD: 22, HEAD: 28, SUB: 20, GROUP_GAP: 10, BOARD_GAP: 14,
  RATIO: 128 / 200, GAP_K: 0.08, MIN_GAP: 4,
  MIN_T: 36, MAX_T: 160, MAX_COLS: 12,
};

// {board key: {minW: its heading's width, groups: [{n: tiles, labelled}]}} - read from the drawn boards, so it follows whatever
// the roster has.
function vehicleBoardShapes() {
  const shapes = {};
  for (const box of document.querySelectorAll("#vehicle-sections .vehicle-section")) {
    shapes[box.dataset.section] = {
      minW: +box.dataset.headW || 0,
      groups: [...box.querySelectorAll(".vehicle-group")].map(g => ({ n: +g.dataset.count, labelled: !!g.dataset.labelled })),
    };
  }
  return shapes;
}

// A board is never narrower than its heading: measure each one (once it is drawn - it can't be while the screen is hidden)
// so the fit can count with it.
function measureVehicleHeadings() {
  const container = document.getElementById("vehicle-sections");
  for (const box of container.querySelectorAll(".vehicle-section")) {
    if (box.dataset.headW) continue;
    const probe = box.querySelector(".vehicle-section-heading").cloneNode(true);
    probe.classList.add("probe");
    container.appendChild(probe);
    const w = Math.ceil(probe.offsetWidth);
    probe.remove();
    if (!w) return;   // (not laid out yet)
    box.dataset.headW = w + VEHICLE_FIT.BOARD;
    box.style.minWidth = box.dataset.headW + "px";
  }
}

function fitVehicleScreen() {
  const layout = document.getElementById("vehicle-layout");
  const container = document.getElementById("vehicle-sections");
  if (!layout || !layout.clientWidth || !layout.clientHeight) return;
  measureVehicleHeadings();
  const shapes = vehicleBoardShapes();
  const bodies = shapes.vehicles, wheels = shapes.wheels, gliders = shapes.gliders;
  if (!bodies || !wheels || !gliders) return;
  const F = VEHICLE_FIT;
  const W = layout.clientWidth, H = layout.clientHeight;

  // per tile size: every board's width and height at each column count
  const boardAt = ({ groups, minW }, t, g, th) => {
    const out = [];
    for (let c = 1; c <= F.MAX_COLS; c++) {
      let h = F.BOARD + F.HEAD;
      groups.forEach((gr, i) => {
        const rows = Math.ceil(gr.n / c);
        h += (gr.labelled ? F.SUB : 0) + rows * th + (rows - 1) * g + (i ? F.GROUP_GAP : 0);
      });
      out.push({ c, w: Math.max(minW, F.BOARD + c * t + (c - 1) * g), h });
    }
    return out;
  };

  let best = null;
  for (let t = F.MAX_T; t >= F.MIN_T && !best; t--) {
    const g = Math.max(F.MIN_GAP, Math.round(t * F.GAP_K));
    const th = Math.round(t * F.RATIO);
    const B = boardAt(bodies, t, g, th), T = boardAt(wheels, t, g, th), G = boardAt(gliders, t, g, th);
    const consider = (arr, w, h, cols) => {
      if (w > W || h > H) return;
      if (!best || w * h < best.area) best = { arr, t, g, th, cols, area: w * h };
    };
    for (const b of B) {
      for (const r of T) {   // (wheels and gliders share a column count in a: they stack)
        const s = G[r.c - 1];
        consider("a", b.w + F.BOARD_GAP + r.w, Math.max(b.h, r.h + F.BOARD_GAP + s.h), { vehicles: b.c, wheels: r.c, gliders: r.c });
      }
      for (const r of T) for (const s of G) {
        consider("b", Math.max(b.w, r.w + F.BOARD_GAP + s.w), b.h + F.BOARD_GAP + Math.max(r.h, s.h), { vehicles: b.c, wheels: r.c, gliders: s.c });
        consider("c", b.w + r.w + s.w + 2 * F.BOARD_GAP, Math.max(b.h, r.h, s.h), { vehicles: b.c, wheels: r.c, gliders: s.c });
      }
    }
  }
  if (!best) {   // too small for anything: the smallest tiles, and the view scrolls as a last resort
    const t = F.MIN_T;
    best = { arr: "a", t, g: F.MIN_GAP, th: Math.round(t * F.RATIO), cols: { vehicles: 8, wheels: 6, gliders: 6 } };
  }
  container.className = "arr-" + best.arr;
  container.style.setProperty("--vt", best.t + "px");
  container.style.setProperty("--vh", best.th + "px");
  container.style.setProperty("--vg", best.g + "px");
  for (const box of container.querySelectorAll(".vehicle-section")) box.style.setProperty("--vc", best.cols[box.dataset.section]);
}
