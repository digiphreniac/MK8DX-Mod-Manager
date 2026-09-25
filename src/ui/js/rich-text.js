// ---- Text with links ----
// A mod's description reaches the page as "runs" - its plain text with the links kept: [{text}, {text, href}, ...] (see
// gamebanana_api.html_to_runs). This builds the DOM for them: text nodes and <a> elements the app makes itself, never markup
// from the mod. A link opens in the user's own browser (the window itself never navigates away), and shows where it goes as its
// tooltip. Text that was saved before runs existed (or has none) is still searched for bare addresses, which people paste all
// the time without making them links.

const BARE_URL_RE = /https?:\/\/[^\s<>"]+/g;

function makeExternalLink(text, href) {
  const a = document.createElement("a");
  a.className = "gb-link";
  a.href = href;
  a.textContent = text;
  a.title = href;
  a.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();   // (a link inside a clickable row shouldn't also open the row)
    pywebview.api.open_external_url(href);
  });
  return a;
}

// `text` into `parent`, with any bare web address in it made a link (without the full stop or bracket that ends a sentence)
function appendLinkedText(parent, text) {
  let last = 0;
  for (const m of text.matchAll(BARE_URL_RE)) {
    const url = m[0].replace(/[.,;:!?)\]}'"]+$/, "");
    if (!url) continue;
    if (m.index > last) parent.appendChild(document.createTextNode(text.slice(last, m.index)));
    parent.appendChild(makeExternalLink(url, url));
    last = m.index + url.length;
  }
  if (last < text.length) parent.appendChild(document.createTextNode(text.slice(last)));
}

// Fills `el` with a mod's description: its runs when it has them, else its plain text.
function renderRichText(el, mod) {
  el.replaceChildren();
  const runs = mod && mod.description_runs;
  if (runs && runs.length) {
    for (const r of runs) {
      if (r.href) el.appendChild(makeExternalLink(r.text, r.href));
      else appendLinkedText(el, r.text);
    }
  } else {
    appendLinkedText(el, (mod && mod.description) || "");
  }
}
