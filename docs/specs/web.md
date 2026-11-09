# The web interface

The web interface is the main way to set up and change PaperPi: plugins, the screen and the password. It runs inside PaperPi itself, on the Pi, and is light enough for a Pi 3. The Pi builds every page and sends it ready to show; a small script, htmx, updates parts of a page without reloading it. It is for the home network only.

What each page does is on [Web Interface](../web-interface.md). This page describes how the web interface is built and kept safe.

## How it is built

- **Inside `paperpi run`,** in its own thread, not as a separate program. It can tell the scheduler directly to apply a change, and it needs no extra Python process (about 40 MB of memory). If it can't start (for example the port is taken), the log says why and the screen keeps running.
- **Pages are built on the Pi** from templates, with FastAPI (a Python web framework built on pydantic, the package that also checks the config file) and jinja2 (page templates). No build step and no second programming language.
- **htmx** (a small script of about 15 KB) updates one part of a page without reloading it, such as the picture on the screen now or the list of warnings.
- **A page that needs dragging** (the plugin list on the home page) uses a small library loaded as a plain file. Buttons do the same job, so everything works on a phone too.

## Plugin settings pages

- **One page handles every plugin.** It reads the plugin's settings description and builds the form from it: number fields, lists to choose from, password fields for secrets.
- **The page has two sections:** General (the settings every plugin has, with "Time limit, alerts, storage" folded inside) and the plugin's own settings, in the groups the plugin names.
- **On Save,** the values are checked with the same description, and errors are shown next to their field. Only settings that changed are written to the config file, and a saved change applies at once ([The config file](config.md#applying-changes)).
- **An empty field means the default.** A value changed back to the default is taken out of the file again.
- **A secret field is always empty on the page.** Leaving it empty keeps the saved secret.
- **Setting helpers** add a search box to the page ([Plugins and setting helpers](plugins.md#setting-helpers)).

Plugins added later show up without changes to the web code.

## Pictures

| Where                    | What it shows                                                                                           |
| ------------------------ | ------------------------------------------------------------------------------------------------------- |
| home page                | a copy of what is on the screen now, with the plugin's name and when it was drawn; it updates by itself |
| **Preview** on a settings page | the plugin drawn with the values in the form, before saving; the real screen is not touched      |
| Plugin Library           | an example picture of every layout of every plugin, drawn from its sample data                         |

- **A preview** draws the block as **Save** would write it, at the screen's size and for the screen's kind. It runs in its own process with a time limit, in a new, empty storage folder that is removed afterwards, so it can't change the plugin's saved files. Real data may take at most 45 seconds; when it fails, takes longer or has nothing to show, the preview uses the sample data and says why. One preview is drawn at a time.
- **Preview pictures are sent inside the page,** never saved as files.
- **Library pictures are drawn ahead** and saved in `library-pictures/` in `/var/lib/paperpi`, so the page opens at once. They wait 60 seconds after PaperPi starts, so the first screen update goes first. A picture is drawn again only when the plugin, the screen or PaperPi changes.

Note: the Library pictures are drawn in 256 grays so they are easy to see on a phone, also for a black-and-white screen; a color screen keeps its colors.

## Logging in

- **The first person to open the web interface sets the password.** No step is needed during the install.
- **After logging in,** the browser stays logged in for 1 year, with a cookie (a small token the browser keeps). There is a **Log out** button. A new password logs out every browser.
- **The password is stored as a scrypt hash:** a scrambled form that can be checked but not turned back into the password. One check takes about 0.1 seconds on a Pi.
- **A forgotten password:** `sudo paperpi reset-password` removes it from the config file; after a reload, the next visitor sets a new one. The log-in page shows these steps.
- **Every password field has a Show button,** so what was typed can be checked before sending.
- **Without logging in,** anyone on the home network sees only the picture on the screen now (on the log-in page), never the other plugins or the settings.

Note: `login = false` in `[web]` switches logging in off. Then anyone on the home network can change the settings; the config check gives a hint and the home page says so.

## Safety

- **For the home network only.** The web interface uses plain HTTP, not HTTPS (an encrypted connection), because HTTPS needs a certificate, and without a public one browsers show a warning page. Do not open it to the internet.
- **Forms are only accepted from the web interface's own pages,** and its pages can't be shown inside another website. Without this, a web page on the internet could make the visitor's browser send a form to PaperPi.
- **It only answers when opened by an IP address** (e.g. `http://192.168.1.20:8080`) or `localhost`. A web page could otherwise point a name of its own at the Pi and set the first password itself.
- **The pages load only PaperPi's own files,** plus pictures sent inside the page. A plugin can't add its own script to a page.
- **Secrets are never shown again** once saved, and never written to the log.

## Numbers

| What                                     | Value                                           |
| ---------------------------------------- | ----------------------------------------------- |
| port                                     | 8080 (`[web] port`)                             |
| staying logged in                        | 1 year                                          |
| longest real-data preview                | 45 seconds (or the plugin's own time limit, if shorter) |
| longest sample-data preview or Library picture | 10 seconds                                |
| Library pictures wait after a start      | 60 seconds                                      |
| wait for **Apply changes**               | 3 seconds, then the page says it is still busy  |
| **Keep these settings** after a new address or port | 5 minutes                            |

## Not built yet

- **A dashboard editor:** a page to place and resize several plugins on one screen.
- **HTTPS:** a manual page on putting your own web server in front of PaperPi, for anyone who wants it.
- **Names such as `paperpi.local`** instead of the IP address.

## Why it works this way

- **Pages built on the Pi with htmx:** a JavaScript app (React, Vue) would need a build step with Node.js, a second programming language, and more memory and processor time on a Pi 3. FastAPI is built on pydantic, so the forms come straight from the settings descriptions.
- **Inside PaperPi, not a separate program:** one program to install, one process fewer, and a change reaches the scheduler directly.
- **No limit on wrong password tries:** it is a household device on a home network, and each check is slow on purpose.
- **The full story** is in the old design note [`web-interface.md`](https://github.com/txoof/PaperPi/blob/main/docs/history/decisions/web-interface.md).

## In the code

- `src/paperpi/web/app.py`: the web server, its pages and the safety rules.
- `src/paperpi/web/auth.py` and `src/paperpi/web/password.py`: logging in and the password hash.
- `src/paperpi/web/forms.py`: the plugin settings pages.
- `src/paperpi/web/preview.py` and `src/paperpi/web/pictures.py`: the previews and the Library pictures.
- `src/paperpi/web/config_file.py` and `src/paperpi/web/changes.py`: writing the config file, and the Review changes page.
- `src/paperpi/web/keep.py`: **Keep these settings**.
- `src/paperpi/web/templates/`: the page templates.
