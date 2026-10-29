# Browser mode - how the app runs on Linux

On Windows and macOS the app opens a window of its own and the system lends it a web view (WebView2, WebKit). **Linux has none
to lend**, so the app shows its page in the browser the user already has: it serves `src/ui/` over HTTP on `127.0.0.1` and opens
the link. Everything else - the whole backend, the whole page - is the same code as on the other two systems.

This is the default on Linux, from source and in the package alike. `MK8DX_GUI=qt` (or `gtk`) still opens a pywebview window for
anyone who wants one, but they have to install the toolkit themselves: `pip install "pywebview[qt]"`.

## Why

The package used to carry Qt WebEngine - which is Chromium - because that was the only way to have a window. It cost more than
the rest of the app put together:

| Linux package | download | unpacked |
| --- | --- | --- |
| 0.4.2, Qt WebEngine, gzip | 211 MB | 597 MB |
| 0.4.3 development, Qt trimmed, xz | 123 MB | 417 MB |
| **browser mode** | **18 MB** | **50 MB** |

`libQt6WebEngineCore.so.6` alone was 194 MB, already stripped, with 169 MB of that executable code; `libicudata.so.73` another
31 MB. Neither can be made smaller without building Qt from source, and neither can be left out: Qt WebEngine is built on Qt
Quick and QML, so `libQt6WebEngineWidgets` links `Quick`, `QuickWidgets`, `Qml`, `QmlModels`, `QmlMeta`, `QmlWorkerScript`,
`OpenGL`, `Positioning` and `PrintSupport` directly. The trimming that `tools/linux_trim.py` used to do (QML modules,
translations, Chromium's other languages and its developer tools) had already taken out everything that could go. The floor for a
packaged Qt window was about 120 MB; browser mode has no floor to speak of, because the browser is already on the machine.

It also drops the whole system-library surface the Qt package needed - NSS, NSPR, xcb, xkbcommon, libXdamage, GTK 3 - and with
it the Chromium sandbox problem on Ubuntu 24.04+ (`QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox`), which users had to work around by
hand. A Linux build now needs nothing installed on the build machine beyond Python.

## How the page still thinks it is talking to pywebview

The page makes about 200 `pywebview.api.<method>(...)` calls. None of them changed. Two things made that cheap:

- **the backend never pushes into JS.** There is no `evaluate_js` anywhere; every exchange is the page asking and Python
  answering, which is exactly what HTTP does.
- **pictures already travel as data.** Local pictures are `data:image/png;base64,...` strings returned by the API, and remote
  ones are GameBanana URLs. Nothing is loaded from a `file://` path, so nothing had to be re-pointed at the server.

So `src/ui/js/webserver-bridge.js` puts an object with pywebview's shape in pywebview's place: one real function per public
method of `Api`, each posting its arguments to `POST /api/<method>` and returning the answer. A call that raises in Python
rejects in JS, as it did under pywebview.

The bridge is **not** in `bootstrap.js`'s `SCRIPTS` list. `api-coalesce.js` and `main.js` expect `window.pywebview.api` to exist
the moment they run, so the server injects the bridge - and the method names and this run's token - into `<head>` ahead of
everything else. In a pywebview window the server never runs, `window.__mk8dxServer` is absent, and the file does nothing.

The `pywebviewready` event is fired at `DOMContentLoaded`, not earlier: `bootstrap.js` only replays the event for the scripts it
loads if its own listener was registered when it went off, and that listener is only there once `bootstrap.js` itself has run.

## Keeping it closed

The server answers only on `127.0.0.1`, so nothing else on the network can reach it. Against the other machine-local risk - a web
page the user has open in another tab trying to drive the app - there are three locks:

- **a token.** Every run makes a fresh `secrets.token_urlsafe(32)`. It is in the link the app opens, `/` serves the page only to
  a request that carries it (and the refusal page does not contain it), and every `/api/` call must send it in `X-MK8DX-Token`.
- **a custom header.** Another origin cannot send `X-MK8DX-Token` without a CORS preflight first, and the server answers every
  `OPTIONS` with 403 and no `Access-Control-Allow-*` header at all, so the browser never sends the call it was preparing.
- **the `Host` header must be the loopback address.** This is what stops a hostname that resolves to 127.0.0.1 from being used to
  make the browser treat the app as somebody else's site.

Static files under `src/ui/` are served without a token - they are the app's own markup, styles and scripts and hold nothing of
the user's - but nothing outside `src/ui/` can be reached whatever the request says (`_serve_static` resolves the path and checks
that `src/ui` is one of its parents).

## When it stops

The app is not a window someone closes, so it has to work out for itself when it is finished:

| | |
| --- | --- |
| the page checks in | `POST /alive` every 20 s, and whenever the tab becomes visible again |
| the page is closed | `pagehide` sends `POST /closing` with `keepalive` (which, unlike `sendBeacon`, still carries the token). The app waits `CLOSING_GRACE` = 6 s before acting, because a reload sends it too |
| nothing at all | after `IDLE_TIMEOUT` = 180 s. Long, because a browser throttles a hidden tab's timers to about once a minute |
| nobody ever opened the link | after `FIRST_LOAD_TIMEOUT` = 30 min - a person may take a while to find the link and paste it, so the short idle timer must not start before the page has loaded once |
| Ctrl-C in the terminal | at once |

**It never stops while a call is being answered.** `_Lifecycle.answering()` counts calls in flight, and `should_quit()` returns
nothing while that count is above zero - so closing the tab in the middle of a merge or a download cannot cut it off part-way.

## Dialogs, and programs of the system

Three things used to come from the window: the folder picker (`pick_master_dir`) and the mod list's Save and Open dialogs. With
no window they come from `zenity` or `kdialog` instead (`src/host_tools.py`; `kdialog` is preferred on a KDE desktop so the
dialog matches the rest of it, `zenity` elsewhere). `Api.can_pick_folders()` says whether there is one at all, and where there
isn't the page offers a box to type a path into instead of a button that would do nothing.

Every program the app starts goes through `host_tools`, for a reason that applies to the browser itself as much as to the
dialogs: **a PyInstaller build runs with `LD_LIBRARY_PATH` pointing at its own copies** of libstdc++, GLib and the rest, and
anything started from inside it inherits that and loads our libraries instead of its own - which is how `xdg-open`, or the
browser it picks, dies on a symbol lookup instead of starting. PyInstaller saves what the variable was in `LD_LIBRARY_PATH_ORIG`
for exactly this; `host_tools.original_environ()` puts it back, `system_env()` does it around code that starts something without
letting us pass an environment (`webbrowser.open`). This was already wrong for the three "open this link" methods in the Qt
package - they were being handed the bundle's library path too - and is fixed by the same change.

## What is in the package now

50 MB unpacked: Pillow and its bundled picture libraries (19 MB), Python itself (11 MB), the bundled `7zz` (3.6 MB), OpenSSL,
and `src/ui/`. The biggest single remaining item is `pillow.libs` at 15 MB, of which `libavif` is 4.7 MB.

## Running it

- `python src/mod_manager.py` - serves the page and opens the browser.
- `MK8DX_NO_BROWSER=1` - prints the link and waits, instead of opening a browser (over SSH, or in a test).
- `MK8DX_PORT=8731` - a fixed port instead of a free one.
- `MK8DX_GUI=qt` - a pywebview window instead, if `pywebview[qt]` is installed.
- `MK8DX_GUI=browser` - browser mode on Windows or macOS, where it is not the default.

`MK8DX_DEBUG=1` does nothing in browser mode: the browser's own developer tools are right there (F12), which is one thing that
got *better* - the Qt package had Chromium's developer tools trimmed out of it.
