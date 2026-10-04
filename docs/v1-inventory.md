# v1 inventory: what to keep, what to drop

Milestone M1, issue #184. Status: proposal, waiting for txoof's approval.

## Problem

PaperPi v2 and epdlib v1 are new code. Nothing is copied from the old versions (PaperPi
branch `v1`, epdlib branch `v0.6`). So every feature, setting and open issue of the old
versions needs a decision: does it come back, in what form, and in which milestone?
This document lists them all, so nothing good is lost and nothing unwanted comes back by
accident.

**How to read it.** Each table row is one feature, setting or issue with a proposed decision:

| Decision | Meaning |
|---|---|
| **Keep** | Same behaviour in v2, written as new code. |
| **Change** | Keep the goal, but do it in a different way (the "why" column says how). |
| **Drop** | Not in v2. |
| **Add** | New in v2, listed where it replaces something from v1. |
| **Carry (Mx)** | (Issues only) Becomes a v2 issue in milestone Mx. |
| **Solved by design** | (Issues only) The v2 plan already removes the cause. Close the old issue. |
| **Close** | (Issues only) No longer relevant. Close the old issue. |

Milestones (from the plan): M2 IT8951 driver test round, M3 epdlib v1, M4 PaperPi core,
M5 web interface, M6 Docker install, M7 remaining plugins, M8 docs and release 2.0,
M9 several plugins on screen at once, M10 drag-and-drop screen regions.

Some terms used below:
- **Schema**: a written description of every setting: its name, type, allowed values and
  default. v2 checks the config file against it, and the web interface builds its forms from it.
- **Docker**: a tool that runs a program in a sealed-off box (a "container") with all the
  software it needs already inside, so it does not depend on what is installed on the Pi.
- **CI**: the automatic checks and builds that GitHub runs on every pull request.
- **IT8951**: the controller chip on the 9.7" display. "HD display" in v1 means a display with this chip.

## Options considered

1. **Port v1 feature by feature**, keeping every setting and command-line option. Rejected:
   it would bring back settings that only existed to work around v1 problems (several config
   files, daemon mode, the `xPlugin:` trick to switch a plugin off).
2. **Start from the plan only** and ignore v1. Rejected: v1 has good ideas and real user
   reports that the plan does not list.
3. **Go through everything in v1 and decide item by item** (chosen). This document is the result.

## Decision (proposed)

### 1. Good ideas from the plan

| Idea | Decision | Why | Milestone |
|---|---|---|---|
| Each plugin is a folder (update function, layouts, sample config, sample image) | Keep | Lets several people work on plugins at the same time without touching each other's files. v2 adds a settings schema and sample data to the folder. | M4 |
| Rotation by priority and minimum display time | Keep | Simple and worked well. Lower number = more important. | M4 |
| A plugin can change its own priority while running (e.g. music player goes to the front when a song starts, steps back when paused) | Keep | Makes the music plugins useful. | M4 |
| A higher-priority plugin interrupts the one on screen | Keep | Needed for the music plugins. | M4 |
| Layouts as data (dictionaries with relative sizes and positions) and automatic font size | Keep | One layout works on every display size. | M3 |
| Docs with sample images made by running each plugin | Keep | Docs never go out of date. v2 runs this in CI. | M8 (epdlib gallery: M3) |
| Skip unchanged screens | Change | v1 compared a marker that changed every time a plugin said "updated", even when the picture was the same. v2 compares the picture itself, so the screen is written only when something visible changed. | M4 |

### 2. PaperPi core behaviour

| v1 feature | Decision | Why | Milestone |
|---|---|---|---|
| Same plugin used several times with different settings (e.g. weather for two cities) | Keep | Users rely on it. | M4 |
| `refresh_rate`: a plugin fetches new data at most once per N seconds | Keep | Protects web services from too many requests. | M4 |
| Crashed plugin drops to lowest priority | Change | Keep the idea, but also log it clearly, retry later with a growing wait, and never send a broken image to the screen (v1 issue #159). | M4 |
| Plugin time limit using the operating system's alarm signal | Change | The alarm signal only works in the main thread and broke the web preview (#123). v2 time limits are designed in issue #190. | M4 |
| Fallback plugin (`default`) when no plugin is active | Keep | The screen should never stay blank or stale without explanation. Built into the core. | M4 |
| Splash screen at start-up | Keep | Shows that PaperPi started and which version. | M4 |
| Clean shutdown on Ctrl-C / stop signal, then optionally clear the screen | Keep | Leaves the display in a known state. | M4 |
| Full screen clear every N writes on IT8951 (`max_refresh`) | Keep | Removes faint leftover images (ghosting) after many fast updates. Belongs in the display driver. | M3 |
| Clear message when SPI is switched off | Keep | Common first-time mistake. The installer also checks it. | M4, M6 |
| Download cache in `/tmp` with expiry by age | Change | `/tmp` uses memory on trixie and the cache could grow without limit. v2 cache has a size limit and lives on disk. | M4 |
| Logging set up from `logging.cfg` | Change | Replaced by one setting for log level and logs with a size limit. | M4 |
| Bundled open-licence fonts | Keep | Plugins need fonts that exist on every install. | M4 |
| Text and background colour setting for colour displays, including `random` | Keep | Small feature, used by several plugins. Shared by all plugins. | M7 |
| Plugin files developed as Jupyter notebooks (`.ipynb` + jupytext) | Drop | The project rule is plain `.py` files only. | – |
| Deprecated `crypto` plugin (`plugins_depricated/`) | Drop | Already retired in v1. | – |

### 3. Config settings

v1 read up to three `.ini` files and merged them: the built-in base file, then either
`/etc/default/paperpi.ini` (daemon mode) or `~/.config/com.txoof.paperpi/paperpi.ini`
(user mode), or a file given with `-c`. **Change:** v2 has one config file, checked against
a schema when it is loaded, with clear error messages (design note #186). Every setting can
also be changed in the web interface (M5).

**`[main]` section**

| Setting | Decision | Why | Milestone |
|---|---|---|---|
| `display_type` | Keep | Chosen from the list of supported displays (generated from the driver list), not typed by hand. | M3, M4 |
| `vcom` | Keep | The IT8951 display needs the voltage printed on its cable. | M3 |
| `max_refresh` | Keep | See "full screen clear" above. Becomes a display setting. | M3 |
| `log_level` | Keep | Useful for troubleshooting. | M4 |
| `splash` | Keep | Some users want a quiet start. | M4 |
| `rotation` (0, 90, -90, 180) | Keep | Needed for frames and cases. | M3 |
| `mirror` | Keep | Some displays show the image backwards. | M3 |
| `color` | Change | v2 learns from the driver what the display can show (black/white, grey levels, colours). One setting remains: "force black and white". | M3 |
| `no_wipe` | Keep | Rename to a positive name such as `clear_screen_on_exit`. Default value: see question 9. | M4 |
| `plugin_timeout` | Keep | A default for all plugins, which each plugin can override. | M4 |
| `CONFIG_VERSION` comment line | Change | Becomes a real `config_version` field, so a newer PaperPi can update an older file. | M4 |
| `force_onebit`, `screen_mode` (set by the code, not by users) | Drop | Internal values; v2 gets them from the driver. | – |

**Settings every plugin section has**

| Setting | Decision | Why | Milestone |
|---|---|---|---|
| Section name `[Plugin: <your name>]` | Change | Keeps the idea of a free name per plugin instance, in the new file format. | M4 |
| `plugin` (which plugin folder) | Keep | | M4 |
| `layout` (which layout from the plugin) | Keep | Chosen from a list in the web interface. | M4, M5 |
| `refresh_rate`, `min_display_time`, `max_priority` | Keep | Core of the rotation. | M4 |
| Switching a plugin off by renaming its section to `[xPlugin: ...]` | Change | Replaced by an explicit on/off setting. | M4 |
| `text_color`, `bkground_color` | Keep | Only for colour displays. | M7 |

**Plugin-specific settings** (all **Keep** unless noted; each moves into that plugin's schema)

| Plugin | Settings | Notes | Milestone |
|---|---|---|---|
| basic_clock | none | | M4 |
| system_info | `storage_unit` | | M4 |
| met_no (weather) | `location_name`, `lat`, `lon`, `email`, `temp_units`, `rain_units`, `windspeed` | Add `altitude` (#176). `email` is required by met.no to identify the caller. | M4 |
| dec_binary_clock | none | v1 sample config names the plugin `dec_bin_clock`, which does not exist. v2 generates the sample, so this cannot happen again. | M7 |
| word_clock | none | | M7 |
| moon_phase | `location_name` (timezone), `lat`, `lon`, `email` | Timezone picked from a list instead of typed. | M7 |
| xkcd_comic | `max_x`, `max_y`, `resize`, `max_retries` | `resize` never worked (#61). | M7 |
| newyorker | `day_range` | | M7 |
| reddit_quote | `max_length`, `max_retries` | See question 3. | M7 |
| slideshow | `image_path`, `order` (random / sequential), `frame` (frame style) | In Docker the image folder must be shared into the container. | M7 |
| lms_client | `player_name`, `idle_timeout` | | M7 |
| librespot_client | `player_name`, `idle_timeout`, `port` | See question 4. | M7 |
| debugging | `title`, `crash_rate`, `max_priority_rate`, `min_priority` | Makes a plugin crash or change priority on purpose, for testing. See question 8. | M4 (as a test tool) |
| demo_plugin | `your_name`, `your_color` | Becomes the plugin template. See question 8. | M8 |
| default, splash_screen | none (not user plugins) | Built into the core. | M4 |

### 4. Command-line options

| v1 option | Decision | Why | Milestone |
|---|---|---|---|
| `-c`, `--config FILE` | Keep | Useful for testing a second config. | M4 |
| `-l`, `--log_level` | Keep | | M4 |
| `-V`, `--version` | Keep | | M4 |
| `--list_plugins` | Keep | | M4 |
| `-C`, `--compatible` (list supported displays) | Change | Becomes a `displays` command plus a generated table in the docs. | M3, M8 |
| `--plugin_info` | Change | Plugin info comes from the plugin's schema; shown in the docs, the web interface and a short command-line view. | M4 |
| `--run_plugin_func` (helper functions: find lat/lon for a place, list timezones, find LMS servers) | Change | Become lookups in the web interface plugin forms. See question 10. | M5, M7 |
| `-d`, `--daemon` | Drop | Docker runs PaperPi as a service; there is only one config file. | – |
| `--add_config` | Drop | Plugins are added in the web interface. | – |
| (new) `render <plugin>` | Add | Render any plugin to a PNG file without a display (from the plan). | M4 |

### 5. Install and packaging

| v1 feature | Decision | Why | Milestone |
|---|---|---|---|
| `install.sh`: copies files to `/usr/local/paperpi`, creates a Python environment, a `paperpi` system user in the `spi`/`gpio` groups, and a systemd service | Change | Replaced by the Docker image and a one-line install command. Kept ideas: PaperPi does not run as root, and the installer has uninstall and "uninstall and delete config" options. | M6 |
| `remote_install.sh` (download with `curl`, choose a branch with `-b`) | Change | One-line install that uses released Docker images instead of `git clone` (#165). | M6 |
| systemd `Restart=on-failure` | Change | Kept, plus a watchdog: PaperPi is restarted when it stops responding, not only when it crashes. This targets the freeze. | M4, M6 |
| Copy of Waveshare driver files inside PaperPi (`paperpi/waveshare_epd`) | Change | Display drivers live in epdlib only. | M3 |
| One `requirements-<plugin>.txt` per plugin, Pipfile, development set-up scripts | Drop | Replaced by `uv` and `pyproject.toml`. | – |
| `install_waveshare_libs.sh`, `debian_packages-*.txt` | Drop | Docker image contains everything. | – |
| `package.sh` | Drop | CI builds the Docker image. | – |

### 6. Documentation

| v1 feature | Decision | Why | Milestone |
|---|---|---|---|
| `create_documentation.py`: runs each plugin with sample data, saves a sample image, writes the plugin README and the plugin list page | Change | Same idea, run by CI and published as MkDocs pages. | M8 |
| The same script rebuilt `paperpi.ini` from every plugin's sample config | Drop | Caused #98. v2 makes a config reference from the schemas instead. | M8 |
| Hand-written guides: step-by-step install, troubleshooting, frame/cable/case, plugin development | Change | Rewritten for v2 in the user manual and plugin developer guide. Hardware notes (frame, cable, case) are worth keeping. | M8 |
| Spell check of the docs in CI | Keep | Cheap and catches mistakes. | M8 |

### 7. epdlib v0.6

| Feature | Decision | Why | Milestone |
|---|---|---|---|
| Layout: each block has `width`/`height` as a share of the screen, and a position that is either fixed (`abs_coordinates`) or next to another block (`relative`) | Keep | The core idea of epdlib. | M3 |
| Every block must state its `type` (TextBlock, ImageBlock, DrawBlock) | Keep | Makes layouts easy to check. | M3 |
| Automatic font size: largest size where sample text fits the block width and `max_lines` | Change | Same method, but a font size set in the layout must be used, not ignored (#58), and the method needs docs (#19). | M3 |
| `chardist` / `maxchar`: guess how many characters fit on a line from a typical letter mix for a language | Change | Measure the actual text with the font instead; fewer surprises. | M3 |
| TextBlock: wrapping, `max_lines`, "..." when text does not fit, left/right/centre alignment | Keep | | M3 |
| ImageBlock: scale to fit, remove transparency, centre horizontally/vertically | Keep | Add left/right/top/bottom alignment (#23). | M3 |
| DrawBlock: simple shapes (rectangle, ellipse, ...) with alignment and scaling | Keep | Used for separators and binary clock dots. | M3 |
| Block options: `padding`, `inverse`, `rand` (random position inside the block), border, fill and background colour | Keep | | M3 |
| HTML colour names, and mapping RED/ORANGE/YELLOW/GREEN/BLUE/BLACK/WHITE to the 7 Waveshare colours | Keep | | M3 |
| Change block colours and settings while running | Keep | Plugins use it. | M3 |
| Image modes: 1 bit, 8-bit grey (`L`), colour (`RGB`) | Change | The driver states which modes it supports; the layout renders in that mode. Adds 4-grey (section 8). | M3 |
| Colour reduction to the 7-colour palette, optional dithering (mixing dots to fake in-between colours) | Keep | | M3 |
| `Screen`: one class that loads any Waveshare or IT8951 driver by name | Change | Replaced by a driver interface with time limits and guaranteed release of SPI/GPIO (design note #188). | M3 |
| Partial refresh on IT8951 | Keep | Measured in the M2 test round. | M2, M3 |
| `list_compatible` and the supported-screens table in the README | Change | Table generated from the driver list. | M3 |
| `ScreenShot`: keep the last N screen images as files for debugging | Change | Replaced by the "virtual" driver that writes PNG files. | M3 |
| `strict_enforce` type-checking decorators | Drop | Replaced by type hints checked with `mypy`. | M3 |
| `RPi.GPIO` dependency | Drop | Only `gpiod` and `spidev` (plan). | M3 |
| PyPI release workflow | Change | Being replaced in epdlib #76. | M0 |

### 8. 4-colour greyscale displays

**Background.** Several small Waveshare black-and-white displays (for example the 2.7")
can also show 4 grey levels. PaperPi #166 and epdlib #71 asked for this, and ThomasR built it
in epdlib PR #72. He then closed his own work because:
- photos looked worse in 4 grey than in 1 bit with dithering, because Pillow (the image
  library) gives no control over how it dithers to 4 levels;
- on the real display, the same grey pixel looked darker or lighter depending on the pixels
  around it, and this differs between display models;
- text with smoother edges (anti-aliasing) did become easier to read on small screens.

txoof agreed the extra complexity gave little value then. The PR was closed with a promise to
carry the idea into epdlib v1.

**Proposal.**
- **M3:** the driver interface lets each driver list the modes it supports (1 bit, 4 grey,
  16 grey, colour). This costs little and keeps the door open.
- **M3, if a test display is available, otherwise later:** a 4-grey mode for Waveshare displays
  that support it. **Off by default**; the user switches it on per display. Images are dithered
  with our own palette (ThomasR's tested values are a starting point), not Pillow's default.
- Image tests compare 1-bit and 4-grey output of the same layout, so the difference is visible
  in the PR.

See question 1.

### 9. Open v1 issues: PaperPi

28 open issues (the M1 issue said 21; the count was out of date). New M1 issues #184–#191 are not listed.

| Issue | Decision | Reason |
|---|---|---|
| #177 Multiple issues to support PaperPi on trixie | Solved by design (M3, M6) | v2 targets Python 3.13 on trixie, uses no `distutils` and no `RPi.GPIO`, and installs with Docker. |
| #176 Add altitude to weather plugin | Carry (M4) | Real bug in forecasts; small change while porting met_no. |
| #174 No display, "padded area too small" warning | Solved by design (M4, M5) | The chosen layout is too dense for a small display. v2 shows a preview (`render` command, web preview) and a clear message. |
| #173 4inch HAT+ (E) not supported | Carry (M3) | v2 uses Waveshare's current driver files, which include newer displays. Needs a tester with the display (question 2). |
| #172 Not displaying anything, padded area too small | Solved by design (M4, M5) | Same as #174. |
| #167 No module named 'ArgConfigParse' | Solved by design (M6) | v2 does not use ArgConfigParse; Docker contains all packages. |
| #166 Add grayscale support for B/W displays | Carry (M3) | See section 8. |
| #165 Use releases for installer | Solved by design (M6) | Installer uses released Docker images from GHCR (GitHub's image registry). |
| #159 PaperPi stops displaying images after several hours | Carry (M4) | Part of the freeze investigation (#185); v2 never shows a broken image and restarts when stuck. |
| #150 Non-IT8951 screens incompatible with HiFiBerry | Carry (M3) | The Waveshare driver claims GPIO 24, which the HiFiBerry also uses. v2 wraps the drivers and can make the pin configurable. HiFiBerry is in the plan's test hardware. |
| #144 Improve prompting in moon phase helper | Solved by design (M5, M7) | Helper functions become lookups in the web interface. |
| #143 Refactor utility scripts for requirements.txt | Close | `uv` and `pyproject.toml` replace these scripts. |
| #140 Refactor modules for JSON configuration | Solved by design (M4) | New config format and schema (#186). |
| #139 Menu-driven command-line configuration | Solved by design (M5) | The web interface does this. See question 11. |
| #130 Updates to documentation builder | Solved by design (M8) | Docs are generated in CI from the schemas. |
| #123 Web interface for configuration | Solved by design (M5) | The web interface is milestone M5. |
| #98 Docs creation overwrites the ini file | Close | v2 docs builder does not write config files. |
| #56 Improve exit on bad config file | Solved by design (M4) | Config is checked against the schema with clear messages. |
| #42 Prompt to edit user config in install.sh | Close | The old installer is replaced. |
| #41 create_devel_environment fails with Pipfile | Close | Pipfile and the script are gone. |
| #35 Conflicting paperpi.ini files | Solved by design (M4) | v2 has one config file. |
| #13 Packaging plugin (install plugins from outside) | Close | Not planned before 2.0. See question 12. |
| #60 Missing fonts crash PaperPi | Carry (M4) | A plugin with a missing font must be switched off with a clear error, not stop PaperPi. Add a test. |
| #61 xkcd does not respect resize | Carry (M7) | Real bug. |
| #64 Border space in xkcd layouts | Carry (M7) | Small layout change; useful with framed displays. |
| #65 reddit quote needs better character clean-up | Carry (M7) | Only if reddit_quote stays (question 3). |
| #63 xkcd: show comic number or QR code | Carry (M7) | Small feature. |
| #62 Update layouts without restarting | Solved by design (M5) | Config changes apply without a restart (#189). |

### 10. Open v1 issues: epdlib

#76 (new release workflow) is not listed.

| Issue | Decision | Reason |
|---|---|---|
| #73 Support 3.7" screen | Carry (M3) | Its driver has different function arguments; the v2 driver wrapper can handle that per display. Needs a tester (question 2). |
| #71 Grayscale support for epd2in7 | Carry (M3) | See section 8. |
| #58 Force larger font size | Carry (M3) | A font size set in the layout must win over the automatic size. |
| #23 Left/right/top/bottom alignment for images | Carry (M3) | Small, useful. |
| #19 Explain how TextBlocks choose font size and handle overflow | Carry (M3) | Part of the epdlib docs and layout gallery. |
| #14 Italic fonts cut off at the left edge | Carry (M3) | Measure the real text outline; add an image test with an italic font. |

After txoof approves this document, txoof closes the old issues marked "Solved by design" and
"Close", and the "Carry" items become new issues in their milestone.

## Open questions

Please answer by number.

1. **4-grey mode:** is the proposal in section 8 OK (driver lists its modes in M3; 4-grey off by
   default)? Do you own a display that supports 4 grey (for example the 2.7")? Without one we
   cannot test it, and it moves to after M3.
2. **Test displays:** which small Waveshare displays do you own? This decides which displays get
   hardware tests in M3, and whether #173 (4inch HAT+ E, a colour display) and epdlib #73 (3.7")
   can be fixed or need a user to test.
3. **reddit_quote:** Reddit has limited access without an account since 2023. Keep it (and check
   that it still works), replace it with another quote source, or drop it?
4. **librespot_client:** v1 supports go-librespot and librespot-java (SpoCon), and marks the second
   as deprecated. Support only go-librespot in v2?
5. **newyorker:** it reads the New Yorker daily cartoon feed. Keep it in M7 (if the feed still works)?
6. **Clock in M4:** the plan ports "clock" in M4 and lists `basic_clock` again in M7. Use
   `basic_clock` in M4 and remove it from the M7 list?
7. **default and splash_screen:** the plan lists them in M7, but the core needs a fallback screen and
   a start-up screen from M4. Move both into the M4 core?
8. **debugging and demo_plugin:** ship them to users, or keep `debugging` as a test tool only (M4)
   and turn `demo_plugin` into the plugin template in the developer guide (M8)?
9. **Clear screen on exit:** v1's built-in default leaves the last image on screen; the sample
   config clears it. Which default do you want in v2?
10. **Helper functions:** OK to move the plugin helpers (find lat/lon, list timezones, find LMS
    servers) into the web interface only, with no command-line version?
11. **#139:** close it, since the web interface replaces a text-menu setup?
12. **Plugins from outside the repo (#13):** not needed before 2.0, so close it?
13. **Old config files:** should v2 offer a one-time import of a v1 `paperpi.ini`, or do users set
    up v2 from scratch in the web interface?
