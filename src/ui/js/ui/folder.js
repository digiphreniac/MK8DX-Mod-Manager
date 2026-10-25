// ===== UI components: FolderCard (where a folder is) =====
//   ui.folderCard({ path, label, recommended, onOpen })  ->  { el }
//     path         the folder
//     label        the tag at the top left ("Recommended", "Custom folder", "Existing folder")
//     recommended  the card is green and the tag solid
//     onOpen       with it, a folder button at the top right opens the folder in the file manager (may be async)
// What a setting says about its folder (is_default / is_recommended / label) is turned into these options by the setting that shows it
// (settings-registry.js): the card knows nothing about which folder it is.
ui.folderCard = function (spec) {
  const head = ui.el("div", "ui-folder-head",
    ui.chip({ text: spec.label, tone: spec.recommended ? "ok" : "neutral", solid: !!spec.recommended, caps: true }).el);
  if (spec.onOpen) {
    head.append(ui.button({
      variant: "ghost", size: "small", class: "ui-folder-open", icon: "folder", title: "Open this folder in the file manager", onClick: spec.onOpen,
    }).el);
  }
  return { el: ui.el("div", "ui-folder" + (spec.recommended ? " ui-folder--recommended" : ""), head, ui.el("code", { class: "ui-folder-path", text: spec.path })) };
};
