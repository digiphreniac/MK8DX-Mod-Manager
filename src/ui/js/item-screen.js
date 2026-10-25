// ---- Items ----
// Every item (Banana, Green Shell, Super Horn ...) as the game's own picture of it, on a board - laid out like Character Select:
// the grid on the left and, on a wide window, the picked item's card docked on the right (on a small one the card is the
// pop-up openCharacterModal() builds), with a name plate along the bottom: the item being viewed, or whatever tile the mouse is
// over. The grid is sized to fit the room there is (fitItemGrid), so nothing scrolls.

// The game's own pictures, {item name: PNG data URI}, from the app's copy of the game files (Api.get_item_icons).
// {} when that copy isn't there yet: the tiles then show the item's name until it is. An item with no picture in the game (the
// Item Box, the Rupee, the Bell) keeps its name either way.
let itemIcons = {};
let itemIconsPending = null;
function loadItemIcons() {
  if (Object.keys(itemIcons).length) return Promise.resolve();
  if (!itemIconsPending) {
    itemIconsPending = pywebview.api.get_item_icons()
      .then(r => { itemIcons = r || {}; }, () => { itemIcons = {}; })
      .finally(() => { itemIconsPending = null; });
  }
  return itemIconsPending;
}

let itemDockedKey = null;   // the item the docked card shows (the pop-up's own is `openCharacter`)
let lastItemKey = null;     // the last item viewed: what the card comes back to

const itemHover = makeHoverFrame(document.getElementById("item-grid-col"), [document.getElementById("item-grid")], ".char-tile");

function paintItemTile(tile) {
  const src = itemIcons[tile.dataset.char];
  tile.classList.toggle("has-art", !!src);
  const art = tile.querySelector(".item-icon");
  if (!src) { if (art) art.remove(); return; }
  if (art) { if (art.src !== src) art.src = src; return; }
  const img = document.createElement("img");
  img.className = "item-icon";
  img.src = src;
  img.alt = "";
  img.draggable = false;
  tile.prepend(img);
}

function renderItemsView() {
  const grid = document.getElementById("item-grid");
  itemHover.hide();   // the tile under the mouse is about to be replaced
  itemHoverEl = null;
  grid.replaceChildren();
  if (!state.items.length) return;
  const icons = loadItemIcons();
  for (const item of state.items) {
    const { tile, checkedUnits } = buildTile(
      item.name, item.units, () => { selectedItem = item.name; markActiveItem(); openCharacterModal(item.name); }, item.gb_attempted,
      { overlayCount: true, hideBadge: true }
    );
    tile.dataset.label = itemLabel(item.name);
    tile.querySelector(".char-name").textContent = tile.dataset.label;
    if (item.catch_all) tile.classList.add("catch-all");
    if (checkedUnits.length >= 2) {
      conflictCount(checkedUnits).then(n => {
        if (n > 0) ui.tile.markConflict(tile, `${n} conflicting file(s) among selected mods`);
      });
    }
    paintItemTile(tile);
    grid.appendChild(tile);
  }
  fitItemGrid();
  markActiveItem();
  icons.then(() => { for (const t of grid.querySelectorAll(".char-tile")) paintItemTile(t); });
  if (viewMode === "items") ensureItemSelection();
}

// Opens an item's card on the Items screen: the item selected, its card up (docked on a wide window, else a pop-up).
async function openItemCard(name) {
  if (!isItemName(name)) return;
  if (viewMode !== "items") switchView("items");
  selectedItem = name;
  renderItemsView();
  openCharacterModal(name);
}

// ---- the viewed item ----
// An item's card being open (from any tile, link or list) makes that item the viewed one; it stays viewed after the card
// closes, until another is opened - the yellow corner brackets and the plate follow it.
function markActiveItem() {
  if (itemDockedKey !== null) selectedItem = itemDockedKey;
  else if (openCharacter !== null && isItemName(openCharacter)) selectedItem = openCharacter;
  for (const t of document.querySelectorAll("#item-grid .char-tile")) t.classList.toggle("active", t.dataset.char === selectedItem);
  updateItemNameBar();
}

// ---- the name plate ----
// While the mouse is over a tile the plate shows THAT item (as the game's select screens do as the cursor moves); otherwise
// the viewed one. How its mods stand follows, small and dim.
let itemHoverEl = null;
function updateItemNameBar() {
  const plate = document.getElementById("item-name-plate");
  const el = itemHoverEl && itemHoverEl.isConnected ? itemHoverEl : document.querySelector("#item-grid .char-tile.active");
  plate.replaceChildren();
  if (!el) { plate.classList.remove("show"); return; }
  plate.append(el.dataset.label || el.dataset.char);
  const item = findItem(el.dataset.char);
  if (item) {
    const total = item.units.length, ticked = item.units.filter(k => state.checked[k]).length;
    const dim = total === 0 ? "no mods yet" : ticked === 0 ? `${total} mod${total === 1 ? "" : "s"}, none in use` : `${ticked} of ${total} mod${total === 1 ? "" : "s"} in use`;
    const base = document.createElement("span");
    base.className = "np-base";
    base.textContent = `(${dim})`;
    plate.appendChild(base);
  }
  plate.classList.add("show");
}
document.getElementById("item-grid").addEventListener("mouseover", (e) => {
  const tile = e.target.closest(".char-tile");
  if (tile && tile !== itemHoverEl) { itemHoverEl = tile; updateItemNameBar(); }
});
document.getElementById("item-grid").addEventListener("mouseleave", () => { itemHoverEl = null; updateItemNameBar(); });

// ---- the docked card ----
// Wide window: the card beside the grid, and always an item in it (the one last viewed, else the first with a mod, else the
// first). Small window: the card is a pop-up and nothing is docked.
function ensureItemSelection() {
  if (!dockedLayout() || viewMode !== "items" || itemDockedKey !== null || !state.items.length) return;
  const known = (n) => n && isItemName(n) ? n : null;
  const first = state.items.find(i => i.units.some(k => state.checked[k])) || state.items[0];
  openCharacterModal(known(lastItemKey) || known(selectedItem) || first.name);
}

// The card goes away (the window became too small for it, or Items was left).
function closeItemDetail() {
  itemDockedKey = null;
  document.getElementById("item-detail-title").textContent = "";
  document.getElementById("item-detail-body").innerHTML = "";
  markActiveItem();
}

// Called at the start of building a docked card (see beginDetail): where to build it.
function beginItemDetail(key) {
  characterModal.close();   // a pop-up left open gives way to the docked card
  openCharacter = null;
  itemDockedKey = key;
  if (isItemName(key)) lastItemKey = key;
  applyItemLayout();
  return { title: document.getElementById("item-detail-title"), body: document.getElementById("item-detail-body") };
}

function applyItemLayout() {
  const docked = dockedLayout();
  document.getElementById("item-layout").classList.toggle("docked", docked);
  document.getElementById("view-items").classList.toggle("docked", docked);
  fitItemGrid();
}

// Called by switchView when Items is shown.
function showItemsView() {
  applyItemLayout();
  if (dockedLayout()) ensureItemSelection();
  else if (itemDockedKey !== null) closeItemDetail();
  markActiveItem();
}

// The window was resized across the threshold: a pop-up that is open for an item moves into the card (and the card always has
// an item); shrinking just takes the card away - nothing pops up by itself.
let itemResizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(itemResizeTimer);
  itemResizeTimer = setTimeout(() => {
    if (viewMode !== "items") return;
    const was = document.getElementById("item-layout").classList.contains("docked");
    applyItemLayout();
    const now = dockedLayout();
    if (was === now) return;
    if (now && openCharacter !== null && isItemName(openCharacter)) {   // pop-up -> docked
      const n = openCharacter;
      closeModal();
      openCharacterModal(n);
    } else if (now) {
      ensureItemSelection();
    } else if (itemDockedKey !== null) {
      closeItemDetail();
    }
  }, 150);
});

// ---- fitting the grid ----
// The biggest square tile at which the whole grid fits its board - by width or by height, whichever runs out first - over
// the number of columns that gives the biggest one (the tile count isn't a multiple of anything the game has, so unlike
// Character Select's fixed 8 columns this takes whatever shape suits the room). The board is the left 55% of the screen when
// the card is docked, the whole width otherwise. Gaps and type follow the tile (item-screen.css).
const ITEM_FIT = { GAP_K: 0.12, MIN_T: 40, MAX_T: 150, PREFER_COLS: 6 };
function fitItemGrid() {
  const layout = document.getElementById("item-layout");
  const col = document.getElementById("item-grid-col");
  const grid = document.getElementById("item-grid");
  if (!layout.clientWidth || !layout.clientHeight) return;
  const n = grid.querySelectorAll(".char-tile").length;
  if (!n) return;
  const cs = getComputedStyle(col);
  const px = (v) => parseFloat(v) || 0;
  const frameX = px(cs.paddingLeft) + px(cs.paddingRight) + px(cs.borderLeftWidth) + px(cs.borderRightWidth);
  const frameY = px(cs.paddingTop) + px(cs.paddingBottom) + px(cs.borderTopWidth) + px(cs.borderBottomWidth);
  const boardW = dockedLayout() ? layout.clientWidth * 0.55 - 8 : layout.clientWidth;
  const W = boardW - frameX, H = layout.clientHeight - frameY;
  const K = ITEM_FIT.GAP_K;
  let best = null;
  for (let c = 1; c <= n; c++) {
    const rows = Math.ceil(n / c);
    const t = Math.min(ITEM_FIT.MAX_T, Math.floor(Math.min(W / (c + (c - 1) * K), H / (rows + (rows - 1) * K))));
    if (!best || t > best.t || (t === best.t && Math.abs(c - ITEM_FIT.PREFER_COLS) < Math.abs(best.c - ITEM_FIT.PREFER_COLS))) best = { c, t };
  }
  const t = Math.max(ITEM_FIT.MIN_T, best.t);   // (too small for anything: the smallest tiles, and the board scrolls as a last resort)
  grid.style.setProperty("--it", t + "px");
  grid.style.setProperty("--ig", Math.max(4, Math.round(t * K)) + "px");
  grid.style.setProperty("--ic", best.c);
}
new ResizeObserver(fitItemGrid).observe(document.getElementById("item-layout"));

applyItemLayout();
