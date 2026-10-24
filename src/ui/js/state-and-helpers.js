let state = { categories: {}, checked: {}, roster: [], cups: [], settings: {}, simpleCategories: [], vehicles: [], items: [], packLinks: { by_item: {}, by_unit: {} },
  epoch: null,          // names the master folder `checked` was loaded from (get_mods); null until this page has loaded it
  checkedSaved: {},     // the ticks as the backend last had them, so a save sends only what changed since
  notes: {} };   // the user's notes on mods, {unit key: text} (get_mods; see mod-notes.js)

// Ticks are saved as CHANGES - {unit key: on/off} for the units that changed since the last load/save - never as the page's whole
// picture: a page whose picture is empty or out of date (still loading, or the master folder was switched under it) then can't
// replace the folder's ticks with its own. The backend also refuses a save whose epoch isn't the folder's current one, and a page
// that hasn't loaded the ticks yet (epoch null) doesn't save at all. Saves go one at a time, in order.
let checkedSaveChain = Promise.resolve();
const checkedPending = {};   // changes handed to a save that hasn't finished - kept over a reload (loadMods) so they aren't dropped
function saveChecked() {
  const changes = {};
  for (const [k, v] of Object.entries(state.checked)) if (state.checkedSaved[k] !== v) changes[k] = v;
  if (!Object.keys(changes).length) return checkedSaveChain;
  Object.assign(checkedPending, changes);
  checkedSaveChain = checkedSaveChain.then(async () => {
    if (state.epoch == null) return false;
    const ok = await pywebview.api.save_checked(changes, state.epoch);
    if (ok === false) {   // the folder changed under this page: take the folder's ticks instead of writing ours over them
      for (const k of Object.keys(changes)) delete checkedPending[k];
      await loadMods();
      return false;
    }
    for (const [k, v] of Object.entries(changes)) { state.checkedSaved[k] = v; if (checkedPending[k] === v) delete checkedPending[k]; }
    return true;
  }).catch(e => { console.error("saving the selected mods failed", e); diag.banner("tick-save", "Your last selection couldn't be saved, so it may be gone when the app restarts. Select it again. " + diag.describe(e)); return false; });
  return checkedSaveChain;
}
let viewMode = "characters";
let openCharacter = null;
let selectedCup = "Mushroom Cup";
let selectedVehicle = null;  // the vehicle part last opened on the Vehicles screen (its card is, or was, open)
let selectedItem = null;     // the item last opened on the Items screen (its card is, or was, open)
let selectedCourse = null;   // the course picked in the selected cup (Course Select), if any
const DLC_CUP_START = "Golden Dash Cup"; // first Booster Course Pass cup

// "Simple" mod categories - mirrors mod_manager.py's SIMPLE_MOD_CATEGORIES
// (same keys/labels). Each is a single fixed pseudo-item with its own
// plain list screen (see #view-more) rather than a per-character/per-course
// grid, but otherwise reuses the exact same modal/GameBanana-card machinery
// characters and courses already use.
// Category keys of the vehicle-part sections (mirrors mod_manager.py's
// VEHICLE_SECTIONS) - each is its own mods/extracted/<category>/ folder.
const VEHICLE_SECTION_KEYS = ["vehicles", "wheels", "gliders"];
// GameBanana files "Mario Kart 8" (Wii U) mods under a different game id than
// "Mario Kart 8 Deluxe" (Switch) - mods for the former don't load on a Switch.
const MK8DX_GAME_ID = 6507;
// gb_identify_mod's guess_category for a mod that is unmistakably a vehicle
// part (filed directly in GameBanana's Vehicles category) but whose text names
// no particular part.
const isVehicleGuess = (g) => VEHICLE_SECTION_KEYS.includes(g) || g === "vehicle_unsorted";

const SIMPLE_CATEGORIES = [
  // `blurb`: what belongs in it, shown on its tile in the More tab
  { key: "mechanics", label: "Mechanics", blurb: "Gameplay tweaks - a coin cap, CPU difficulty, how the game plays. Most are code patches." },
  { key: "ui", label: "UI", blurb: "Menus, the in-race HUD, loading screens and the minimap." },
  { key: "code_patches", label: "Code patches", blurb: "Patches to the game's program itself. They only work on the exact game version they were made for." },
  { key: "modpacks", label: "Modpacks", blurb: "Big bundles of many mods. A pack is also listed on every card it changes." },
  { key: "battle_courses", label: "Battle courses", blurb: "Custom battle arenas, each replacing one of the game's battle courses." },
];
// Items (mirrors mod_manager.py's ITEMS_*) have their own screen and a per-item roster, loaded from Api.get_items_view() into
// state.items as [{name, internal, units, gb_attempted, catch_all?, label?}]. The last one is the catch-all ("Items", the folder
// everything filed before items had a roster is in), shown as "Other items".
// Where the footer's "Donate" link and the All done page's "Buy me a coffee" row lead.
const SUPPORT_URL = "https://buymeacoffee.com/digiphreniac";
function openSupportPage() { pywebview.api.open_external_url(SUPPORT_URL); }
// The other two ways to help, shown on the All done page (see supportCard() in flow.js). The more likes the GameBanana page has, the
// more people see it. An empty address hides that row, so a missing one never sends anybody anywhere.
const GAMEBANANA_PAGE_URL = "https://gamebanana.com/tools/24624";
const GITHUB_URL = "https://github.com/digiphreniac/MK8DX-Mod-Manager";
// The community server: help, chat, and working on mods together (a row on the All done page's card, and a button in Help).
const DISCORD_URL = "https://discord.gg/mNShnnu8j8";
function openExternal(url) { pywebview.api.open_external_url(url); }
const ITEMS_CATEGORY = "items";
const ITEMS_OTHER = "Items";
const ITEMS_OTHER_LABEL = "Other items";
function findItem(name) { return state.items.find(i => i.name === name) || null; }
function isItemName(name) { return state.items.some(i => i.name === name); }
// what an item is called on screen (only the catch-all differs from its name)
function itemLabel(name) { const it = findItem(name); return it && it.label ? it.label : name; }
function findSimpleCategoryByLabel(name) {
  return SIMPLE_CATEGORIES.find(c => c.label === name) || null;
}

// Vehicle parts (bodies / tires / gliders) - a per-item roster like
// characters, loaded from Api.get_vehicles_view() into state.vehicles as
// [{key, label, items: [{name, type, internal, units, gb_attempted}]}].
// Each section key is also its download/merge category ("vehicles" =
// bodies, "wheels", "gliders"). Part names are unique across sections.
function findVehicleItem(name) {
  for (const section of state.vehicles) {
    const item = section.items.find(i => i.name === name);
    if (item) return { section: section.key, item };
  }
  return null;
}

// One representative emoji per cup, standing in for real cup-icon artwork
// (see .cup-emoji - rendered large, above the cup name, like a mini icon
// rather than inline text). Keyed by roster.json's exact "cup" names.
const CUP_EMOJI = {
  "Mushroom Cup": "\u{1F344}",   // 🍄
  "Flower Cup": "\u{1F338}",     // 🌸
  "Star Cup": "\u{2B50}",        // ⭐
  "Special Cup": "\u{1F451}",    // 👑
  "Shell Cup": "\u{1F422}",      // 🐢
  "Banana Cup": "\u{1F34C}",     // 🍌
  "Leaf Cup": "\u{1F341}",       // 🍁
  "Lightning Cup": "\u{26A1}",   // ⚡
  "Egg Cup": "\u{1F95A}",        // 🥚
  "Triforce Cup": "\u{1F53A}",   // 🔺
  "Crossing Cup": "\u{1F343}",   // 🍃
  "Bell Cup": "\u{1F514}",       // 🔔
  "Golden Dash Cup": "\u{1F3C6}",// 🏆
  "Lucky Cat Cup": "\u{1F431}",  // 🐱
  "Turnip Cup": "\u{1FADC}",     // 🫜
  "Propeller Cup": "\u{1F6E9}\u{FE0F}", // 🛩️
  "Rock Cup": "\u{1FAA8}",       // 🪨
  "Moon Cup": "\u{1F319}",       // 🌙
  "Fruit Cup": "\u{1F349}",      // 🍉
  "Boomerang Cup": "\u{1FA83}",  // 🪃
  "Feather Cup": "\u{1FAB6}",    // 🪶
  "Cherry Cup": "\u{1F352}",     // 🍒
  "Acorn Cup": "\u{1F330}",      // 🌰
  "Spiny Cup": "\u{1F994}",      // 🦔
};

// The mods the user has selected, as the backend knows them. Deliberately not "every mod the page has listed that is selected": that list
// (state.categories) is only reloaded by loadMods(), so a mod downloaded and selected in this very session isn't in it yet, and the Commit
// page said "No mods are selected yet". The backend checks each key (a selected mod that is gone from the disk is reported there).
function selectedKeys() {
  return Object.keys(state.checked || {}).filter(k => state.checked[k]);
}

function allKeys() {
  const keys = [];
  for (const cat in state.categories) {
    for (const unit of state.categories[cat]) {
      keys.push(cat + "/" + unit);
    }
  }
  return keys;
}

function initials(name) {
  const words = name.replace(/[().]/g, "").split(" ").filter(Boolean);
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

// Matches the in-game character-select grid: 8 columns x 6 rows, grouped by
// family the same way the game groups them. A couple of slots are a single
// icon in-game that lets you pick between two roster entries (Villager,
// Inkling, Link, Metal / Gold Mario) - those are represented as {group, options} instead of a name.
const CHARACTER_GRID_LAYOUT = [
  "Mario", "Luigi", "Peach", "Daisy", "Rosalina", "Tanooki Mario", "Cat Peach", "Peachette",
  "Yoshi", "Toad", "Koopa Troopa", "Shy Guy", "Lakitu", "Toadette", "King Boo", "Petey Piranha",
  "Baby Mario", "Baby Luigi", "Baby Peach", "Baby Daisy", "Baby Rosalina", { group: "Metal Mario", options: ["Metal Mario", "Gold Mario"] }, "Pink Gold Peach", "Wiggler",
  "Wario", "Waluigi", "Donkey Kong", "Bowser", "Dry Bones", "Bowser Jr.", "Dry Bowser", "Kamek",
  "Larry", "Lemmy", "Wendy", "Ludwig", "Iggy", "Roy", "Morton", "Birdo",
  { group: "Inkling", options: ["Inkling Girl", "Inkling Boy"] },
  { group: "Villager", options: ["Villager (Boy)", "Villager (Girl)"] },
  "Isabelle", { group: "Link", options: ["Link", "Link (Breath of the Wild)"] }, "Diddy Kong", "Funky Kong", "Pauline", "Mii",
];

// The 1-2 most prominent colors per base-game character/group - just one
// entry for a character whose design really only reads as a single color
// (Yoshi, Link, Metal Mario, ...), two for anything with a genuine second
// iconic color, each with a rough dominance weight (needn't sum to 100 -
// buildCornerGradient() normalizes). Hand-picked from each character's
// actual in-game appearance, keyed by the exact string used in
// CHARACTER_GRID_LAYOUT above (group tiles keyed by their group label,
// since that's the single tile shown for both options). Used to paint each
// tile's background - see buildCornerGradient().
const CHARACTER_COLORS = {
  "Mario":            [{hex:"#E52521",weight:60},{hex:"#2E3192",weight:40}],
  "Luigi":            [{hex:"#43B047",weight:60},{hex:"#2E3192",weight:40}],
  "Peach":            [{hex:"#F783C6",weight:65},{hex:"#FFD966",weight:35}],
  "Daisy":            [{hex:"#FF8C1A",weight:60},{hex:"#FFE646",weight:40}],
  "Rosalina":         [{hex:"#DCE8F5",weight:55},{hex:"#F5E1A4",weight:45}],
  "Tanooki Mario":    [{hex:"#8B5A2B",weight:100}],
  "Cat Peach":        [{hex:"#F783C6",weight:60},{hex:"#FCEEDD",weight:40}],
  "Peachette":        [{hex:"#FF8AC6",weight:55},{hex:"#FFB347",weight:45}],
  "Yoshi":            [{hex:"#66BB55",weight:100}],
  "Toad":             [{hex:"#FFFFFF",weight:55},{hex:"#E4212C",weight:45}],
  "Koopa Troopa":     [{hex:"#3FA34D",weight:60},{hex:"#F2D479",weight:40}],
  "Shy Guy":          [{hex:"#E5342A",weight:100}],
  "Lakitu":           [{hex:"#6EC6E8",weight:55},{hex:"#3FA34D",weight:45}],
  "Toadette":         [{hex:"#FFFFFF",weight:50},{hex:"#FF6FA3",weight:50}],
  "King Boo":         [{hex:"#F5F5F5",weight:100}],
  "Petey Piranha":    [{hex:"#3E9142",weight:60},{hex:"#D8342A",weight:40}],
  "Baby Mario":       [{hex:"#E52521",weight:60},{hex:"#2E3192",weight:40}],
  "Baby Luigi":       [{hex:"#43B047",weight:60},{hex:"#2E3192",weight:40}],
  "Baby Peach":       [{hex:"#F783C6",weight:60},{hex:"#FFD966",weight:40}],
  "Baby Daisy":       [{hex:"#FF8C1A",weight:60},{hex:"#FFE646",weight:40}],
  "Baby Rosalina":    [{hex:"#DCE8F5",weight:55},{hex:"#F5E1A4",weight:45}],
  "Metal Mario":      [{hex:"#C7CDD3",weight:60},{hex:"#D4AF37",weight:40}],   // (the group tile: silver, and Gold Mario's gold)
  "Pink Gold Peach":  [{hex:"#E8AFC0",weight:55},{hex:"#D9B36C",weight:45}],
  "Wiggler":          [{hex:"#F5D033",weight:100}],
  "Wario":            [{hex:"#F5D033",weight:55},{hex:"#6A3FA0",weight:45}],
  "Waluigi":          [{hex:"#6A3FA0",weight:60},{hex:"#2B2B2B",weight:40}],
  "Donkey Kong":      [{hex:"#7A4B2A",weight:65},{hex:"#D8342A",weight:35}],
  "Bowser":           [{hex:"#3FA34D",weight:50},{hex:"#F3A24B",weight:50}],
  "Dry Bones":        [{hex:"#F0EAD6",weight:100}],
  "Bowser Jr.":       [{hex:"#F3A24B",weight:55},{hex:"#3FA34D",weight:45}],
  "Dry Bowser":       [{hex:"#DED7C6",weight:100}],
  "Kamek":            [{hex:"#3D6FD4",weight:55},{hex:"#E8C87A",weight:45}],
  "Larry":            [{hex:"#4FD5E8",weight:55},{hex:"#3FA34D",weight:45}],
  "Lemmy":            [{hex:"#A6E22E",weight:55},{hex:"#F2D479",weight:45}],
  "Wendy":            [{hex:"#FF4FA3",weight:55},{hex:"#3FA34D",weight:45}],
  "Ludwig":           [{hex:"#5AC8E8",weight:55},{hex:"#3FA34D",weight:45}],
  "Iggy":             [{hex:"#7ED957",weight:55},{hex:"#F2D479",weight:45}],
  "Roy":              [{hex:"#FF5FA3",weight:55},{hex:"#1A1A1A",weight:45}],
  "Morton":           [{hex:"#D8D8D8",weight:55},{hex:"#3FA34D",weight:45}],
  "Birdo":            [{hex:"#FF6FC5",weight:100}],
  "Inkling":          [{hex:"#3AC7E0",weight:55},{hex:"#FF7A1A",weight:45}],
  "Villager":         [{hex:"#4A90D9",weight:55},{hex:"#4CAF50",weight:45}],
  "Isabelle":         [{hex:"#F5C842",weight:55},{hex:"#4CAF50",weight:45}],
  "Link":             [{hex:"#3E8E41",weight:100}],
  "Diddy Kong":       [{hex:"#E5342A",weight:55},{hex:"#7A4B2A",weight:45}],
  "Funky Kong":       [{hex:"#7A4B2A",weight:55},{hex:"#C060C0",weight:45}],
  "Pauline":          [{hex:"#D8342A",weight:55},{hex:"#1A1A1A",weight:45}],
  "Mii":              [{hex:"#4A90D9",weight:55},{hex:"#FFFFFF",weight:45}],
};

function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

// Builds a CSS background-image value that paints up to 4 colors into the
// 4 corners of an element, each corner's spread/strength driven by that
// color's weight - a heavier color reaches further across the tile and
// sits more opaque, a lighter one stays a small, subtle patch in its
// corner. Implemented as one radial-gradient layer per color (real 4-corner
// gradients aren't a CSS primitive) rather than reimplementing it in JS.
function buildCornerGradient(colors) {
  if (!colors || colors.length === 0) return "";
  if (colors.length === 1) {
    // Single-color character - flat, fully-saturated fill (two identical
    // stops rather than a plain background-color so it still layers as a
    // background-image, same as the two-color case below).
    const { r, g, b } = hexToRgb(colors[0].hex);
    return `linear-gradient(135deg, rgb(${r},${g},${b}) 0%, rgb(${r},${g},${b}) 100%)`;
  }
  // Two colors: a diagonal corner-to-corner blend, full strength at each
  // end (no white-wash tint - see the brightness fix this replaced) with
  // the blend band's position along the diagonal shifted by weight, so the
  // more dominant color visibly covers more of the tile.
  const [a, b] = colors;
  const totalWeight = a.weight + b.weight || 1;
  const splitPct = Math.round((a.weight / totalWeight) * 100);
  const bandStart = Math.max(10, splitPct - 20);
  const bandEnd = Math.min(90, splitPct + 20);
  const rgbA = hexToRgb(a.hex), rgbB = hexToRgb(b.hex);
  return `linear-gradient(135deg, rgb(${rgbA.r},${rgbA.g},${rgbA.b}) ${bandStart}%, rgb(${rgbB.r},${rgbB.g},${rgbB.b}) ${bandEnd}%)`;
}

// A group whose first option is named like the group itself needs a word for it next to the other option: the plain "Link" is the
// classic one, next to "Link (Breath of the Wild)". (Metal Mario | Gold Mario need none: each is named in full.)
const GROUP_FIRST_OPTION_LABEL = { "Link": "Classic" };
function groupOptionLabel(fullName, groupName) {
  if (fullName === groupName && GROUP_FIRST_OPTION_LABEL[groupName]) return GROUP_FIRST_OPTION_LABEL[groupName];
  const paren = fullName.match(/\(([^)]+)\)/);
  if (paren) return paren[1];
  return fullName.replace(groupName, "").trim() || fullName;
}

function findRosterEntry(name) {
  const fromChars = state.roster.find(r => r.name === name);
  if (fromChars) return fromChars;
  for (const cup of state.cups) {
    const fromCourse = cup.courses.find(c => c.name === name);
    if (fromCourse) return fromCourse;
  }
  const simple = findSimpleCategoryByLabel(name);
  if (simple) {
    const fromSimple = state.simpleCategories.find(c => c.key === simple.key);
    if (fromSimple) return fromSimple;
  }
  const vehicle = findVehicleItem(name);
  if (vehicle) return vehicle.item;
  const item = findItem(name);
  if (item) return item;
  return { name, units: [] };
}

function isCharacterName(name) {
  return state.roster.some(r => r.name === name);
}

function findCupForCourse(name) {
  return state.cups.find(cup => cup.courses.some(c => c.name === name)) || null;
}

// Which download/merge category a given item name (character, course, or
// one of SIMPLE_CATEGORIES' fixed labels) belongs to - drives which
// mods/extracted/<category>/ folder a fetch downloads into, and which
// GameBanana browsing flow (per-character grid, course search, or plain
// simple-category grid) its "Browse GameBanana" button uses.
function resolveItemCategory(name) {
  if (isCharacterName(name)) return "characters";
  const simple = findSimpleCategoryByLabel(name);
  if (simple) return simple.key;
  const vehicle = findVehicleItem(name);
  if (vehicle) return vehicle.section;
  if (isItemName(name)) return ITEMS_CATEGORY;
  return "courses";
}

// Shared by the "Mods to merge" list (character/course modal) and the Full
// List tab - deletes a downloaded mod's folder from disk entirely, no
// matter how it got there (manual download or GameBanana fetch).
function buildRemoveModButton(key, onRemoved) {
  const btn = document.createElement("button");
  btn.className = "ghost small remove-mod-btn";
  btn.textContent = "Remove";
  btn.title = "Delete this mod's downloaded files";
  btn.addEventListener("click", async (e) => {
    e.stopPropagation();
    const label = key.split("/").slice(1).join("/");
    if (!confirm(`Delete the downloaded files for "${label}"? This can't be undone.`)) return;
    btn.disabled = true;
    btn.textContent = "Removing...";
    const result = await pywebview.api.remove_mod_unit(key);
    if (!result.success) {
      alert(result.error);
      btn.disabled = false;
      btn.textContent = "Remove";
      return;
    }
    delete state.checked[key];
    await onRemoved();
  });
  return btn;
}

function formatFileSize(bytes) {
  if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  if (bytes >= 1024) return (bytes / 1024).toFixed(0) + " KB";
  return bytes + " B";
}

// Footer stat sizes can reach multi-GB territory (extracted mods especially),
// unlike formatFileSize()'s single-file use, so this scales up to GB instead
// of leaving a huge MB number.
function formatBytesGB(bytes) {
  const GB = 1024 * 1024 * 1024;
  const MB = 1024 * 1024;
  if (bytes >= GB) return (bytes / GB).toFixed(2) + " GB";
  if (bytes >= MB) return (bytes / MB).toFixed(1) + " MB";
  if (bytes >= 1024) return (bytes / 1024).toFixed(0) + " KB";
  return bytes + " B";
}

async function refreshStats() {
  const stats = await pywebview.api.get_stats();
  const courseEl = document.getElementById("stat-courses");
  courseEl.innerHTML = `<strong>${stats.courses.pct}%</strong> courses modded (${stats.courses.modded}/${stats.courses.total})`;
  const charEl = document.getElementById("stat-characters");
  charEl.innerHTML = `<strong>${stats.characters.pct}%</strong> characters modded (${stats.characters.modded}/${stats.characters.total})`;
  const sizeEl = document.getElementById("stat-size");
  sizeEl.innerHTML = `Downloaded: <strong>${formatBytesGB(stats.compressed_bytes)}</strong> compressed / <strong>${formatBytesGB(stats.extracted_bytes)}</strong> extracted`;
}

const FILE_STATUS_LABEL = {
  not_downloaded: "Not downloaded",
  downloaded: "Downloaded ✓",
  needs_manual_fix: "Needs manual fix",
  ui_assets: "UI art only",
  missing_romfs: "Needs romfs folder",
  error: "Error",
};

// Item names (character/course) whose "GameBanana mods" card should render
// collapsed - toggled manually via the section header's Show/Hide button,
// read back when refreshAfterChange() rebuilds the card from scratch so the
// collapse survives that rebuild.
const gbSectionCollapsed = new Set();
let gbJustAdded = null;   // {item, modId, type}: the mod "Use this mod" just added - the card it lands on scrolls to it (and downloads it when there is only one file)
let cardNotice = null;   // {item, text}: something to tell the user at the top of that part's card (a mod that was just filed there for them); kept until they close it or open another card

