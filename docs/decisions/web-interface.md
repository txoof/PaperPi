# Web interface technology

Status: proposed (M1, issue #191). Decided with txoof.

## Problem

In v2 the web interface is the main way to set up and change PaperPi: plugins, screen, password. A command line is used only where it really can't be avoided. It runs on the Pi, so it must be light enough for a Pi 3. PaperPi is a household device on a home network, so the web interface is kept simple.

## Options considered

1. **FastAPI, with pages built on the Pi plus htmx.** FastAPI is a Python web framework built on pydantic, the package that already describes and checks the config (`config-format.md`), so forms can be built straight from those descriptions. The Pi sends ready HTML pages. htmx is a small JavaScript file (about 15 KB) that updates one part of a page without reloading it. No build step, no Node.js. Uses roughly 40–60 MB of memory. **Chosen.**
2. **Flask.** An older Python framework. Similar, but it doesn't link to pydantic as neatly.
3. **A JavaScript app (React, Vue).** Richer pages, but it needs a separate build step with Node.js, a second programming language, and more memory and processor time on a Pi 3.

## Decision (proposed)

### Pages

- Pages are built on the Pi. htmx updates parts of a page, such as the screen preview and the list of warnings.
- A page that needs dragging or resizing gets a small JavaScript library made for that, loaded as a plain file with no build step. The first case will be the dashboard editor (see "Later").

### Plugin settings forms

- One page handles every plugin. It reads the plugin's settings description (see `plugin-interface.md`) and builds the form from it: number field, dropdown, password field for API keys, and so on.
- On Save, the values are checked with the same description. Errors are shown next to the field. A saved change applies at once (see `live-config-reload.md`).
- A setting that needs more than a plain field can name an input type from a small list in the web interface, e.g. `location` (lat/lon lookup), `server_search` (find music servers), `layout_picker`. New input types are added when a plugin needs one.
- Plugins added later show up without changes to the web code.

### Logging in

- The first person to open the web interface sets the password. After a reset (delete the password line in the config file, see `config-format.md`) the same happens again. This replaces "password set during installation" in the plan; installing needs no extra step.
- After logging in, the browser stays logged in for 1 year, using a cookie (a small token the browser keeps). There is a **Log out** button.
- No limit on wrong password attempts.

### No HTTPS

- The web interface uses plain HTTP, e.g. `http://paperpi.local:8080`. HTTPS (an encrypted connection) needs a certificate, and without a public one browsers show a warning page, which only gets in the way at home.
- The docs say: the web interface is for the home network only. Do not open it to the internet.

### Preview images

- **Home page:** a copy of what is on the e-paper screen now, with the plugin's name and when it was drawn. It updates by itself when the screen changes.
- **Plugin settings page:** a **Preview** button draws the plugin with the settings in the form, before saving, using the PNG driver (see `display-driver-interface.md`). The real screen is not touched. If the plugin's data source can't be reached, the preview uses the plugin's sample data and says so.

### Other pages

The web interface also shows the warnings decided in the other notes: the last 100 warnings and errors, plugins that are left out after failures, "screen not answering", config errors with their line, and "the config file was changed outside the web interface. Apply changes?".

### Later

These wait until after 2.0, and each becomes its own issue then. Nothing in this design should block them.
- **Dashboard editor:** a graphical page to place and resize several plugins on one screen (milestones M9/M10). Dragging and resizing happen in the browser with a small grid library (e.g. gridstack.js). The Pi saves the result as a list of boxes (position and size of each plugin) in the config and draws a real preview after each change. Plugins already receive the size of the area they draw in, so they don't need changes.
- **HTTPS:** a docs page on putting your own web server in front of PaperPi for anyone who wants it. Docs only, no code.

## Open questions

None. All points above were agreed with txoof on 2026-10-04.
