// ===== UI components: confirm and alert =====
// The app's own versions of confirm() and alert(): they look like the rest of the app, stack above whatever is open, and can wait for a
// job.
//
//   const answer = await ui.confirm({
//     title, message,            message: text; a "\n" starts a new line
//     detail,                    a smaller grey line under it
//     extra: { label, checked, hint },     a tick box; its state is answer.value
//     confirmLabel, cancelLabel, danger, busyLabel,
//     onConfirm(value),          optional job to run when they say yes. The window stays open and busy until it settles; then
//                                  return nothing (it closes), { error } (shown inside, they can try again or cancel), or
//                                  { message, tone: "ok" | "err" } (shown inside, the yes button goes and Cancel becomes Close)
//   })  ->  false when they cancel, otherwise { value }  (so `if (!answer) return;` works)
//
//   await ui.alert({ title, message, okLabel })       one button; resolves when it is closed
ui.confirm = function (opts) {
  return new Promise((resolve) => {
    let answer = false, busy = false;
    const content = [];
    if (opts.message) content.push(ui.el("p", { class: "ui-confirm-message", text: opts.message }));
    if (opts.detail) content.push(ui.el("div", { class: "settings-hint", text: opts.detail }));
    let tick = null;
    if (opts.extra) {
      tick = ui.el("input", { checked: !!opts.extra.checked, attrs: { type: "checkbox" } });
      content.push(ui.el("label", "settings-checkbox-label", tick, opts.extra.label));
      if (opts.extra.hint) content.push(ui.el("div", { class: "settings-hint", text: opts.extra.hint }));
    }
    const result = ui.el("div", { class: "ui-result", hidden: true });
    content.push(result);

    const showResult = (message, tone) => { result.className = "ui-result " + tone; result.textContent = message; result.hidden = false; };
    const modal = ui.modal({
      id: "ui-confirm-" + Math.random().toString(36).slice(2, 8),
      title: opts.title, size: "narrow", role: "alertdialog", body: content,
      beforeClose: () => !busy,
      onClose: () => { resolve(answer); setTimeout(() => modal.destroy()); },
      actions: [
        { label: opts.cancelLabel || "Cancel", variant: "ghost", size: "small", onClick: () => modal.close() },
        {
          label: opts.confirmLabel || "OK", busyLabel: opts.busyLabel, variant: opts.danger ? "danger" : "primary", size: "small",
          onClick: async () => {
            const value = tick ? tick.checked : undefined;
            const [cancel, yes] = modal.actions;
            if (!opts.onConfirm) { answer = { value }; modal.close(); return; }
            busy = true;
            result.hidden = true;
            cancel.setDisabled(true);
            let outcome;
            try { outcome = await opts.onConfirm(value); }
            catch (e) { outcome = { error: e && e.message ? e.message : String(e) }; }
            busy = false;
            cancel.setDisabled(false);
            if (outcome && outcome.error) { showResult(outcome.error, "err"); return; }
            answer = { value };
            if (outcome && outcome.message) {
              showResult(outcome.message, outcome.tone || "ok");
              yes.el.hidden = true;
              cancel.setLabel("Close");
              return;
            }
            modal.close();
          },
        },
      ],
    });
    modal.open();
    modal.actions[opts.danger ? 0 : 1].el.focus();      // (a destructive yes is never what Enter lands on)
  });
};

ui.alert = function (opts) {
  return new Promise((resolve) => {
    const modal = ui.modal({
      id: "ui-alert-" + Math.random().toString(36).slice(2, 8),
      title: opts.title || "Heads up", size: "narrow", role: "alertdialog",
      body: ui.el("p", { class: "ui-confirm-message", text: opts.message || "" }),
      onClose: () => { resolve(); setTimeout(() => modal.destroy()); },
      actions: [{ label: opts.okLabel || "OK", variant: "primary", size: "small", onClick: () => modal.close() }],
    });
    modal.open();
    modal.actions[0].el.focus();
  });
};
