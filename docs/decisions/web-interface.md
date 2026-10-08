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

### Plugin list pages

*Added in M5 part 2b (issue #238), agreed with txoof on 2026-10-07.*
- **Active Plugins** lists every `[[plugin]]` block in the config file, in file order (the order the plugins take turns), also blocks with errors. Each has: Switch on / Switch off, **Up** and **Down** buttons (no dragging, so no extra JavaScript library; works the same on a phone), and Remove, which asks first.
- **Plugin Library** lists every plugin type that comes with PaperPi, with its one-line description, except `default` (PaperPi's own "nothing to show" message) and `debugging` (for testing PaperPi). Choosing one asks for a name (a free one is suggested, for example "Basic clock 2"; it may be left empty) and adds the block at the end of Active Plugins with a new `id` (see `config-format.md`, M5 part 3a-0). Active Plugins shows the name, and the `id` next to the type when it differs, so two plugins with the same name can be told apart. Sample pictures follow in part 3b.
- A plugin with required settings (see `plugin-interface.md`) is added **switched off**, and the add page lists those settings with their help text (for `met_no`: a real email address, as met.no's terms ask). Active Plugins shows "Needs settings: ..." and can't switch it on until they are filled in. *M5 part 3a-2 (agreed with txoof on 2026-10-08):* after adding, the new plugin's settings page opens at once, and each plugin in Active Plugins has a Settings link. The settings page also has a folded "Technical information" part with the plugin's `id`, type and storage folder.
- Each change is saved at once (nothing else in the config file changes: comments stay, and the comments just above a `[[plugin]]` line move and are removed with its block; a comment on the same line as `enabled =` is lost) and PaperPi reloads the file, so it applies at once.
- **Hand edits not applied yet:** a change from the web interface is made to the file as it is on disk, so hand edits stay and apply together with it. The page then says "Your hand edits to the config file were applied too." (The other choice, refusing to save until the hand edits are applied, needs an extra step every time.)
- A change names its block by place and `id`. If the block was moved or its `id` changed by hand since the page was shown, nothing is changed and the page says the file changed meanwhile. A file the web interface can't change safely (for example a `[[plugin]]` line written in an unusual way) is never saved wrongly: every change is read back and compared before saving. A change is also refused while the file has a problem that stops PaperPi from using it (PaperPi then runs on the last good copy, so the change would not apply), and when the file would become larger than PaperPi reads.

### Plugin settings forms

- One page handles every plugin. It reads the plugin's settings description (see `plugin-interface.md`) and builds the form from it: number field, dropdown, password field for API keys, and so on.
- On Save, the values are checked with the same description. Errors are shown next to the field. A saved change applies at once (see `live-config-reload.md`).
- A setting that needs more than a plain field can name an input type from a small list in the web interface, e.g. `location` (lat/lon lookup), `server_search` (find music servers), `layout_picker`. New input types are added when a plugin needs one. *Built in M5 part 3a-2:* a plugin names one with `paperpi.plugin.setting(..., helper="location")`; the web interface's list (`paperpi.web.helpers`) holds a function per name that adds its part under the field. A name it doesn't know adds nothing, so the plain field still works. The first helper is `location` (part 3c).
- Plugins added later show up without changes to the web code.
- *Agreed with txoof on 2026-10-08 (M5 part 3a):* the page shows the plugin's `name` first, then its own settings, then display time, refresh, layout and level; the other shared settings (time limit, alert and storage settings) are folded under "More settings", which opens by itself when one of them has an error or a value that is not the default. Each field shows its value, or the default when the file doesn't set it.
- How a save works (M5 part 3a-1): only settings that changed are written. An empty field means "the default" (an empty check box: off; an empty list: nothing picked); a value changed to the default is taken out of the file and becomes the comment `# key = default` again (a value left as it is stays, also one written in the file that equals the default), so the help text above it still fits. A new setting takes the place of its `# key = ...` comment line when there is one. If any value has an error, nothing is saved; each error is shown next to its field, with what was typed (never a secret). A secret (such as an API key) is never shown on the page; leaving its field empty keeps the saved one. A setting the form can't show (a group of settings, a list of numbers) is shown as it is in the file, to be changed there. A setting written over several lines in the file is never changed by the page.

### Logging in

- The first person to open the web interface sets the password. After a reset (delete the password line in the config file, see `config-format.md`) the same happens again. This replaces "password set during installation" in the plan; installing needs no extra step.
- After logging in, the browser stays logged in for 1 year, using a cookie (a small token the browser keeps). There is a **Log out** button.
- No limit on wrong password attempts.

*Update (M5, issue #238, agreed with txoof on 2026-10-07):*
- The web server runs **inside `paperpi run`**, in its own thread, not as a separate program. It can tell the scheduler directly to apply a change, it needs one Python process fewer (about 40 MB), and there is one program to install. Previews will draw in a separate process with a time limit, like normal updates, so a slow or broken plugin can't stop the web pages or the screen. If the web interface can't start (port taken), the log says why and the screen keeps running.
- The password is stored as a **scrypt** hash, which is built into Python (about 0.1 s and 16 MB of memory per check on a Pi; checks run one at a time; no limit on wrong tries, agreed again on 2026-10-07). The log-in cookie is signed with that hash, so a new password logs out every browser.
- Packages: FastAPI, uvicorn (the web server that runs FastAPI), jinja2 (page templates) and python-multipart (reads forms).
- **Log-in can be switched off:** `login = false` in `[web]`. Then anyone on the home network can change the settings; the config check gives a hint and the home page says so.
- **Forgotten password:** `sudo paperpi reset-password` removes the `password_hash` line and leaves the rest of the file as it is. After a restart or reload, the first visitor sets a new password. The log-in page shows these steps.
- Forms are only accepted from the web interface's own pages, and its pages can't be shown inside another website. Without this, a web page on the internet could make the visitor's browser send a form to PaperPi in their name. For the same reason the web interface only answers when it is opened by an IP address (e.g. `http://192.168.1.20:8080`) or `localhost`: a web page could otherwise point a name of its own at the Pi (called DNS rebinding) and set the first password itself. Names such as `paperpi.local` may be allowed later. Agreed with txoof on 2026-10-07: setup is done by IP address.

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
