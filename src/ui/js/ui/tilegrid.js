// ===== UI components: TileGrid (what the screens that show tiles do the same) =====
//   const grid = ui.tileGrid({
//     roots,           the elements that hold the tiles (the grid itself, a strip of courses ...)
//     tileSelector,    what counts as a tile inside them (".char-tile")
//     keyAttr,         the data- attribute that names a tile ("char": data-char); used by markActive
//     frameHost,       a positioned element that is not rebuilt: the yellow frame that follows the tile under the mouse lives in it
//     plate,           the name plate: it shows what resolve() says about the tile under the mouse, or else about the selected one
//     resolve(hover),  -> { main, dim } | null. `hover` is the tile under the mouse (null when none); `dim` is the small grey part in
//                      brackets after the name. The screen decides what the plate says; the grid decides when to ask.
//     fit(), observe   fit() is called now and then whenever one of the `observe` elements changes size (sizing the tiles to the room)
//   })  ->  { hover(), refresh(), markActive(key, selector), active(selector), reset(), hideFrame(), fit() }
// The layout (which tiles, in what rows, how big) stays with each screen: characters are 8 fixed columns, items look for the best
// column count, vehicles have three arrangements, courses have cups on pages. Only what they share is here.
ui.tileGrid = function (spec) {
  const roots = spec.roots;
  const keyAttr = spec.keyAttr || "char";
  let hoverEl = null;

  // the frame: a box that slides to the tile under the mouse
  let frame = null, shown = false;
  const host = spec.frameHost;
  if (host) {
    frame = ui.el("div", "hover-frame");
    host.append(frame);
  }
  function hideFrame() {
    if (!frame) return;
    frame.classList.remove("show");
    shown = false;
  }
  function moveFrame(tile) {
    const hr = host.getBoundingClientRect(), tr = tile.getBoundingClientRect();
    const pad = 4;   // same margin as the yellow brackets
    const x = tr.left - hr.left + host.scrollLeft - host.clientLeft - pad;
    const y = tr.top - hr.top + host.scrollTop - host.clientTop - pad;
    if (!shown) frame.style.transition = "none";
    frame.style.transform = `translate(${x}px, ${y}px)`;
    frame.style.width = (tr.width + 2 * pad) + "px";
    frame.style.height = (tr.height + 2 * pad) + "px";
    if (!shown) { void frame.offsetWidth; frame.style.transition = ""; }
    frame.classList.add("show");
    shown = true;
  }

  const hover = () => (hoverEl && hoverEl.isConnected ? hoverEl : null);

  function refresh() {
    const plate = spec.plate;
    if (!plate) return;
    const said = spec.resolve ? spec.resolve(hover()) : null;
    plate.replaceChildren();
    if (!said || !said.main) { plate.classList.remove("show"); return; }
    plate.append(said.main);
    if (said.dim) plate.append(ui.el("span", { class: "np-base", text: `(${said.dim})` }));
    plate.classList.add("show");
  }

  for (const root of roots) {
    root.addEventListener("mouseover", (e) => {
      const tile = e.target.closest(spec.tileSelector);
      if (!tile) return;
      if (frame && root.contains(tile)) moveFrame(tile);
      if (tile !== hoverEl) { hoverEl = tile; refresh(); }
    });
    root.addEventListener("mouseleave", () => { hideFrame(); hoverEl = null; refresh(); });
  }

  const grid = {
    hover,
    refresh,
    hideFrame,
    // the tile under the mouse was just replaced (the grid is being drawn again)
    reset() { hideFrame(); hoverEl = null; },
    // `.active` goes on the tile whose key is `key` (nothing for null); `selector` narrows which tiles are looked at
    markActive(key, selector) {
      for (const root of roots) for (const t of root.querySelectorAll(selector || spec.tileSelector)) t.classList.toggle("active", key != null && t.dataset[keyAttr] === key);
    },
    active(selector) {
      for (const root of roots) {
        const t = root.querySelector((selector || spec.tileSelector) + ".active");
        if (t) return t;
      }
      return null;
    },
    fit() { if (spec.fit) spec.fit(); },
  };
  if (spec.fit) for (const el of spec.observe || []) new ResizeObserver(() => spec.fit()).observe(el);
  return grid;
};

// The biggest square tile at which `n` tiles fit a W x H box, with a gap of K tiles between them: by width or by height, whichever runs
// out first. `cols` fixes the number of columns; without it every number of columns is tried and the one with the biggest tile wins (of
// those, the one nearest `preferCols`). `extraRows` is room for something else under the tiles (a heading).
//   -> { cols, tile (never under minT), fits (false: even the smallest allowed tile does not fit) }
ui.fitTiles = function ({ W, H, n, K, cols, extraRows = 0, minT = 0, maxT = Infinity, preferCols }) {
  let best = null;
  const options = cols ? [cols] : Array.from({ length: Math.max(1, n) }, (_, i) => i + 1);
  for (const c of options) {
    const rows = Math.max(1, Math.ceil(n / c)) + extraRows;
    const t = Math.min(maxT, Math.floor(Math.min(W / (c + (c - 1) * K), H / (rows + (rows - 1) * K))));
    if (!best || t > best.t || (t === best.t && preferCols !== undefined && Math.abs(c - preferCols) < Math.abs(best.c - preferCols))) best = { c, t };
  }
  return { cols: best.c, tile: Math.max(minT, best.t), fits: best.t >= minT };
};
