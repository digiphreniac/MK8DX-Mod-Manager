// ===== The app's windows, as specs =====
// Settings, Conflicts and omitted files, Help and "Check the names we guessed" - built here with the components in js/ui/ and left hidden
// until opened (so every part can be looked up by id from the start). What they do when opened lives with the code they belong to
// (openSettingsModal in views.js, openConflictsModal in data-and-conflicts.js ...); the callbacks below name those functions, which are
// only called later, after every script has loaded.

// ---- Settings ----
const appExperienceCard = ui.section({
  title: "App experience",
  actions: [{
    label: "Reset to default",
    disabled: () => !groupDiffersFromDefaults("app-experience"),       // (asked again by appExperienceCard.refresh(), see updateResetButtons)
    onClick: () => resetGroupToDefaults("app-experience"),
  }],
  body: ui.settingsGroup("app-experience"),
});

const settingsModal = ui.modal({
  id: "settings-modal",
  title: "Settings",
  size: "wide",
  body: ui.columns([
    ui.section({ title: "Data folder", body: ui.settingsGroup("data-folder") }),
    ui.section({ title: "Staging folder", body: ui.settingsGroup("staging-folder") }),
    ui.section({ title: "Game language", body: ui.el("div", { id: "ui-setup-settings-body" }) }),
    ui.section({
      title: "UI Icon Worklist",
      body: [
        ui.el("div", "settings-hint",
          "Every downloaded mod that's UI art or a packed .sarc with no romfs (character icon sets, loading-screen/theme archives, ...) - can't be merged automatically. " +
          "Use an external tool like Switch Toolbox to inject the icons into your combined set at ",
          ui.el("code", { text: "ui-icons/romfs/UI/cmn/" }),
          ". A whole-file .sarc from a theme is a full replacement of that set, so start from it deliberately rather than layering it over your own icon work."),
        ui.el("div", { id: "ui-icon-worklist-body" }, ui.el("div", { class: "ui-icon-worklist-empty", text: "Loading…" })),
      ],
    }),
    ui.section({ title: "Game version", body: ui.settingsGroup("game-version") }),
    appExperienceCard,
    ui.section({
      id: "conflicts-card",
      title: "Conflicts and omitted files",
      body: ui.el("div", "conflicts-card-row",
        ui.button({ id: "btn-open-conflicts", label: "Review", size: "small", onClick: () => openConflictsModal() }).el,
        ui.el("div", { class: "settings-hint", id: "conflicts-summary", text: "Checking…" })),
    }),
    ui.section({
      title: "Maintenance",
      body: [
        ui.button({ id: "btn-clear-all-mods", label: "Clear All Mods…", variant: "danger", size: "small", confirm: () => clearAllModsConfirm() }).el,
        ui.el("div", { class: "settings-hint", text: "Forgets every GameBanana mod link and file status tracked for every character (optionally deleting the downloaded files too). Mods you added manually, outside the app, are never touched." }),
      ],
    }),
  ]),
});

// ---- Conflicts and omitted files (opened from the card in Settings) ----
const conflictsModal = ui.modal({
  id: "conflicts-modal",
  title: "Conflicts and omitted files",
  bar: true,
  body: [
    ui.el("div", { id: "conflicts-body" }, ui.el("div", { class: "conflicts-empty", text: "Loading…" })),
    ui.disclosure({ class: "conflicts-howto", summary: "How this works" },
      ui.el("div", {
        class: "settings-hint",
        text: "When two selected mods change the same file you can keep one mod's copy, use the game's own file, or leave just those files out of one mod - the rest of the mod still works. " +
          "Leave-outs are remembered, even across re-downloads, and every mod's popup has a \"Files\" button (in a character's mod list it is \"Edit included files\" in the row's ... menu) to leave out any single file.",
      })).el,
  ],
});

// ---- Help ----
const helpModal = ui.modal({
  id: "help-modal",
  title: "Help",
  sections: [
    ui.section({
      title: "Known issues",
      body: [
        ui.el("div", { class: "help-status-term", text: "A modded course feels like it's playing in slow motion" }),
        ui.el("div", { class: "help-status-def", text: "Very heavy tracks can run in slow motion on the Switch. This comes from the track itself, not the app, so tell the track's author, or ask on the Discord." }),
        ui.el("div", { class: "help-status-term", text: "A character's icon or a course's name still looks like the original" }),
        ui.el("div", { class: "help-status-def", text: "Commit again after changing your mods. Also check that the language in Settings is the one your Switch uses, because the menu text is only built for that language." }),
        ui.el("div", { class: "help-status-term", text: "A mod I deselected still shows up in the game" }),
        ui.el("div", "help-status-def",
          "Copying onto an SD card only adds and replaces files, so a deselected mod's files stay behind. Delete ",
          ui.el("code", { text: "atmosphere/contents/0100152000022000/romfs" }),
          " on the SD card (or in your emulator's mod folder) first, then copy the staging folder again."),
      ],
    }),
    ui.section({
      title: "More support",
      body: [
        ui.el("div", { class: "help-status-def", text: "If you're having trouble, please join the Discord and ask for support there. You'll likely be asked for your log file, which you can find by clicking the button below." }),
        ui.el("div", "help-diag-row",
          ui.button({
            id: "btn-open-discord", label: "Join the Discord",
            icon: ui.html('<span class="help-btn-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#5865F2" d="M20.317 4.3698a19.7913 19.7913 0 00-4.8851-1.5152.0741.0741 0 00-.0785.0371c-.211.3753-.4447.8648-.6083 1.2495-1.8447-.2762-3.68-.2762-5.4868 0-.1636-.3933-.4058-.8742-.6177-1.2495a.077.077 0 00-.0785-.037 19.7363 19.7363 0 00-4.8852 1.515.0699.0699 0 00-.0321.0277C.5334 9.0458-.319 13.5799.0992 18.0578a.0824.0824 0 00.0312.0561c2.0528 1.5076 4.0413 2.4228 5.9929 3.0294a.0777.0777 0 00.0842-.0276c.4616-.6304.8731-1.2952 1.226-1.9942a.076.076 0 00-.0416-.1057c-.6528-.2476-1.2743-.5495-1.8722-.8923a.077.077 0 01-.0076-.1277c.1258-.0943.2517-.1923.3718-.2914a.0743.0743 0 01.0776-.0105c3.9278 1.7933 8.18 1.7933 12.0614 0a.0739.0739 0 01.0785.0095c.1202.099.246.1981.3728.2924a.077.077 0 01-.0066.1276 12.2986 12.2986 0 01-1.873.8914.0766.0766 0 00-.0407.1067c.3604.698.7719 1.3628 1.225 1.9932a.076.076 0 00.0842.0286c1.961-.6067 3.9495-1.5219 6.0023-3.0294a.077.077 0 00.0313-.0552c.5004-5.177-.8382-9.6739-3.5485-13.6604a.061.061 0 00-.0312-.0286zM8.02 15.3312c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9555-2.4189 2.157-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.9555 2.4189-2.1569 2.4189zm7.9748 0c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9554-2.4189 2.1569-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.946 2.4189-2.1568 2.4189Z"/></svg></span>'),
          }).el,
          ui.button({ id: "btn-show-log", label: "Show log file" }).el),
        ui.el("div", { class: "help-status-def", id: "help-log-note", hidden: true }),
      ],
    }),
  ],
});

// ---- Check the names we guessed (the rows are drawn into its body when it opens) ----
const guessedNamesModal = ui.modal({ id: "guessed-names-modal", title: "Check the names we guessed", size: "narrow", body: [] });

// ---- the windows whose markup is still in html/*.html: adopted, so they stack, close on Escape and on a click outside like the rest ----
const addModModal = ui.modal({ adopt: "add-mod-modal" });
const gbDetailModal = ui.modal({ adopt: "gb-detail-modal" });
const iconGenModal = ui.modal({ adopt: "icon-gen-modal" });
// The GameBanana browser stops its search when it closes, and Escape clears the search box first (the window closes on the next one).
const gbBrowseModal = ui.modal({
  adopt: "gb-browse-modal",
  onClose: () => { if (gbBrowse) gbBrowse.stop(); gbBrowse = null; },
  onEscape: () => !!(gbBrowseClearSearch && gbBrowseClearSearch()),
});
// The character / course / vehicle / item card as a pop-up (on a small window; on a wide one the card is docked beside the grid instead).
const characterModal = ui.modal({ adopt: "modal", onClose: () => { openCharacter = null; markActiveTile(); } });
